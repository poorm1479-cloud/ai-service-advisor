"""Campaign scheduler — materialize AI plans into queued messages + drain queue."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.marketing.ai_chooser import MarketingAiChooser
from app.marketing.channels import ChannelRouter
from app.marketing.enums import CampaignStatus, MessageStatus, QueueItemState
from app.marketing.models import Campaign, CampaignMessage, MarketingLog
from app.marketing.queue import MessageQueue
from app.marketing.store import MarketingStorePort


class CampaignScheduler:
    def __init__(
        self,
        *,
        store: MarketingStorePort,
        queue: MessageQueue,
        channels: ChannelRouter,
        chooser: MarketingAiChooser,
    ) -> None:
        self._store = store
        self._queue = queue
        self._channels = channels
        self._chooser = chooser

    async def schedule_campaign(
        self, campaign: Campaign, *, now: datetime | None = None
    ) -> list[CampaignMessage]:
        now = now or datetime.now(timezone.utc)
        plan_default = self._chooser.plan_campaign_defaults(campaign, now=now)
        campaign.ai_defaults = plan_default
        campaign.status = CampaignStatus.SCHEDULED
        if campaign.scheduled_start is None:
            campaign.scheduled_start = plan_default.send_at
        await self._store.save_campaign(campaign)

        messages: list[CampaignMessage] = []
        for member in campaign.audience:
            plan = self._chooser.plan_for_member(campaign, member, now=now)
            msg = CampaignMessage(
                id=uuid4(),
                shop_id=campaign.shop_id,
                campaign_id=campaign.id,
                customer_id=member.customer_id,
                channel=plan.channel,
                status=MessageStatus.SCHEDULED,
                body=plan.message,
                subject=plan.subject,
                scheduled_at=plan.send_at,
                ai_plan=plan,
                metadata={
                    "to_phone": member.phone,
                    "to_email": member.email,
                    "name": member.name,
                },
            )
            await self._store.save_message(msg)
            await self._queue.enqueue_message(msg, run_at=plan.send_at)
            messages.append(msg)

        await self._store.add_log(
            MarketingLog(
                shop_id=campaign.shop_id,
                campaign_id=campaign.id,
                event="campaign.scheduled",
                detail=f"{len(messages)} messages planned",
            )
        )
        return messages

    async def process_due(self, *, now: datetime | None = None, limit: int = 100) -> list[CampaignMessage]:
        now = now or datetime.now(timezone.utc)
        due = await self._store.list_due_queue(now=now, limit=limit)
        processed: list[CampaignMessage] = []

        # Mark parent campaigns running
        campaign_ids: set[UUID] = set()

        for item in due:
            item.state = QueueItemState.IN_FLIGHT
            await self._store.save_queue_item(item)
            message = await self._store.get_message(item.shop_id, item.message_id)
            if message is None:
                item.state = QueueItemState.FAILED
                await self._store.save_queue_item(item)
                continue

            campaign_ids.add(message.campaign_id)
            message.status = MessageStatus.SENDING
            message.attempt = item.attempt + 1
            await self._store.save_message(message)

            to = self._recipient(message)
            if not to:
                message.status = MessageStatus.FAILED
                message.error = "No recipient address for channel"
                await self._store.save_message(message)
                item.state = QueueItemState.FAILED
                item.last_error = message.error
                await self._store.save_queue_item(item)
                continue

            sender = self._channels.get(message.channel)
            result = await sender.send(message, to=to)
            if result.ok:
                message.status = MessageStatus.SENT
                message.sent_at = now
                message.provider_id = result.provider_id
                message.error = None
                await self._store.save_message(message)
                item.state = QueueItemState.SUCCEEDED
                item.attempt = message.attempt
                await self._store.save_queue_item(item)
                await self._store.add_log(
                    MarketingLog(
                        shop_id=message.shop_id,
                        campaign_id=message.campaign_id,
                        message_id=message.id,
                        event="message.sent",
                        detail=f"channel={message.channel.value} provider={result.provider_id}",
                    )
                )
                processed.append(message)
            else:
                await self._queue.schedule_retry(
                    item, message, error=result.error or "send failed", backoff_ms=500
                )

        for cid in campaign_ids:
            # Pick any shop from processed/due
            shop_id = due[0].shop_id if due else None
            if shop_id is None:
                continue
            campaign = await self._store.get_campaign(shop_id, cid)
            if campaign and campaign.status == CampaignStatus.SCHEDULED:
                campaign.status = CampaignStatus.RUNNING
                await self._store.save_campaign(campaign)

        return processed

    def _recipient(self, message: CampaignMessage) -> str | None:
        meta = message.metadata or {}
        if message.channel.value == "sms" or message.channel.value == "voice":
            return meta.get("to_phone")
        return meta.get("to_email")
