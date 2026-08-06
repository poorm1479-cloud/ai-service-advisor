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

    async def get_call_by_sid(self, call_sid: str) -> VoiceCall | None: ...

    async def list_calls(
        self, shop_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[VoiceCall]: ...

    async def list_live_calls(self, shop_id: UUID) -> list[VoiceCall]: ...

    async def update_call(self, call: VoiceCall) -> VoiceCall: ...

    async def add_turn(self, turn: VoiceTurn) -> VoiceTurn: ...

    async def list_turns(self, shop_id: UUID, call_id: UUID) -> list[VoiceTurn]: ...

    async def delete_call(self, shop_id: UUID, call_id: UUID) -> bool: ...

    async def find_shop_id_by_voice_number(self, phone_e164: str) -> UUID | None: ...


class InMemoryVoiceStore:
    def __init__(self) -> None:
        self.calls: dict[UUID, VoiceCall] = {}
        self.by_sid: dict[str, UUID] = {}
        self.turns: dict[UUID, list[VoiceTurn]] = defaultdict(list)
        self.shop_numbers: dict[str, UUID] = {}

    def register_shop_number(self, shop_id: UUID, phone_e164: str) -> None:
        self.shop_numbers[normalize_phone(phone_e164)] = shop_id

    async def find_shop_id_by_voice_number(self, phone_e164: str) -> UUID | None:
        return self.shop_numbers.get(normalize_phone(phone_e164))

    async def create_call(self, call: VoiceCall) -> VoiceCall:
        self.calls[call.id] = call
        if call.twilio_call_sid:
            self.by_sid[call.twilio_call_sid] = call.id
        return call

    async def get_call(self, shop_id: UUID, call_id: UUID) -> VoiceCall | None:
        call = self.calls.get(call_id)
        if call and call.shop_id == shop_id:
            return call
        return None

    async def get_call_by_sid(self, call_sid: str) -> VoiceCall | None:
        call_id = self.by_sid.get(call_sid)
        if not call_id:
            return None
        return self.calls.get(call_id)

    async def list_calls(
        self, shop_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[VoiceCall]:
        items = [c for c in self.calls.values() if c.shop_id == shop_id]
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
            if c.shop_id == shop_id and c.status in live and not c.ended_at
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
            # Allow lookup by sid-only contexts in tests
            call = self.calls.get(call_id)
            if call is None or call.shop_id != shop_id:
                return []
        return list(self.turns.get(call_id, []))

    async def delete_call(self, shop_id: UUID, call_id: UUID) -> bool:
        call = await self.get_call(shop_id, call_id)
        if call is None:
            return False
        if call.twilio_call_sid and self.by_sid.get(call.twilio_call_sid) == call_id:
            del self.by_sid[call.twilio_call_sid]
        self.calls.pop(call_id, None)
        self.turns.pop(call_id, None)
        return True
