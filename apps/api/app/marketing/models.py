"""Marketing automation domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.marketing.enums import (
    CampaignStatus,
    CampaignType,
    Channel,
    MessageStatus,
    QueueItemState,
)


@dataclass(slots=True)
class AudienceMember:
    customer_id: UUID
    name: str
    phone: str | None = None
    email: str | None = None
    preferred_channel: Channel | None = None
    timezone: str = "America/Los_Angeles"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AiPlan:
    """AI-chosen send strategy for a recipient or campaign default."""

    channel: Channel
    send_at: datetime
    message: str
    subject: str | None = None
    frequency_days: int = 30
    confidence: float = 0.7
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Campaign:
    id: UUID
    shop_id: UUID
    name: str
    campaign_type: CampaignType
    status: CampaignStatus = CampaignStatus.DRAFT
    channels_allowed: list[Channel] = field(default_factory=lambda: [Channel.SMS, Channel.EMAIL])
    audience: list[AudienceMember] = field(default_factory=list)
    template_key: str | None = None
    custom_message: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    ai_defaults: AiPlan | None = None
    max_sends_per_customer_days: int = 14
    budget: Decimal = Decimal("0")
    expected_revenue: Decimal = Decimal("0")
    tags: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CampaignMessage:
    id: UUID
    shop_id: UUID
    campaign_id: UUID
    customer_id: UUID
    channel: Channel
    status: MessageStatus = MessageStatus.QUEUED
    body: str = ""
    subject: str | None = None
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    clicked_at: datetime | None = None
    replied_at: datetime | None = None
    appointment_id: UUID | None = None
    revenue: Decimal = Decimal("0")
    provider_id: str | None = None
    attempt: int = 0
    error: str | None = None
    ai_plan: AiPlan | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QueueItem:
    id: UUID
    shop_id: UUID
    message_id: UUID
    campaign_id: UUID
    run_at: datetime
    state: QueueItemState = QueueItemState.PENDING
    attempt: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class CampaignMetrics:
    campaign_id: UUID
    shop_id: UUID
    sent: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    replied: int = 0
    appointments: int = 0
    failed: int = 0
    revenue: Decimal = Decimal("0")
    cost: Decimal = Decimal("0")
    open_rate: float = 0.0
    click_rate: float = 0.0
    reply_rate: float = 0.0
    appointment_rate: float = 0.0
    roi: float = 0.0


@dataclass(slots=True)
class CalendarEvent:
    campaign_id: UUID
    name: str
    campaign_type: CampaignType
    status: CampaignStatus
    day: date
    channel: Channel | None = None
    message_count: int = 0


@dataclass(slots=True)
class MarketingLog:
    id: UUID = field(default_factory=uuid4)
    shop_id: UUID | None = None
    campaign_id: UUID | None = None
    message_id: UUID | None = None
    level: str = "info"
    event: str = ""
    detail: str = ""
    created_at: datetime | None = None
