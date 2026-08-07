"""Marketing automation service."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.marketing.ai_chooser import MarketingAiChooser, recommendation_cooldown_days
from app.marketing.channels import ChannelRouter
from app.marketing.enums import CampaignStatus, CampaignType, Channel, MessageStatus
from app.marketing.models import (
    AudienceMember,
    CalendarEvent,
    Campaign,
    CampaignMessage,
    CampaignMetrics,
    MarketingLog,
)
from app.marketing.queue import MessageQueue
from app.marketing.scheduler import CampaignScheduler
from app.marketing.store import (
    MarketingStorePort,
    compute_metrics,
    demo_audience,
    is_demo_campaign,
    is_demo_member,
)

# Channels that suppress re-recommendation for AI Suggestions.
_RECOMMENDATION_CHANNELS = (Channel.SMS, Channel.EMAIL)


class MarketingAutomationService:
    def __init__(
        self,
        *,
        store: MarketingStorePort,
        scheduler: CampaignScheduler,
        queue: MessageQueue,
        chooser: MarketingAiChooser,
        channels: ChannelRouter,
    ) -> None:
        self._store = store
        self._scheduler = scheduler
        self._queue = queue
        self._chooser = chooser
        self._channels = channels

    async def create_campaign(
        self,
        *,
        shop_id: UUID,
        name: str,
        campaign_type: CampaignType | str,
        channels_allowed: list[str] | None = None,
        audience: list[dict[str, Any]] | None = None,
        custom_message: str | None = None,
        scheduled_start: datetime | None = None,
        max_sends_per_customer_days: int = 14,
        budget: Decimal | None = None,
        expected_revenue: Decimal | None = None,
        tags: list[str] | None = None,
        use_demo_audience: bool = False,
        metadata: dict[str, Any] | None = None,
        auto_schedule: bool = False,
    ) -> Campaign:
        ctype = campaign_type if isinstance(campaign_type, CampaignType) else CampaignType(campaign_type)
        members: list[AudienceMember]
        if use_demo_audience:
            members = demo_audience()
        elif audience:
            members = [_parse_member(a) for a in audience]
        else:
            members = []

        meta = dict(metadata or {})
        if "shop_name" not in meta:
            meta["shop_name"] = "your shop"

        chans = [Channel(c) for c in (channels_allowed or ["sms", "email"])]
        campaign = Campaign(
            id=uuid4(),
            shop_id=shop_id,
            name=name,
            campaign_type=ctype,
            status=CampaignStatus.DRAFT,
            channels_allowed=chans,
            audience=members,
            custom_message=custom_message,
            scheduled_start=scheduled_start,
            max_sends_per_customer_days=max_sends_per_customer_days,
            budget=budget or Decimal("0"),
            expected_revenue=expected_revenue or Decimal("0"),
            tags=tags or [],
            metadata=meta,
        )
        campaign.ai_defaults = self._chooser.plan_campaign_defaults(campaign)
        await self._store.save_campaign(campaign)
        await self._store.add_log(
            MarketingLog(
                shop_id=shop_id,
                campaign_id=campaign.id,
                event="campaign.created",
                detail=campaign.name,
            )
        )
        if auto_schedule:
            await self.schedule_campaign(shop_id, campaign.id)
            campaign = await self.get_campaign(shop_id, campaign.id)
        return campaign

    async def list_campaigns(
        self, shop_id: UUID, *, status: CampaignStatus | None = None, exclude_demo: bool = False
    ) -> list[Campaign]:
        campaigns = await self._store.list_campaigns(shop_id, status=status)
        if exclude_demo:
            campaigns = [c for c in campaigns if not is_demo_campaign(c)]
        return campaigns

    async def get_campaign(self, shop_id: UUID, campaign_id: UUID) -> Campaign:
        c = await self._store.get_campaign(shop_id, campaign_id)
        if c is None:
            raise LookupError("Campaign not found")
        return c

    async def update_campaign(
        self, shop_id: UUID, campaign_id: UUID, patch: dict[str, Any]
    ) -> Campaign:
        c = await self.get_campaign(shop_id, campaign_id)
        if c.status not in {CampaignStatus.DRAFT, CampaignStatus.PAUSED, CampaignStatus.SCHEDULED}:
            if "status" not in patch:
                raise PermissionError("Only draft/paused/scheduled campaigns can be edited")
        if "name" in patch and patch["name"]:
            c.name = str(patch["name"])
        if "custom_message" in patch:
            c.custom_message = patch["custom_message"]
        if "status" in patch and patch["status"]:
            c.status = CampaignStatus(patch["status"])
        if "channels_allowed" in patch and patch["channels_allowed"] is not None:
            c.channels_allowed = [Channel(x) for x in patch["channels_allowed"]]
        if "scheduled_start" in patch:
            c.scheduled_start = patch["scheduled_start"]
        if "tags" in patch and patch["tags"] is not None:
            c.tags = list(patch["tags"])
        if "budget" in patch and patch["budget"] is not None:
            c.budget = Decimal(str(patch["budget"]))
        if "expected_revenue" in patch and patch["expected_revenue"] is not None:
            c.expected_revenue = Decimal(str(patch["expected_revenue"]))
        c.ai_defaults = self._chooser.plan_campaign_defaults(c)
        return await self._store.save_campaign(c)

    async def schedule_campaign(self, shop_id: UUID, campaign_id: UUID) -> list[CampaignMessage]:
        campaign = await self.get_campaign(shop_id, campaign_id)
        if campaign.status == CampaignStatus.CANCELLED:
            raise ValueError("Cannot schedule cancelled campaign")
        return await self._scheduler.schedule_campaign(campaign)

    async def process_queue(
        self,
        *,
        now: datetime | None = None,
        shop_id: UUID | None = None,
    ) -> list[CampaignMessage]:
        return await self._scheduler.process_due(now=now, shop_id=shop_id)

    async def process_campaign_now(
        self, shop_id: UUID, campaign_id: UUID, *, now: datetime | None = None
    ) -> list[CampaignMessage]:
        """Force pending queue items for a campaign to run immediately (ops / demo)."""
        now = now or datetime.now(timezone.utc)
        await self.get_campaign(shop_id, campaign_id)
        await self._store.force_campaign_queue_due(
            shop_id, campaign_id, now=now - timedelta(seconds=1)
        )
        return await self._scheduler.process_due(
            now=now, shop_id=shop_id, campaign_id=campaign_id
        )

    async def delete_message(self, shop_id: UUID, message_id: UUID) -> None:
        message = await self._store.get_message(shop_id, message_id)
        if message is None:
            raise LookupError("Message not found")
        ok = await self._store.delete_message(shop_id, message_id)
        if not ok:
            raise LookupError("Message not found")
        await self._store.add_log(
            MarketingLog(
                shop_id=shop_id,
                campaign_id=message.campaign_id,
                message_id=message.id,
                event="message.deleted",
                detail="Message record deleted",
            )
        )

    async def delete_messages(self, shop_id: UUID, message_ids: list[UUID]) -> int:
        ids = list(dict.fromkeys(message_ids))
        if not ids:
            return 0
        count = await self._store.delete_messages(shop_id, ids)
        if count > 0:
            await self._store.add_log(
                MarketingLog(
                    shop_id=shop_id,
                    campaign_id=None,
                    message_id=None,
                    event="messages.deleted_bulk",
                    detail=f"Deleted {count} message record(s)",
                )
            )
        return count

    async def delete_all_messages(self, shop_id: UUID) -> int:
        count = await self._store.delete_all_messages(shop_id)
        if count > 0:
            await self._store.add_log(
                MarketingLog(
                    shop_id=shop_id,
                    campaign_id=None,
                    message_id=None,
                    event="messages.deleted_all",
                    detail=f"Deleted {count} message record(s)",
                )
            )
        return count

    async def track_event(
        self,
        shop_id: UUID,
        message_id: UUID,
        *,
        event: str,
        appointment_id: UUID | None = None,
        revenue: Decimal | None = None,
    ) -> CampaignMessage:
        message = await self._store.get_message(shop_id, message_id)
        if message is None:
            raise LookupError("Message not found")
        now = datetime.now(timezone.utc)
        kind = (event or "").strip().lower()
        # Accept open/opened, click/clicked, reply/replied synonyms from clients.
        if kind in {"open", "opened"}:
            message.opened_at = message.opened_at or now
            message.status = MessageStatus.OPENED
            kind = "open"
        elif kind in {"click", "clicked"}:
            message.clicked_at = message.clicked_at or now
            message.opened_at = message.opened_at or now
            message.status = MessageStatus.CLICKED
            kind = "click"
        elif kind in {"reply", "replied"}:
            message.replied_at = message.replied_at or now
            message.status = MessageStatus.REPLIED
            kind = "reply"
        elif kind == "appointment":
            message.appointment_id = appointment_id or message.appointment_id or uuid4()
            message.revenue = revenue or message.revenue or Decimal("150")
        elif kind == "revenue":
            message.revenue = revenue or message.revenue
        else:
            raise ValueError(f"Unknown event: {event}")
        await self._store.save_message(message)
        await self._store.add_log(
            MarketingLog(
                shop_id=shop_id,
                campaign_id=message.campaign_id,
                message_id=message.id,
                event=f"track.{kind}",
                detail=str(revenue or appointment_id or ""),
            )
        )
        return message

    async def get_metrics(self, shop_id: UUID, campaign_id: UUID) -> CampaignMetrics:
        await self.get_campaign(shop_id, campaign_id)
        messages = await self._store.list_messages(shop_id, campaign_id)
        return compute_metrics(shop_id, campaign_id, messages)

    async def analytics_summary(self, shop_id: UUID, *, exclude_demo: bool = False) -> dict[str, Any]:
        campaigns = await self.list_campaigns(shop_id, exclude_demo=exclude_demo)
        totals = {
            "campaigns": len(campaigns),
            "sent": 0,
            "opened": 0,
            "clicked": 0,
            "replied": 0,
            "appointments": 0,
            "revenue": Decimal("0"),
            "cost": Decimal("0"),
            "by_type": {},
            "by_channel": {"sms": 0, "email": 0, "voice": 0},
        }
        per_campaign = []
        for c in campaigns:
            messages = await self._store.list_messages(shop_id, c.id)
            m = compute_metrics(shop_id, c.id, messages)
            totals["sent"] += m.sent
            totals["opened"] += m.opened
            totals["clicked"] += m.clicked
            totals["replied"] += m.replied
            totals["appointments"] += m.appointments
            totals["revenue"] += m.revenue
            totals["cost"] += m.cost
            totals["by_type"][c.campaign_type.value] = totals["by_type"].get(c.campaign_type.value, 0) + 1
            for msg in messages:
                if msg.sent_at:
                    totals["by_channel"][msg.channel.value] = totals["by_channel"].get(msg.channel.value, 0) + 1
            per_campaign.append(
                {
                    "campaign_id": str(c.id),
                    "name": c.name,
                    "type": c.campaign_type.value,
                    "status": c.status.value,
                    "open_rate": m.open_rate,
                    "click_rate": m.click_rate,
                    "reply_rate": m.reply_rate,
                    "appointment_rate": m.appointment_rate,
                    "revenue": str(m.revenue),
                    "roi": m.roi,
                }
            )
        sent = totals["sent"] or 1
        return {
            "campaigns": totals["campaigns"],
            "sent": totals["sent"],
            "open_rate": round(totals["opened"] / sent, 4),
            "click_rate": round(totals["clicked"] / sent, 4),
            "reply_rate": round(totals["replied"] / sent, 4),
            "appointment_rate": round(totals["appointments"] / sent, 4),
            "revenue": str(totals["revenue"].quantize(Decimal("0.01"))),
            "cost": str(totals["cost"].quantize(Decimal("0.01"))),
            "roi": round(float(totals["revenue"] - totals["cost"]) / float(totals["cost"] or 1), 2),
            "by_type": totals["by_type"],
            "by_channel": totals["by_channel"],
            "campaigns_detail": per_campaign,
        }

    async def calendar(
        self,
        shop_id: UUID,
        *,
        start: date | None = None,
        end: date | None = None,
        exclude_demo: bool = False,
    ) -> list[CalendarEvent]:
        start = start or date.today()
        end = end or (start + timedelta(days=30))
        events: list[CalendarEvent] = []
        for c in await self.list_campaigns(shop_id, exclude_demo=exclude_demo):
            messages = await self._store.list_messages(shop_id, c.id)
            by_day: dict[date, list[CampaignMessage]] = {}
            for m in messages:
                day = (m.scheduled_at or m.sent_at or c.scheduled_start or c.created_at)
                if day is None:
                    continue
                d = day.date() if isinstance(day, datetime) else day
                if d < start or d > end:
                    continue
                by_day.setdefault(d, []).append(m)
            if not by_day and c.scheduled_start:
                d = c.scheduled_start.date()
                if start <= d <= end:
                    events.append(
                        CalendarEvent(
                            campaign_id=c.id,
                            name=c.name,
                            campaign_type=c.campaign_type,
                            status=c.status,
                            day=d,
                            channel=c.ai_defaults.channel if c.ai_defaults else None,
                            message_count=len(c.audience),
                        )
                    )
            for d, msgs in by_day.items():
                ch = msgs[0].channel if msgs else None
                events.append(
                    CalendarEvent(
                        campaign_id=c.id,
                        name=c.name,
                        campaign_type=c.campaign_type,
                        status=c.status,
                        day=d,
                        channel=ch,
                        message_count=len(msgs),
                    )
                )
        events.sort(key=lambda e: e.day)
        return events

    async def list_logs(
        self, shop_id: UUID, *, campaign_id: UUID | None = None, limit: int = 100
    ) -> list[MarketingLog]:
        return await self._store.list_logs(shop_id, campaign_id=campaign_id, limit=limit)

    async def preview_ai(
        self, shop_id: UUID, campaign_id: UUID, customer_id: UUID | None = None
    ) -> dict[str, Any]:
        campaign = await self.get_campaign(shop_id, campaign_id)
        if not campaign.audience:
            raise LookupError("Campaign has no audience members")
        # Prefer non-demo contacts when mixed. When CRM data reuses sample phone/email
        # fingerprints (common in local shops), fall back to the campaign audience so
        # AI Recommendations can still preview after a successful create.
        preferred = [a for a in campaign.audience if not is_demo_member(a)]
        pool = preferred or list(campaign.audience)
        member = next((a for a in pool if a.customer_id == customer_id), None)
        if member is None:
            member = pool[0]
        plan = self._chooser.plan_for_member(campaign, member)
        meta = member.metadata or {}
        return {
            "customer_id": str(member.customer_id),
            "customer_name": member.name,
            "phone": member.phone,
            "email": member.email,
            "vehicle": meta.get("vehicle"),
            "service": meta.get("service"),
            "channel": plan.channel.value,
            "send_at": plan.send_at.isoformat(),
            "message": plan.message,
            "subject": plan.subject,
            "frequency_days": plan.frequency_days,
            "confidence": plan.confidence,
            "reasons": plan.reasons,
        }

    async def customers_in_recommendation_cooldown(
        self,
        shop_id: UUID,
        campaign_type: CampaignType | str,
        *,
        now: datetime | None = None,
        cooldown_days: int | None = None,
    ) -> set[UUID]:
        """Customers who received SMS/email for this campaign type within the cooldown window."""
        now = now or datetime.now(timezone.utc)
        days = cooldown_days if cooldown_days is not None else recommendation_cooldown_days(
            campaign_type
        )
        if days <= 0:
            return set()
        ctype = (
            campaign_type.value
            if isinstance(campaign_type, CampaignType)
            else str(campaign_type)
        )
        since = now - timedelta(days=days)
        return await self._store.recently_contacted_customer_ids(
            shop_id,
            campaign_type=ctype,
            channels=list(_RECOMMENDATION_CHANNELS),
            since=since,
        )

    def filter_audience_for_recommendations(
        self,
        members: list[AudienceMember],
        suppressed: set[UUID],
    ) -> list[AudienceMember]:
        if not suppressed:
            return members
        return [m for m in members if m.customer_id not in suppressed]


def _parse_member(raw: dict[str, Any]) -> AudienceMember:
    return AudienceMember(
        customer_id=UUID(str(raw["customer_id"])) if raw.get("customer_id") else uuid4(),
        name=str(raw.get("name") or "Customer"),
        phone=raw.get("phone"),
        email=raw.get("email"),
        preferred_channel=Channel(raw["preferred_channel"]) if raw.get("preferred_channel") else None,
        metadata=dict(raw.get("metadata") or {}),
    )
