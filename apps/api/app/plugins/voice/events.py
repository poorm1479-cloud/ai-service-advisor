"""Voice plugin domain events — communication layer only (not Workflow DomainEventType)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass(slots=True)
class IncomingCallEvent:
    event_id: UUID = field(default_factory=uuid4)
    event_type: str = "voice.incoming_call"
    shop_id: UUID | None = None
    call_sid: str = ""
    from_number: str = ""
    to_number: str = ""
    session_id: UUID | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConversationStartedEvent:
    event_id: UUID = field(default_factory=uuid4)
    event_type: str = "voice.conversation_started"
    shop_id: UUID | None = None
    session_id: UUID | None = None
    conversation_id: UUID | None = None
    caller_phone: str = ""
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VoiceMessageEvent:
    event_id: UUID = field(default_factory=uuid4)
    event_type: str = "voice.voice_message"
    shop_id: UUID | None = None
    session_id: UUID | None = None
    conversation_id: UUID | None = None
    role: str = "caller"
    text: str = ""
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HumanEscalationEvent:
    event_id: UUID = field(default_factory=uuid4)
    event_type: str = "voice.human_escalation"
    shop_id: UUID | None = None
    session_id: UUID | None = None
    conversation_id: UUID | None = None
    reason: str = ""
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CallCompletedEvent:
    event_id: UUID = field(default_factory=uuid4)
    event_type: str = "voice.call_completed"
    shop_id: UUID | None = None
    session_id: UUID | None = None
    conversation_id: UUID | None = None
    duration_sec: float | None = None
    resolved_by_ai: bool = False
    transferred: bool = False
    appointment_converted: bool = False
    satisfaction: float | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = field(default_factory=dict)


VoiceEvent = (
    IncomingCallEvent
    | ConversationStartedEvent
    | VoiceMessageEvent
    | HumanEscalationEvent
    | CallCompletedEvent
)
