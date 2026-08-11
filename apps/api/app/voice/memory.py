"""Per-call conversation memory with barge-in awareness."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from app.voice.models import VoiceTurn


@dataclass
class CallMemorySnapshot:
    shop_id: UUID
    call_id: UUID
    caller_phone: str
    turns: list[VoiceTurn] = field(default_factory=list)
    pending_question: str | None = None
    appointment_id: str | None = None
    slots_offered: list[dict] = field(default_factory=list)
    pending_service: str | None = None
    pending_service_id: str | None = None
    pending_duration_minutes: int | None = None
    pending_service_price: str | None = None
    pending_cancel: bool = False
    # "book" | "reschedule" | "cancel" — guides YES affirmations
    pending_action: str | None = None
    # Partial customer preference until day + clock are both known.
    pending_preferred_start: str | None = None
    pending_preferred_end: str | None = None
    pending_time_precision: str | None = None
    pending_needs_date: bool = False
    pending_needs_time: bool = False
    # Booked visit start (ISO) — anchor for "same time" after a service-type swap.
    active_visit_start: str | None = None
    interrupted: bool = False
    context_notes: list[str] = field(default_factory=list)

    def as_transcript(self) -> str:
        lines: list[str] = []
        for t in self.turns:
            tag = t.role.upper()
            intent = f" [{t.intent}]" if t.intent else ""
            barge = " (interrupted)" if t.interrupted else ""
            lines.append(f"{tag}{intent}{barge}: {t.text}")
        return "\n".join(lines)


class CallMemoryPort(Protocol):
    async def load(self, *, shop_id: UUID, call_id: UUID, caller_phone: str) -> CallMemorySnapshot: ...

    async def append(self, *, shop_id: UUID, call_id: UUID, turn: VoiceTurn) -> CallMemorySnapshot: ...

    async def mark_interrupted(self, *, shop_id: UUID, call_id: UUID) -> CallMemorySnapshot: ...

    async def update_state(
        self,
        *,
        shop_id: UUID,
        call_id: UUID,
        pending_question: str | None = None,
        appointment_id: str | None = None,
        slots_offered: list[dict] | None = None,
        pending_service: str | None = None,
        pending_service_id: str | None = None,
        pending_duration_minutes: int | None = None,
        pending_service_price: str | None = None,
        pending_cancel: bool | None = None,
        pending_action: str | None = None,
        pending_preferred_start: str | None = None,
        pending_preferred_end: str | None = None,
        pending_time_precision: str | None = None,
        pending_needs_date: bool | None = None,
        pending_needs_time: bool | None = None,
        active_visit_start: str | None = None,
        clear_pending_booking: bool = False,
        context_note: str | None = None,
    ) -> CallMemorySnapshot: ...


class InMemoryCallMemory:
    def __init__(self, *, max_turns: int = 200) -> None:
        self._data: dict[UUID, CallMemorySnapshot] = {}
        self._locks: dict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._max_turns = max_turns

    async def load(
        self, *, shop_id: UUID, call_id: UUID, caller_phone: str
    ) -> CallMemorySnapshot:
        async with self._locks[call_id]:
            snap = self._data.get(call_id)
            if snap is None:
                snap = CallMemorySnapshot(
                    shop_id=shop_id, call_id=call_id, caller_phone=caller_phone
                )
                self._data[call_id] = snap
            return snap

    async def append(
        self, *, shop_id: UUID, call_id: UUID, turn: VoiceTurn
    ) -> CallMemorySnapshot:
        async with self._locks[call_id]:
            snap = self._data.get(call_id) or CallMemorySnapshot(
                shop_id=shop_id,
                call_id=call_id,
                caller_phone="",
            )
            if turn.created_at is None:
                turn.created_at = datetime.now(timezone.utc)
            snap.turns.append(turn)
            if len(snap.turns) > self._max_turns:
                snap.turns = snap.turns[-self._max_turns :]
            snap.interrupted = False
            self._data[call_id] = snap
            return snap

    async def mark_interrupted(self, *, shop_id: UUID, call_id: UUID) -> CallMemorySnapshot:
        async with self._locks[call_id]:
            snap = self._data.get(call_id)
            if snap is None:
                snap = CallMemorySnapshot(shop_id=shop_id, call_id=call_id, caller_phone="")
            snap.interrupted = True
            if snap.turns and snap.turns[-1].role == "assistant":
                snap.turns[-1].interrupted = True
            self._data[call_id] = snap
            return snap

    async def update_state(
        self,
        *,
        shop_id: UUID,
        call_id: UUID,
        pending_question: str | None = None,
        appointment_id: str | None = None,
        slots_offered: list[dict] | None = None,
        pending_service: str | None = None,
        pending_service_id: str | None = None,
        pending_duration_minutes: int | None = None,
        pending_service_price: str | None = None,
        pending_cancel: bool | None = None,
        pending_action: str | None = None,
        pending_preferred_start: str | None = None,
        pending_preferred_end: str | None = None,
        pending_time_precision: str | None = None,
        pending_needs_date: bool | None = None,
        pending_needs_time: bool | None = None,
        active_visit_start: str | None = None,
        clear_pending_booking: bool = False,
        context_note: str | None = None,
    ) -> CallMemorySnapshot:
        async with self._locks[call_id]:
            snap = self._data.get(call_id) or CallMemorySnapshot(
                shop_id=shop_id, call_id=call_id, caller_phone=""
            )
            if pending_question is not None:
                snap.pending_question = pending_question or None
            if appointment_id is not None:
                snap.appointment_id = appointment_id or None
            if active_visit_start is not None:
                snap.active_visit_start = active_visit_start or None
            if pending_cancel is not None:
                snap.pending_cancel = bool(pending_cancel)
            if pending_action is not None:
                snap.pending_action = pending_action or None
            if clear_pending_booking:
                snap.slots_offered = []
                snap.pending_service = None
                snap.pending_service_id = None
                snap.pending_duration_minutes = None
                snap.pending_service_price = None
                snap.pending_cancel = False
                snap.pending_action = None
                snap.pending_preferred_start = None
                snap.pending_preferred_end = None
                snap.pending_time_precision = None
                snap.pending_needs_date = False
                snap.pending_needs_time = False
            else:
                if slots_offered is not None:
                    snap.slots_offered = slots_offered
                if pending_service is not None:
                    snap.pending_service = pending_service or None
                if pending_service_id is not None:
                    snap.pending_service_id = pending_service_id or None
                if pending_duration_minutes is not None:
                    snap.pending_duration_minutes = pending_duration_minutes or None
                if pending_service_price is not None:
                    snap.pending_service_price = pending_service_price or None
                if pending_preferred_start is not None:
                    snap.pending_preferred_start = pending_preferred_start or None
                if pending_preferred_end is not None:
                    snap.pending_preferred_end = pending_preferred_end or None
                if pending_time_precision is not None:
                    snap.pending_time_precision = pending_time_precision or None
                if pending_needs_date is not None:
                    snap.pending_needs_date = bool(pending_needs_date)
                if pending_needs_time is not None:
                    snap.pending_needs_time = bool(pending_needs_time)
            if context_note:
                snap.context_notes.append(context_note)
                snap.context_notes = snap.context_notes[-20:]
            self._data[call_id] = snap
            return snap
