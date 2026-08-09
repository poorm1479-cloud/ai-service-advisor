"""Voice domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class VoiceCall:
    id: UUID
    shop_id: UUID
    caller_phone: str
    called_phone: str
    status: str = "ringing"
    customer_id: UUID | None = None
    twilio_call_sid: str | None = None
    recording_sid: str | None = None
    recording_url: str | None = None
    recording_duration_sec: int | None = None
    last_intent: str | None = None
    transcript: str | None = None
    call_summary: str | None = None
    repair_notes: dict[str, Any] | None = None
    owner_summary: str | None = None
    escalate: bool = False
    escalation_reason: str | None = None
    human_takeover: bool = False
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VoiceTurn:
    id: UUID
    call_id: UUID
    shop_id: UUID
    role: str
    text: str
    intent: str | None = None
    interrupted: bool = False
    audio_url: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class InboundCallEvent:
    call_sid: str
    from_number: str
    to_number: str
    call_status: str | None = None
    direction: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SpeechInput:
    call_sid: str
    speech_result: str
    confidence: float | None = None
    interrupted: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StreamChunk:
    call_sid: str
    stream_sid: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    sequence_number: int | None = None
    shop_id: UUID | None = None
    to_number: str | None = None
