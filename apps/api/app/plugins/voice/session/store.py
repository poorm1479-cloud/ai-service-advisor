"""Voice session models and in-memory store."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4


@dataclass(slots=True)
class VoiceTurnRecord:
    id: UUID = field(default_factory=uuid4)
    role: Literal["caller", "assistant", "system"] = "caller"
    text: str = ""
    audio_url: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VoiceSession:
    id: UUID = field(default_factory=uuid4)
    shop_id: UUID | None = None
    call_sid: str = ""
    from_number: str = ""
    to_number: str = ""
    status: Literal["ringing", "active", "on_hold", "transferred", "completed"] = "ringing"
    conversation_id: UUID | None = None
    customer_id: UUID | None = None
    turns: list[VoiceTurnRecord] = field(default_factory=list)
    recording_url: str | None = None
    recording_sid: str | None = None
    human_takeover: bool = False
    escalation_reason: str | None = None
    resolved_by_ai: bool = False
    appointment_converted: bool = False
    satisfaction: float | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class VoiceSessionStore:
    def __init__(self) -> None:
        self._by_id: dict[UUID, VoiceSession] = {}
        self._by_sid: dict[str, UUID] = {}

    def save(self, session: VoiceSession) -> VoiceSession:
        self._by_id[session.id] = session
        if session.call_sid:
            self._by_sid[session.call_sid] = session.id
        return session

    def get(self, session_id: UUID) -> VoiceSession | None:
        return self._by_id.get(session_id)

    def get_by_sid(self, call_sid: str) -> VoiceSession | None:
        sid = self._by_sid.get(call_sid)
        return self._by_id.get(sid) if sid else None

    def list_for_shop(self, shop_id: UUID, *, limit: int = 50) -> list[VoiceSession]:
        items = [s for s in self._by_id.values() if s.shop_id == shop_id]
        items.sort(key=lambda s: s.started_at, reverse=True)
        return items[:limit]

    def clear(self) -> None:
        self._by_id.clear()
        self._by_sid.clear()
