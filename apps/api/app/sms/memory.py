"""Conversation memory — per-customer history for contextual replies."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from app.sms.models import ConversationTurn


@dataclass
class ConversationMemorySnapshot:
    shop_id: UUID
    customer_phone: str
    conversation_id: UUID | None
    turns: list[ConversationTurn] = field(default_factory=list)
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
    pending_preferred_start: str | None = None
    pending_preferred_end: str | None = None
    pending_time_precision: str | None = None
    pending_needs_date: bool = False
    pending_needs_time: bool = False
    # Booked visit start (ISO) — anchor for "same time" after a service-type swap.
    active_visit_start: str | None = None

    def as_prompt_context(self, *, max_turns: int = 20) -> str:
        lines: list[str] = []
        for turn in self.turns[-max_turns:]:
            role = turn.role.upper()
            intent = f" [{turn.intent}]" if turn.intent else ""
            lines.append(f"{role}{intent}: {turn.content}")
        if self.pending_question:
            lines.append(f"SYSTEM: pending follow-up — {self.pending_question}")
        return "\n".join(lines)


class ConversationMemoryPort(Protocol):
    async def load(
        self, *, shop_id: UUID, customer_phone: str, conversation_id: UUID | None = None
    ) -> ConversationMemorySnapshot: ...

    async def append(
        self,
        *,
        shop_id: UUID,
        customer_phone: str,
        turn: ConversationTurn,
        conversation_id: UUID | None = None,
    ) -> ConversationMemorySnapshot: ...

    async def update_state(
        self,
        *,
        shop_id: UUID,
        customer_phone: str,
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
        conversation_id: UUID | None = None,
    ) -> ConversationMemorySnapshot: ...

    async def clear(self, *, shop_id: UUID, customer_phone: str) -> None: ...


class InMemoryConversationMemory:
    """Supports multiple simultaneous conversations via per-key locks."""

    def __init__(self, *, max_turns: int = 100) -> None:
        self._data: dict[tuple[UUID, str], ConversationMemorySnapshot] = {}
        self._locks: dict[tuple[UUID, str], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._max_turns = max_turns

    def _key(self, shop_id: UUID, phone: str) -> tuple[UUID, str]:
        return (shop_id, phone)

    async def load(
        self, *, shop_id: UUID, customer_phone: str, conversation_id: UUID | None = None
    ) -> ConversationMemorySnapshot:
        key = self._key(shop_id, customer_phone)
        async with self._locks[key]:
            snap = self._data.get(key)
            if snap is None:
                snap = ConversationMemorySnapshot(
                    shop_id=shop_id,
                    customer_phone=customer_phone,
                    conversation_id=conversation_id,
                )
                self._data[key] = snap
            elif conversation_id:
                snap.conversation_id = conversation_id
            return snap

    async def append(
        self,
        *,
        shop_id: UUID,
        customer_phone: str,
        turn: ConversationTurn,
        conversation_id: UUID | None = None,
    ) -> ConversationMemorySnapshot:
        key = self._key(shop_id, customer_phone)
        async with self._locks[key]:
            snap = self._data.get(key) or ConversationMemorySnapshot(
                shop_id=shop_id,
                customer_phone=customer_phone,
                conversation_id=conversation_id,
            )
            if turn.at is None:
                turn.at = datetime.now(timezone.utc)
            snap.turns.append(turn)
            if len(snap.turns) > self._max_turns:
                snap.turns = snap.turns[-self._max_turns :]
            if conversation_id:
                snap.conversation_id = conversation_id
            self._data[key] = snap
            return snap

    async def update_state(
        self,
        *,
        shop_id: UUID,
        customer_phone: str,
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
        conversation_id: UUID | None = None,
    ) -> ConversationMemorySnapshot:
        snap = await self.load(
            shop_id=shop_id,
            customer_phone=customer_phone,
            conversation_id=conversation_id,
        )
        key = self._key(shop_id, customer_phone)
        async with self._locks[key]:
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
            self._data[key] = snap
            return snap

    async def clear(self, *, shop_id: UUID, customer_phone: str) -> None:
        key = self._key(shop_id, customer_phone)
        async with self._locks[key]:
            self._data.pop(key, None)
