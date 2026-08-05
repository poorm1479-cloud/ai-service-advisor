"""Marketing agent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class MarketingActionType(str, Enum):
    SMS_CAMPAIGN = "sms_campaign"
    EMAIL_CAMPAIGN = "email_campaign"
    REVIEW_REQUEST = "review_request"
    THANK_YOU = "thank_you"
    MAINTENANCE_REMINDER = "maintenance_reminder"


@dataclass(slots=True)
class MarketingRequest:
    action_type: MarketingActionType
    customer_id: UUID | None = None
    channel: str = "sms"
    template: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    scheduled_at: datetime | None = None


@dataclass(slots=True)
class MarketingActionResult:
    action_type: str
    channel: str
    customer_id: UUID | None
    template: str
    body: str
    scheduled_at: datetime | None
    dispatched: bool
    payload: dict[str, Any] = field(default_factory=dict)
    # AI Decision Layer — proposed dispatch; Workflow executes it
    decision: Any | None = None
