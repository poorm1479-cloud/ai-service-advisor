"""Voice call store — ports + in-memory implementation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from app.sms.store import normalize_phone
from app.voice.enums import VoiceCallStatus
from app.voice.models import VoiceCall, VoiceTurn


class VoiceStorePort(Protocol):
    async def create_call(self, call: VoiceCall) -> VoiceCall: ...

    async def get_call(self, shop_id: UUID, call_id: UUID) -> VoiceCall | None: ...

    async def get_call_by_sid(
        self, call_sid: str, shop_id: UUID | None = None
    ) -> VoiceCall | None: ...

    async def list_calls(
        self, shop_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[VoiceCall]: ...

    async def list_live_calls(self, shop_id: UUID) -> list[VoiceCall]: ...

    async def update_call(self, call: VoiceCall) -> VoiceCall: ...

    async def add_turn(self, turn: VoiceTurn) -> VoiceTurn: ...

    async def list_turns(self, shop_id: UUID, call_id: UUID) -> list[VoiceTurn]: ...

    async def delete_call(self, shop_id: UUID, call_id: UUID) -> bool: ...

    async def find_shop_id_by_voice_number(self, phone_e164: str) -> UUID | None: ...

    async def is_shop_ai_paused(self, shop_id: UUID) -> bool: ...


class InMemoryVoiceStore:
    def __init__(self) -> None:
        self.calls: dict[UUID, VoiceCall] = {}
        self.by_sid: dict[str, UUID] = {}
        self.turns: dict[UUID, list[VoiceTurn]] = defaultdict(list)
        self.shop_numbers: dict[str, UUID] = {}
        self.ai_paused_shops: set[UUID] = set()

    def register_shop_number(self, shop_id: UUID, phone_e164: str) -> None:
        self.shop_numbers[normalize_phone(phone_e164)] = shop_id

    async def find_shop_id_by_voice_number(self, phone_e164: str) -> UUID | None:
        return self.shop_numbers.get(normalize_phone(phone_e164))

    async def is_shop_ai_paused(self, shop_id: UUID) -> bool:
        return shop_id in self.ai_paused_shops

    async def create_call(self, call: VoiceCall) -> VoiceCall:
        self.calls[call.id] = call
        if call.twilio_call_sid:
            self.by_sid[call.twilio_call_sid] = call.id
        return call

    async def get_call(self, shop_id: UUID, call_id: UUID) -> VoiceCall | None:
        call = self.calls.get(call_id)
        if call and call.shop_id == shop_id and call.deleted_at is None:
            return call
        return None

    async def get_call_by_sid(
        self, call_sid: str, shop_id: UUID | None = None
    ) -> VoiceCall | None:
        call_id = self.by_sid.get(call_sid)
        if not call_id:
            return None
        call = self.calls.get(call_id)
        if call is None:
            return None
        if shop_id is not None and call.shop_id != shop_id:
            return None
        return call

    async def list_calls(
        self, shop_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[VoiceCall]:
        items = [
            c
            for c in self.calls.values()
            if c.shop_id == shop_id and c.deleted_at is None
        ]
        if status:
            items = [c for c in items if c.status == status]
        items.sort(key=lambda c: c.started_at or c.created_at or datetime.min, reverse=True)
        return items[:limit]

    async def list_live_calls(self, shop_id: UUID) -> list[VoiceCall]:
        live = {
            VoiceCallStatus.RINGING.value,
            VoiceCallStatus.IN_PROGRESS.value,
            VoiceCallStatus.ESCALATED.value,
        }
        items = [
            c
            for c in self.calls.values()
            if c.shop_id == shop_id
            and c.deleted_at is None
            and c.status in live
            and not c.ended_at
        ]
        items.sort(key=lambda c: c.started_at or c.created_at or datetime.min, reverse=True)
        return items

    async def update_call(self, call: VoiceCall) -> VoiceCall:
        self.calls[call.id] = call
        if call.twilio_call_sid:
            self.by_sid[call.twilio_call_sid] = call.id
        return call

    async def add_turn(self, turn: VoiceTurn) -> VoiceTurn:
        self.turns[turn.call_id].append(turn)
        return turn

    async def list_turns(self, shop_id: UUID, call_id: UUID) -> list[VoiceTurn]:
        call = await self.get_call(shop_id, call_id)
        if call is None:
            return []
        return list(self.turns.get(call_id, []))

    async def delete_call(self, shop_id: UUID, call_id: UUID) -> bool:
        call = self.calls.get(call_id)
        if call is None or call.shop_id != shop_id or call.deleted_at is not None:
            return False
        now = datetime.now(timezone.utc)
        call.deleted_at = now
        if call.ended_at is None:
            call.ended_at = now
        return True
