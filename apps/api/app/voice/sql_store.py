"""SQLAlchemy voice call store."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import ShopModel, VoiceCallModel, VoiceTurnModel
from app.sms.store import normalize_phone
from app.voice.enums import VoiceCallStatus
from app.voice.models import VoiceCall, VoiceTurn


def _call(m: VoiceCallModel) -> VoiceCall:
    repair = None
    if m.repair_notes_json:
        try:
            repair = json.loads(m.repair_notes_json)
        except json.JSONDecodeError:
            repair = None
    meta = {}
    if m.metadata_json:
        try:
            meta = json.loads(m.metadata_json)
        except json.JSONDecodeError:
            meta = {}
    return VoiceCall(
        id=m.id,
        shop_id=m.shop_id,
        caller_phone=m.caller_phone,
        called_phone=m.called_phone,
        status=m.status,
        customer_id=m.customer_id,
        twilio_call_sid=m.twilio_call_sid,
        recording_sid=m.recording_sid,
        recording_url=m.recording_url,
        recording_duration_sec=m.recording_duration_sec,
        last_intent=m.last_intent,
        transcript=m.transcript,
        call_summary=m.call_summary,
        repair_notes=repair,
        owner_summary=m.owner_summary,
        escalate=m.escalate,
        escalation_reason=m.escalation_reason,
        human_takeover=m.human_takeover,
        started_at=m.started_at,
        ended_at=m.ended_at,
        created_at=m.created_at,
        metadata=meta,
    )


def _turn(m: VoiceTurnModel) -> VoiceTurn:
    return VoiceTurn(
        id=m.id,
        call_id=m.call_id,
        shop_id=m.shop_id,
        role=m.role,
        text=m.text,
        intent=m.intent,
        interrupted=m.interrupted,
        audio_url=m.audio_url,
        created_at=m.created_at,
    )


class SqlAlchemyVoiceStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_shop_id_by_voice_number(self, phone_e164: str) -> UUID | None:
        phone = normalize_phone(phone_e164)
        # Prefer dedicated voice number, fall back to sms number
        row = await self._session.scalar(
            select(ShopModel.id).where(ShopModel.voice_phone_e164 == phone)
        )
        if row:
            return row
        return await self._session.scalar(
            select(ShopModel.id).where(ShopModel.sms_phone_e164 == phone)
        )

    async def create_call(self, call: VoiceCall) -> VoiceCall:
        await self._session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(call.shop_id)},
        )
        model = VoiceCallModel(
            id=call.id,
            shop_id=call.shop_id,
            customer_id=call.customer_id,
            caller_phone=call.caller_phone,
            called_phone=call.called_phone,
            status=call.status,
            twilio_call_sid=call.twilio_call_sid,
            started_at=call.started_at or datetime.now(timezone.utc),
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _call(model)

    async def get_call(self, shop_id: UUID, call_id: UUID) -> VoiceCall | None:
        row = await self._session.scalar(
            select(VoiceCallModel).where(
                VoiceCallModel.shop_id == shop_id, VoiceCallModel.id == call_id
            )
        )
        return _call(row) if row else None

    async def get_call_by_sid(self, call_sid: str) -> VoiceCall | None:
        row = await self._session.scalar(
            select(VoiceCallModel).where(VoiceCallModel.twilio_call_sid == call_sid)
        )
        return _call(row) if row else None

    async def list_calls(
        self, shop_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[VoiceCall]:
        stmt = select(VoiceCallModel).where(VoiceCallModel.shop_id == shop_id)
        if status:
            stmt = stmt.where(VoiceCallModel.status == status)
        stmt = stmt.order_by(VoiceCallModel.started_at.desc().nullslast()).limit(limit)
        rows = await self._session.scalars(stmt)
        return [_call(r) for r in rows]

    async def list_live_calls(self, shop_id: UUID) -> list[VoiceCall]:
        live = [
            VoiceCallStatus.RINGING.value,
            VoiceCallStatus.IN_PROGRESS.value,
            VoiceCallStatus.ESCALATED.value,
        ]
        rows = await self._session.scalars(
            select(VoiceCallModel)
            .where(
                VoiceCallModel.shop_id == shop_id,
                VoiceCallModel.status.in_(live),
                VoiceCallModel.ended_at.is_(None),
            )
            .order_by(VoiceCallModel.started_at.desc().nullslast())
        )
        return [_call(r) for r in rows]

    async def update_call(self, call: VoiceCall) -> VoiceCall:
        row = await self._session.get(VoiceCallModel, call.id)
        if row is None:
            raise ValueError("Call not found")
        row.customer_id = call.customer_id
        row.status = call.status
        row.twilio_call_sid = call.twilio_call_sid
        row.recording_sid = call.recording_sid
        row.recording_url = call.recording_url
        row.recording_duration_sec = call.recording_duration_sec
        row.last_intent = call.last_intent
        row.transcript = call.transcript
        row.call_summary = call.call_summary
        row.repair_notes_json = json.dumps(call.repair_notes) if call.repair_notes else None
        row.owner_summary = call.owner_summary
        row.escalate = call.escalate
        row.escalation_reason = call.escalation_reason
        row.human_takeover = call.human_takeover
        row.started_at = call.started_at
        row.ended_at = call.ended_at
        row.metadata_json = json.dumps(call.metadata) if call.metadata else None
        await self._session.flush()
        return _call(row)

    async def add_turn(self, turn: VoiceTurn) -> VoiceTurn:
        model = VoiceTurnModel(
            id=turn.id or uuid4(),
            call_id=turn.call_id,
            shop_id=turn.shop_id,
            role=turn.role,
            text=turn.text,
            intent=turn.intent,
            interrupted=turn.interrupted,
            audio_url=turn.audio_url,
            created_at=turn.created_at or datetime.now(timezone.utc),
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _turn(model)

    async def list_turns(self, shop_id: UUID, call_id: UUID) -> list[VoiceTurn]:
        rows = await self._session.scalars(
            select(VoiceTurnModel)
            .where(VoiceTurnModel.shop_id == shop_id, VoiceTurnModel.call_id == call_id)
            .order_by(VoiceTurnModel.created_at.asc())
        )
        return [_turn(r) for r in rows]

    async def delete_call(self, shop_id: UUID, call_id: UUID) -> bool:
        await self._session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )
        row = await self._session.scalar(
            select(VoiceCallModel).where(
                VoiceCallModel.shop_id == shop_id,
                VoiceCallModel.id == call_id,
            )
        )
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True
