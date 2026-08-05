"""SMS domain models — conversations, messages, jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class SmsMessage:
    id: UUID
    conversation_id: UUID
    shop_id: UUID
    direction: str
    body: str
    twilio_sid: str | None = None
    intent: str | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SmsConversation:
    id: UUID
    shop_id: UUID
    customer_phone: str
    customer_id: UUID | None = None
    status: str = "active"
    subject: str | None = None
    last_intent: str | None = None
    owner_summary: str | None = None
    reply_preview: str | None = None
    escalate: bool = False
    escalation_reason: str | None = None
    human_takeover: bool = False
    last_message_at: datetime | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConversationTurn:
    """One turn in conversation memory."""

    role: str  # customer | assistant | system
    content: str
    intent: str | None = None
    at: datetime | None = None


@dataclass(slots=True)
class InboundSms:
    from_number: str
    to_number: str
    body: str
    message_sid: str | None = None
    account_sid: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OutboundSms:
    to_number: str
    from_number: str
    body: str
    conversation_id: UUID | None = None


@dataclass(slots=True)
class SmsJob:
    id: UUID
    shop_id: UUID | None
    payload: dict[str, Any]
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    created_at: datetime | None = None
