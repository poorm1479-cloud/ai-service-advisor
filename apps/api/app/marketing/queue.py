"""Message queue + retry processing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.marketing.enums import MessageStatus, QueueItemState
from app.marketing.models import CampaignMessage, MarketingLog, QueueItem
from app.marketing.store import MarketingStorePort


class MessageQueue:
    def __init__(self, store: MarketingStorePort, *, max_attempts: int = 3) -> None:
        self._store = store
        self._max_attempts = max_attempts

    async def enqueue_message(
        self,
        message: CampaignMessage,
        *,
        run_at: datetime | None = None,
    ) -> QueueItem:
        item = QueueItem(
            id=uuid4(),
            shop_id=message.shop_id,
            message_id=message.id,
            campaign_id=message.campaign_id,
            run_at=run_at or message.scheduled_at or datetime.now(timezone.utc),
            state=QueueItemState.PENDING,
            attempt=0,
            max_attempts=self._max_attempts,
        )
        message.status = MessageStatus.SCHEDULED
        await self._store.save_message(message)
        await self._store.enqueue(item)
        await self._store.add_log(
            MarketingLog(
                shop_id=message.shop_id,
                campaign_id=message.campaign_id,
                message_id=message.id,
                event="queue.enqueued",
                detail=f"run_at={item.run_at.isoformat()}",
            )
        )
        return item

    async def schedule_retry(
        self,
        item: QueueItem,
        message: CampaignMessage,
        *,
        error: str,
        backoff_ms: int = 1000,
    ) -> QueueItem | None:
        next_attempt = item.attempt + 1
        if next_attempt >= item.max_attempts:
            item.state = QueueItemState.EXHAUSTED
            item.last_error = error
            message.status = MessageStatus.FAILED
            message.error = error
            await self._store.save_message(message)
            await self._store.save_queue_item(item)
            await self._store.add_log(
                MarketingLog(
                    shop_id=message.shop_id,
                    campaign_id=message.campaign_id,
                    message_id=message.id,
                    level="error",
                    event="queue.exhausted",
                    detail=error,
                )
            )
            return None

        delay = backoff_ms * (2 ** max(item.attempt, 0))
        item.attempt = next_attempt
        item.state = QueueItemState.PENDING
        item.last_error = error
        item.run_at = datetime.now(timezone.utc) + timedelta(milliseconds=delay)
        message.status = MessageStatus.RETRYING
        message.attempt = next_attempt
        message.error = error
        await self._store.save_message(message)
        await self._store.save_queue_item(item)
        await self._store.add_log(
            MarketingLog(
                shop_id=message.shop_id,
                campaign_id=message.campaign_id,
                message_id=message.id,
                level="warn",
                event="queue.retry",
                detail=f"attempt={next_attempt} error={error}",
            )
        )
        return item
