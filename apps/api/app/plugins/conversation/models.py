"""Conversation domain models — unified aggregate across channels."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class ConversationStatus(StrEnum):
    OPEN = "open"
    ACTIVE = "active"
    WAITING = "waiting"
    ESCALATED = "escalated"
    CLOSED = "closed"
    MERGED = "merged"


class ConversationChannel(StrEnum):
    PHONE = "phone"
    SMS = "sms"
    EMAIL = "email"
    FACEBOOK = "facebook"
    WEBSITE_CHAT = "website_chat"
    WALK_IN = "walk_in"
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    GOOGLE_BUSINESS = "google_business"
    UNKNOWN = "unknown"


class ParticipantRole(StrEnum):
    CUSTOMER = "customer"
    SHOP = "shop"
    AI_ASSISTANT = "ai_assistant"
    MECHANIC = "mechanic"
    MANAGER = "manager"
    ADVISOR = "advisor"


@dataclass(slots=True)
class Participant:
    role: str
    identifier: str | None = None
    display_name: str | None = None
    customer_id: UUID | None = None
    user_id: UUID | None = None


@dataclass(slots=True)
class ConversationAttachment:
    id: UUID = field(default_factory=uuid4)
    url: str | None = None
    content_type: str | None = None
    filename: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConversationMessage:
    """Unified message inside a Conversation."""

    id: UUID
    conversation_id: UUID
    shop_id: UUID
    sender: str
    receiver: str | None
    channel: str
    content: str
    timestamp: datetime
    attachments: list[ConversationAttachment] = field(default_factory=list)
    ai_summary: str | None = None
    intent: str | None = None
    language: str | None = None
    confidence: float | None = None
    direction: str = "inbound"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConversationEvent:
    id: UUID = field(default_factory=uuid4)
    kind: str = "note"
    summary: str = ""
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConversationAiInsights:
    """AI enrichment attached to a Conversation (decide layer → Workflow update)."""

    summary: str | None = None
    intent: str | None = None
    sentiment: str | None = None
    urgency_score: float = 0.0
    suggested_reply: str | None = None
    suggested_service: str | None = None
    suggested_appointment: str | None = None
    risk_score: float = 0.0
    revenue_opportunity: float = 0.0
    confidence: float = 0.0
    highlights: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Conversation:
    """Conversation aggregate — Workflow operates on ConversationId."""

    id: UUID
    shop_id: UUID
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    status: str = ConversationStatus.OPEN.value
    current_workflow: str | None = None
    assigned_advisor: str | None = None
    priority: str = "normal"
    channel: str = ConversationChannel.UNKNOWN.value
    external_key: str | None = None  # phone / email / fb psid / walk-in id
    channel_history: list[str] = field(default_factory=list)
    participants: list[Participant] = field(default_factory=list)
    messages: list[ConversationMessage] = field(default_factory=list)
    timeline: list[ConversationEvent] = field(default_factory=list)
    attachments: list[ConversationAttachment] = field(default_factory=list)
    ai_decisions: list[dict[str, Any]] = field(default_factory=list)
    workflow_history: list[dict[str, Any]] = field(default_factory=list)
    events: list[ConversationEvent] = field(default_factory=list)
    ai: ConversationAiInsights = field(default_factory=ConversationAiInsights)
    merged_into: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
