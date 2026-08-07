"""Marketing store port + in-memory implementation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from app.marketing.enums import CampaignStatus, Channel, MessageStatus, QueueItemState
from app.marketing.models import (
    AudienceMember,
    Campaign,
    CampaignMessage,
    CampaignMetrics,
    MarketingLog,
    QueueItem,
)


class MarketingStorePort(Protocol):
    async def save_campaign(self, campaign: Campaign) -> Campaign: ...

    async def get_campaign(self, shop_id: UUID, campaign_id: UUID) -> Campaign | None: ...

    async def list_campaigns(
        self, shop_id: UUID, *, status: CampaignStatus | None = None
    ) -> list[Campaign]: ...

    async def save_message(self, message: CampaignMessage) -> CampaignMessage: ...

    async def get_message(self, shop_id: UUID, message_id: UUID) -> CampaignMessage | None: ...

    async def list_messages(
        self, shop_id: UUID, campaign_id: UUID, *, limit: int = 500
    ) -> list[CampaignMessage]: ...

    async def recently_contacted_customer_ids(
        self,
        shop_id: UUID,
        *,
        campaign_type: str,
        channels: list[Channel],
        since: datetime,
    ) -> set[UUID]:
        """Customer IDs with a sent SMS/email (etc.) for campaign_type on/after since."""
        ...

    async def delete_message(self, shop_id: UUID, message_id: UUID) -> bool: ...

    async def delete_messages(self, shop_id: UUID, message_ids: list[UUID]) -> int: ...

    async def delete_all_messages(self, shop_id: UUID) -> int: ...

    async def enqueue(self, item: QueueItem) -> QueueItem: ...

    async def list_due_queue(
        self,
        *,
        now: datetime,
        limit: int = 100,
        shop_id: UUID | None = None,
        campaign_id: UUID | None = None,
    ) -> list[QueueItem]: ...

    async def save_queue_item(self, item: QueueItem) -> QueueItem: ...

    async def force_campaign_queue_due(
        self, shop_id: UUID, campaign_id: UUID, *, now: datetime
    ) -> int: ...

    async def add_log(self, log: MarketingLog) -> MarketingLog: ...

    async def list_logs(
        self, shop_id: UUID, *, campaign_id: UUID | None = None, limit: int = 100
    ) -> list[MarketingLog]: ...


class InMemoryMarketingStore:
    def __init__(self) -> None:
        self.campaigns: dict[UUID, Campaign] = {}
        self.messages: dict[UUID, CampaignMessage] = {}
        self.queue: dict[UUID, QueueItem] = {}
        self.logs: list[MarketingLog] = []

    async def save_campaign(self, campaign: Campaign) -> Campaign:
        now = datetime.now(timezone.utc)
        if campaign.created_at is None:
            campaign.created_at = now
        campaign.updated_at = now
        self.campaigns[campaign.id] = campaign
        return campaign

    async def get_campaign(self, shop_id: UUID, campaign_id: UUID) -> Campaign | None:
        c = self.campaigns.get(campaign_id)
        if c is None or c.shop_id != shop_id:
            return None
        return c

    async def list_campaigns(
        self, shop_id: UUID, *, status: CampaignStatus | None = None
    ) -> list[Campaign]:
        items = [c for c in self.campaigns.values() if c.shop_id == shop_id]
        if status:
            items = [c for c in items if c.status == status]
        items.sort(key=lambda c: c.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items

    async def save_message(self, message: CampaignMessage) -> CampaignMessage:
        if message.created_at is None:
            message.created_at = datetime.now(timezone.utc)
        self.messages[message.id] = message
        return message

    async def get_message(self, shop_id: UUID, message_id: UUID) -> CampaignMessage | None:
        m = self.messages.get(message_id)
        if m is None or m.shop_id != shop_id:
            return None
        return m

    async def list_messages(
        self, shop_id: UUID, campaign_id: UUID, *, limit: int = 500
    ) -> list[CampaignMessage]:
        items = [
            m
            for m in self.messages.values()
            if m.shop_id == shop_id and m.campaign_id == campaign_id
        ]
        items.sort(key=lambda m: m.created_at or datetime.min.replace(tzinfo=timezone.utc))
        return items[:limit]

    async def recently_contacted_customer_ids(
        self,
        shop_id: UUID,
        *,
        campaign_type: str,
        channels: list[Channel],
        since: datetime,
    ) -> set[UUID]:
        channel_set = set(channels)
        matching_campaign_ids = {
            c.id
            for c in self.campaigns.values()
            if c.shop_id == shop_id and c.campaign_type.value == campaign_type
        }
        if not matching_campaign_ids:
            return set()
        since_aware = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        out: set[UUID] = set()
        for m in self.messages.values():
            if m.shop_id != shop_id or m.campaign_id not in matching_campaign_ids:
                continue
            if m.channel not in channel_set or m.sent_at is None:
                continue
            sent = m.sent_at if m.sent_at.tzinfo else m.sent_at.replace(tzinfo=timezone.utc)
            if sent >= since_aware:
                out.add(m.customer_id)
        return out

    async def delete_message(self, shop_id: UUID, message_id: UUID) -> bool:
        m = self.messages.get(message_id)
        if m is None or m.shop_id != shop_id:
            return False
        del self.messages[message_id]
        for qid in [
            qid
            for qid, q in self.queue.items()
            if q.message_id == message_id and q.shop_id == shop_id
        ]:
            del self.queue[qid]
        return True

    async def delete_messages(self, shop_id: UUID, message_ids: list[UUID]) -> int:
        id_set = set(message_ids)
        if not id_set:
            return 0
        deleted = 0
        for mid in list(id_set):
            m = self.messages.get(mid)
            if m is None or m.shop_id != shop_id:
                continue
            del self.messages[mid]
            deleted += 1
        for qid in [
            qid
            for qid, q in self.queue.items()
            if q.shop_id == shop_id and q.message_id in id_set
        ]:
            del self.queue[qid]
        return deleted

    async def delete_all_messages(self, shop_id: UUID) -> int:
        ids = [mid for mid, m in self.messages.items() if m.shop_id == shop_id]
        for mid in ids:
            del self.messages[mid]
        for qid in [qid for qid, q in self.queue.items() if q.shop_id == shop_id]:
            del self.queue[qid]
        return len(ids)

    async def enqueue(self, item: QueueItem) -> QueueItem:
        if item.created_at is None:
            item.created_at = datetime.now(timezone.utc)
        self.queue[item.id] = item
        return item

    async def list_due_queue(
        self,
        *,
        now: datetime,
        limit: int = 100,
        shop_id: UUID | None = None,
        campaign_id: UUID | None = None,
    ) -> list[QueueItem]:
        items = [
            q
            for q in self.queue.values()
            if q.state == QueueItemState.PENDING and q.run_at <= now
        ]
        if shop_id is not None:
            items = [q for q in items if q.shop_id == shop_id]
        if campaign_id is not None:
            items = [q for q in items if q.campaign_id == campaign_id]
        items.sort(key=lambda q: q.run_at)
        return items[:limit]

    async def save_queue_item(self, item: QueueItem) -> QueueItem:
        self.queue[item.id] = item
        return item

    async def force_campaign_queue_due(
        self, shop_id: UUID, campaign_id: UUID, *, now: datetime
    ) -> int:
        updated = 0
        for item in self.queue.values():
            if (
                item.shop_id == shop_id
                and item.campaign_id == campaign_id
                and item.state == QueueItemState.PENDING
            ):
                item.run_at = now
                updated += 1
        return updated

    async def add_log(self, log: MarketingLog) -> MarketingLog:
        if log.created_at is None:
            log.created_at = datetime.now(timezone.utc)
        self.logs.append(log)
        return log

    async def list_logs(
        self, shop_id: UUID, *, campaign_id: UUID | None = None, limit: int = 100
    ) -> list[MarketingLog]:
        items = [l for l in self.logs if l.shop_id == shop_id]
        if campaign_id:
            items = [l for l in items if l.campaign_id == campaign_id]
        items.sort(key=lambda l: l.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[:limit]


def demo_audience() -> list[AudienceMember]:
    return [
        AudienceMember(
            customer_id=uuid4(),
            name="Alex Rivera",
            phone="+15550100",
            email="alex@example.com",
            metadata={
                "vehicle": "2016 Honda Accord",
                "service": "oil change",
                "shop": "Apex Auto",
                "is_demo": True,
            },
        ),
        AudienceMember(
            customer_id=uuid4(),
            name="Jordan Lee",
            phone="+15550101",
            email="jordan@example.com",
            preferred_channel=Channel.EMAIL,
            metadata={
                "vehicle": "2019 Toyota Corolla",
                "service": "brakes",
                "shop": "Apex Auto",
                "is_demo": True,
            },
        ),
        AudienceMember(
            customer_id=uuid4(),
            name="Sam Chen",
            phone="+15550102",
            metadata={
                "vehicle": "2014 Ford Fusion",
                "service": "battery",
                "shop": "Apex Auto",
                "is_demo": True,
            },
        ),
    ]


_DEMO_PHONES = frozenset({"+15550100", "+15550101", "+15550102", "15550100", "15550101", "15550102"})
_DEMO_EMAILS = frozenset({"alex@example.com", "jordan@example.com", "sam@example.com"})


def is_demo_member(member: AudienceMember) -> bool:
    """Identify synthetic demo_audience() contacts (not CRM-imported shop data)."""
    meta = member.metadata or {}
    if meta.get("is_demo") is True:
        return True
    # Legacy fingerprints for campaigns saved before is_demo metadata existed.
    phone = (member.phone or "").replace("-", "").replace(" ", "")
    email = (member.email or "").lower()
    if phone in _DEMO_PHONES or phone.lstrip("+") in _DEMO_PHONES:
        return True
    if email in _DEMO_EMAILS:
        return True
    return False


def is_demo_campaign(campaign: Campaign) -> bool:
    if not campaign.audience:
        return False
    return all(is_demo_member(m) for m in campaign.audience)


def compute_metrics(shop_id: UUID, campaign_id: UUID, messages: list[CampaignMessage]) -> CampaignMetrics:
    from decimal import Decimal

    sent = sum(
        1
        for m in messages
        if m.sent_at
        or m.status
        in {
            MessageStatus.SENT,
            MessageStatus.DELIVERED,
            MessageStatus.OPENED,
            MessageStatus.CLICKED,
            MessageStatus.REPLIED,
        }
    )
    opened = sum(1 for m in messages if m.opened_at or m.status in {MessageStatus.OPENED, MessageStatus.CLICKED, MessageStatus.REPLIED})
    clicked = sum(1 for m in messages if m.clicked_at or m.status in {MessageStatus.CLICKED, MessageStatus.REPLIED})
    replied = sum(1 for m in messages if m.replied_at or m.status == MessageStatus.REPLIED)
    appointments = sum(1 for m in messages if m.appointment_id)
    failed = sum(1 for m in messages if m.status == MessageStatus.FAILED)
    revenue = sum((m.revenue for m in messages), Decimal("0"))
    # Cost heuristic by channel
    cost = Decimal("0")
    for m in messages:
        if not m.sent_at and m.status not in {MessageStatus.SENT, MessageStatus.DELIVERED, MessageStatus.OPENED, MessageStatus.CLICKED, MessageStatus.REPLIED}:
            continue
        if m.channel == Channel.SMS:
            cost += Decimal("0.02")
        elif m.channel == Channel.EMAIL:
            cost += Decimal("0.005")
        else:
            cost += Decimal("0.08")
    def rate(n: int, d: int) -> float:
        return round(n / d, 4) if d else 0.0

    roi = round(float(revenue - cost) / float(cost), 2) if cost > 0 else 0.0
    return CampaignMetrics(
        campaign_id=campaign_id,
        shop_id=shop_id,
        sent=sent,
        delivered=sent,
        opened=opened,
        clicked=clicked,
        replied=replied,
        appointments=appointments,
        failed=failed,
        revenue=revenue.quantize(Decimal("0.01")),
        cost=cost.quantize(Decimal("0.01")),
        open_rate=rate(opened, sent),
        click_rate=rate(clicked, sent),
        reply_rate=rate(replied, sent),
        appointment_rate=rate(appointments, sent),
        roi=roi,
    )
