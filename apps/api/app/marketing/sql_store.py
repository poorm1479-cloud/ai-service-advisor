"""SQLAlchemy marketing store — durable campaigns, messages, queue, logs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    delete,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base, SessionLocal
from app.marketing.enums import CampaignStatus, CampaignType, Channel, MessageStatus, QueueItemState
from app.marketing.models import (
    AiPlan,
    AudienceMember,
    Campaign,
    CampaignMessage,
    MarketingLog,
    QueueItem,
)


class MarketingCampaignModel(Base):
    __tablename__ = "marketing_campaigns"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    channels_json: Mapped[str | None] = mapped_column(Text)
    audience_json: Mapped[str | None] = mapped_column(Text)
    custom_message: Mapped[str | None] = mapped_column(Text)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_defaults_json: Mapped[str | None] = mapped_column(Text)
    max_sends_per_customer_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    budget: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    expected_revenue: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    tags_json: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketingMessageModel(Base):
    __tablename__ = "marketing_messages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    campaign_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    appointment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    provider_id: Mapped[str | None] = mapped_column(String(128))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    ai_plan_json: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketingQueueModel(Base):
    __tablename__ = "marketing_queue"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketingLogModel(Base):
    __tablename__ = "marketing_logs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    campaign_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    message_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _channel_list(raw: Any) -> list[Channel]:
    if not isinstance(raw, list):
        return [Channel.SMS, Channel.EMAIL]
    out: list[Channel] = []
    for item in raw:
        try:
            out.append(Channel(str(item)))
        except ValueError:
            continue
    return out or [Channel.SMS, Channel.EMAIL]


def _audience_list(raw: Any) -> list[AudienceMember]:
    if not isinstance(raw, list):
        return []
    members: list[AudienceMember] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            preferred = item.get("preferred_channel")
            members.append(
                AudienceMember(
                    customer_id=UUID(str(item["customer_id"]))
                    if item.get("customer_id")
                    else uuid4(),
                    name=str(item.get("name") or "Customer"),
                    phone=item.get("phone"),
                    email=item.get("email"),
                    preferred_channel=Channel(preferred) if preferred else None,
                    timezone=str(item.get("timezone") or "America/Los_Angeles"),
                    metadata=dict(item.get("metadata") or {}),
                )
            )
        except (TypeError, ValueError, KeyError):
            continue
    return members


def _ai_plan(raw: Any) -> AiPlan | None:
    if not isinstance(raw, dict) or not raw.get("message"):
        return None
    try:
        send_at = raw.get("send_at")
        if isinstance(send_at, str):
            send_at = datetime.fromisoformat(send_at.replace("Z", "+00:00"))
        if not isinstance(send_at, datetime):
            send_at = datetime.now(timezone.utc)
        return AiPlan(
            channel=Channel(str(raw.get("channel") or Channel.SMS.value)),
            send_at=send_at,
            message=str(raw["message"]),
            subject=raw.get("subject"),
            frequency_days=int(raw.get("frequency_days") or 30),
            confidence=float(raw.get("confidence") or 0.7),
            reasons=list(raw.get("reasons") or []),
        )
    except (TypeError, ValueError, KeyError):
        return None


def _ai_plan_to_dict(plan: AiPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "channel": plan.channel.value,
        "send_at": plan.send_at.isoformat(),
        "message": plan.message,
        "subject": plan.subject,
        "frequency_days": plan.frequency_days,
        "confidence": plan.confidence,
        "reasons": plan.reasons,
    }


def _audience_to_dicts(members: list[AudienceMember]) -> list[dict[str, Any]]:
    return [
        {
            "customer_id": str(m.customer_id),
            "name": m.name,
            "phone": m.phone,
            "email": m.email,
            "preferred_channel": m.preferred_channel.value if m.preferred_channel else None,
            "timezone": m.timezone,
            "metadata": m.metadata,
        }
        for m in members
    ]


def _campaign(row: MarketingCampaignModel) -> Campaign:
    return Campaign(
        id=row.id,
        shop_id=row.shop_id,
        name=row.name,
        campaign_type=CampaignType(row.campaign_type),
        status=CampaignStatus(row.status),
        channels_allowed=_channel_list(_json_loads(row.channels_json, [])),
        audience=_audience_list(_json_loads(row.audience_json, [])),
        custom_message=row.custom_message,
        scheduled_start=row.scheduled_start,
        scheduled_end=row.scheduled_end,
        ai_defaults=_ai_plan(_json_loads(row.ai_defaults_json, None)),
        max_sends_per_customer_days=row.max_sends_per_customer_days,
        budget=Decimal(str(row.budget or 0)),
        expected_revenue=Decimal(str(row.expected_revenue or 0)),
        tags=list(_json_loads(row.tags_json, []) or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata=dict(_json_loads(row.metadata_json, {}) or {}),
    )


def _message(row: MarketingMessageModel) -> CampaignMessage:
    return CampaignMessage(
        id=row.id,
        shop_id=row.shop_id,
        campaign_id=row.campaign_id,
        customer_id=row.customer_id,
        channel=Channel(row.channel),
        status=MessageStatus(row.status),
        body=row.body or "",
        subject=row.subject,
        scheduled_at=row.scheduled_at,
        sent_at=row.sent_at,
        opened_at=row.opened_at,
        clicked_at=row.clicked_at,
        replied_at=row.replied_at,
        appointment_id=row.appointment_id,
        revenue=Decimal(str(row.revenue or 0)),
        provider_id=row.provider_id,
        attempt=row.attempt or 0,
        error=row.error,
        ai_plan=_ai_plan(_json_loads(row.ai_plan_json, None)),
        created_at=row.created_at,
        metadata=dict(_json_loads(row.metadata_json, {}) or {}),
    )


def _queue(row: MarketingQueueModel) -> QueueItem:
    return QueueItem(
        id=row.id,
        shop_id=row.shop_id,
        message_id=row.message_id,
        campaign_id=row.campaign_id,
        run_at=row.run_at,
        state=QueueItemState(row.state),
        attempt=row.attempt or 0,
        max_attempts=row.max_attempts or 3,
        last_error=row.last_error,
        created_at=row.created_at,
    )


def _log(row: MarketingLogModel) -> MarketingLog:
    return MarketingLog(
        id=row.id,
        shop_id=row.shop_id,
        campaign_id=row.campaign_id,
        message_id=row.message_id,
        level=row.level,
        event=row.event,
        detail=row.detail or "",
        created_at=row.created_at,
    )


class SqlAlchemyMarketingStore:
    """Session-per-operation store so the singleton marketing runtime stays durable."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or SessionLocal

    async def _set_shop(self, session: AsyncSession, shop_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )

    async def save_campaign(self, campaign: Campaign) -> Campaign:
        now = datetime.now(timezone.utc)
        if campaign.created_at is None:
            campaign.created_at = now
        campaign.updated_at = now
        async with self._session_factory() as session:
            await self._set_shop(session, campaign.shop_id)
            row = await session.get(MarketingCampaignModel, campaign.id)
            if row is None:
                row = MarketingCampaignModel(id=campaign.id, shop_id=campaign.shop_id)
                session.add(row)
            row.name = campaign.name
            row.campaign_type = campaign.campaign_type.value
            row.status = campaign.status.value
            row.channels_json = _json_dumps([c.value for c in campaign.channels_allowed])
            row.audience_json = _json_dumps(_audience_to_dicts(campaign.audience))
            row.custom_message = campaign.custom_message
            row.scheduled_start = campaign.scheduled_start
            row.scheduled_end = campaign.scheduled_end
            row.ai_defaults_json = _json_dumps(_ai_plan_to_dict(campaign.ai_defaults))
            row.max_sends_per_customer_days = campaign.max_sends_per_customer_days
            row.budget = campaign.budget
            row.expected_revenue = campaign.expected_revenue
            row.tags_json = _json_dumps(campaign.tags)
            row.metadata_json = _json_dumps(campaign.metadata)
            row.created_at = campaign.created_at or now
            row.updated_at = campaign.updated_at or now
            await session.commit()
        return campaign

    async def get_campaign(self, shop_id: UUID, campaign_id: UUID) -> Campaign | None:
        async with self._session_factory() as session:
            await self._set_shop(session, shop_id)
            row = await session.scalar(
                select(MarketingCampaignModel).where(
                    MarketingCampaignModel.id == campaign_id,
                    MarketingCampaignModel.shop_id == shop_id,
                )
            )
            return _campaign(row) if row else None

    async def list_campaigns(
        self, shop_id: UUID, *, status: CampaignStatus | None = None
    ) -> list[Campaign]:
        async with self._session_factory() as session:
            await self._set_shop(session, shop_id)
            stmt = select(MarketingCampaignModel).where(MarketingCampaignModel.shop_id == shop_id)
            if status:
                stmt = stmt.where(MarketingCampaignModel.status == status.value)
            stmt = stmt.order_by(MarketingCampaignModel.created_at.desc())
            rows = (await session.scalars(stmt)).all()
            return [_campaign(r) for r in rows]

    async def save_message(self, message: CampaignMessage) -> CampaignMessage:
        if message.created_at is None:
            message.created_at = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            await self._set_shop(session, message.shop_id)
            row = await session.get(MarketingMessageModel, message.id)
            if row is None:
                row = MarketingMessageModel(
                    id=message.id,
                    shop_id=message.shop_id,
                    campaign_id=message.campaign_id,
                    customer_id=message.customer_id,
                )
                session.add(row)
            row.channel = message.channel.value
            row.status = message.status.value
            row.body = message.body
            row.subject = message.subject
            row.scheduled_at = message.scheduled_at
            row.sent_at = message.sent_at
            row.opened_at = message.opened_at
            row.clicked_at = message.clicked_at
            row.replied_at = message.replied_at
            row.appointment_id = message.appointment_id
            row.revenue = message.revenue
            row.provider_id = message.provider_id
            row.attempt = message.attempt
            row.error = message.error
            row.ai_plan_json = _json_dumps(_ai_plan_to_dict(message.ai_plan))
            row.metadata_json = _json_dumps(message.metadata)
            row.created_at = message.created_at
            await session.commit()
        return message

    async def get_message(self, shop_id: UUID, message_id: UUID) -> CampaignMessage | None:
        async with self._session_factory() as session:
            await self._set_shop(session, shop_id)
            row = await session.scalar(
                select(MarketingMessageModel).where(
                    MarketingMessageModel.id == message_id,
                    MarketingMessageModel.shop_id == shop_id,
                )
            )
            return _message(row) if row else None

    async def list_messages(
        self, shop_id: UUID, campaign_id: UUID, *, limit: int = 500
    ) -> list[CampaignMessage]:
        async with self._session_factory() as session:
            await self._set_shop(session, shop_id)
            rows = (
                await session.scalars(
                    select(MarketingMessageModel)
                    .where(
                        MarketingMessageModel.shop_id == shop_id,
                        MarketingMessageModel.campaign_id == campaign_id,
                    )
                    .order_by(MarketingMessageModel.created_at.asc())
                    .limit(limit)
                )
            ).all()
            return [_message(r) for r in rows]

    async def recently_contacted_customer_ids(
        self,
        shop_id: UUID,
        *,
        campaign_type: str,
        channels: list[Channel],
        since: datetime,
    ) -> set[UUID]:
        if not channels:
            return set()
        channel_values = [c.value if isinstance(c, Channel) else str(c) for c in channels]
        since_aware = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        async with self._session_factory() as session:
            await self._set_shop(session, shop_id)
            rows = (
                await session.execute(
                    select(MarketingMessageModel.customer_id)
                    .join(
                        MarketingCampaignModel,
                        MarketingCampaignModel.id == MarketingMessageModel.campaign_id,
                    )
                    .where(
                        MarketingMessageModel.shop_id == shop_id,
                        MarketingCampaignModel.shop_id == shop_id,
                        MarketingCampaignModel.campaign_type == campaign_type,
                        MarketingMessageModel.channel.in_(channel_values),
                        MarketingMessageModel.sent_at.is_not(None),
                        MarketingMessageModel.sent_at >= since_aware,
                    )
                    .distinct()
                )
            ).all()
            return {row[0] for row in rows}

    async def delete_message(self, shop_id: UUID, message_id: UUID) -> bool:
        async with self._session_factory() as session:
            await self._set_shop(session, shop_id)
            row = await session.scalar(
                select(MarketingMessageModel).where(
                    MarketingMessageModel.id == message_id,
                    MarketingMessageModel.shop_id == shop_id,
                )
            )
            if row is None:
                return False
            await session.execute(
                delete(MarketingQueueModel).where(
                    MarketingQueueModel.shop_id == shop_id,
                    MarketingQueueModel.message_id == message_id,
                )
            )
            await session.delete(row)
            await session.commit()
            return True

    async def delete_messages(self, shop_id: UUID, message_ids: list[UUID]) -> int:
        if not message_ids:
            return 0
        async with self._session_factory() as session:
            await self._set_shop(session, shop_id)
            count = await session.scalar(
                select(func.count())
                .select_from(MarketingMessageModel)
                .where(
                    MarketingMessageModel.shop_id == shop_id,
                    MarketingMessageModel.id.in_(message_ids),
                )
            )
            await session.execute(
                delete(MarketingQueueModel).where(
                    MarketingQueueModel.shop_id == shop_id,
                    MarketingQueueModel.message_id.in_(message_ids),
                )
            )
            await session.execute(
                delete(MarketingMessageModel).where(
                    MarketingMessageModel.shop_id == shop_id,
                    MarketingMessageModel.id.in_(message_ids),
                )
            )
            await session.commit()
            return int(count or 0)

    async def delete_all_messages(self, shop_id: UUID) -> int:
        async with self._session_factory() as session:
            await self._set_shop(session, shop_id)
            count = await session.scalar(
                select(func.count())
                .select_from(MarketingMessageModel)
                .where(MarketingMessageModel.shop_id == shop_id)
            )
            await session.execute(
                delete(MarketingQueueModel).where(MarketingQueueModel.shop_id == shop_id)
            )
            await session.execute(
                delete(MarketingMessageModel).where(MarketingMessageModel.shop_id == shop_id)
            )
            await session.commit()
            return int(count or 0)

    async def enqueue(self, item: QueueItem) -> QueueItem:
        if item.created_at is None:
            item.created_at = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            await self._set_shop(session, item.shop_id)
            row = await session.get(MarketingQueueModel, item.id)
            if row is None:
                row = MarketingQueueModel(
                    id=item.id,
                    shop_id=item.shop_id,
                    message_id=item.message_id,
                    campaign_id=item.campaign_id,
                )
                session.add(row)
            row.run_at = item.run_at
            row.state = item.state.value
            row.attempt = item.attempt
            row.max_attempts = item.max_attempts
            row.last_error = item.last_error
            row.created_at = item.created_at
            await session.commit()
        return item

    async def list_due_queue(
        self,
        *,
        now: datetime,
        limit: int = 100,
        shop_id: UUID | None = None,
        campaign_id: UUID | None = None,
    ) -> list[QueueItem]:
        async with self._session_factory() as session:
            if shop_id is not None:
                await self._set_shop(session, shop_id)
            else:
                # Cross-shop drain (admin/worker): RLS requires a shop context otherwise.
                await session.execute(text("SELECT set_config('app.shop_id', '', true)"))
            stmt = select(MarketingQueueModel).where(
                MarketingQueueModel.state == QueueItemState.PENDING.value,
                MarketingQueueModel.run_at <= now,
            )
            if shop_id is not None:
                stmt = stmt.where(MarketingQueueModel.shop_id == shop_id)
            if campaign_id is not None:
                stmt = stmt.where(MarketingQueueModel.campaign_id == campaign_id)
            stmt = stmt.order_by(MarketingQueueModel.run_at.asc()).limit(limit)
            if shop_id is None:
                # Prefer bypassing RLS for system-wide queue processing when available.
                try:
                    await session.execute(text("SET LOCAL row_security = off"))
                except Exception:  # noqa: BLE001
                    pass
            rows = (await session.scalars(stmt)).all()
            return [_queue(r) for r in rows]

    async def save_queue_item(self, item: QueueItem) -> QueueItem:
        async with self._session_factory() as session:
            await self._set_shop(session, item.shop_id)
            row = await session.get(MarketingQueueModel, item.id)
            if row is None:
                return await self.enqueue(item)
            row.run_at = item.run_at
            row.state = item.state.value
            row.attempt = item.attempt
            row.max_attempts = item.max_attempts
            row.last_error = item.last_error
            await session.commit()
        return item

    async def force_campaign_queue_due(
        self, shop_id: UUID, campaign_id: UUID, *, now: datetime
    ) -> int:
        async with self._session_factory() as session:
            await self._set_shop(session, shop_id)
            result = await session.execute(
                update(MarketingQueueModel)
                .where(
                    MarketingQueueModel.shop_id == shop_id,
                    MarketingQueueModel.campaign_id == campaign_id,
                    MarketingQueueModel.state == QueueItemState.PENDING.value,
                )
                .values(run_at=now)
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def add_log(self, log: MarketingLog) -> MarketingLog:
        if log.created_at is None:
            log.created_at = datetime.now(timezone.utc)
        if log.shop_id is None:
            return log
        async with self._session_factory() as session:
            await self._set_shop(session, log.shop_id)
            session.add(
                MarketingLogModel(
                    id=log.id,
                    shop_id=log.shop_id,
                    campaign_id=log.campaign_id,
                    message_id=log.message_id,
                    level=log.level,
                    event=log.event,
                    detail=log.detail,
                    created_at=log.created_at,
                )
            )
            await session.commit()
        return log

    async def list_logs(
        self, shop_id: UUID, *, campaign_id: UUID | None = None, limit: int = 100
    ) -> list[MarketingLog]:
        async with self._session_factory() as session:
            await self._set_shop(session, shop_id)
            stmt = select(MarketingLogModel).where(MarketingLogModel.shop_id == shop_id)
            if campaign_id:
                stmt = stmt.where(MarketingLogModel.campaign_id == campaign_id)
            stmt = stmt.order_by(MarketingLogModel.created_at.desc()).limit(limit)
            rows = (await session.scalars(stmt)).all()
            return [_log(r) for r in rows]
