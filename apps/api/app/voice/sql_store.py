"""SQLAlchemy voice call store (session-per-call, survives API restarts)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.models import ShopModel, VoiceCallModel, VoiceTurnModel
from app.sms.store import normalize_phone
from app.voice.enums import VoiceCallStatus
from app.voice.models import VoiceCall, VoiceTurn

logger = logging.getLogger("asa.voice.sql_store")


def _call(m: VoiceCallModel) -> VoiceCall:
    repair = None
    if m.repair_notes_json:
        try:
            repair = json.loads(m.repair_notes_json)
        except json.JSONDecodeError:
            repair = None
    meta: dict = {}
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
        deleted_at=m.deleted_at,
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
    """Postgres-backed voice call store for production runtime."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        if session is not None and session_factory is None:
            self._fixed_session = session
            self._session_factory = None
        else:
            self._fixed_session = None
            if session_factory is None:
                from app.infrastructure.database import SessionLocal

                session_factory = SessionLocal
            self._session_factory = session_factory
        # CallSid → shop_id (process-local). Complements app.sid_lookup RLS path.
        self._sid_shop: dict[str, UUID] = {}

    def _remember_sid(self, call: VoiceCall) -> None:
        if call.twilio_call_sid:
            self._sid_shop[call.twilio_call_sid] = call.shop_id

    def shop_id_for_sid(self, call_sid: str) -> UUID | None:
        return self._sid_shop.get(call_sid)

    async def _bind(self, session: AsyncSession, shop_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )
        # Ensure write path is not confused with sid-lookup mode.
        await session.execute(text("SELECT set_config('app.sid_lookup', '', true)"))

    async def _enable_sid_lookup(self, session: AsyncSession) -> None:
        """Transaction-local SELECT permission for CallSid without known shop."""
        await session.execute(text("SELECT set_config('app.sid_lookup', '1', true)"))

    async def find_shop_id_by_voice_number(self, phone_e164: str) -> UUID | None:
        phone = normalize_phone(phone_e164)

        async def _run(session: AsyncSession) -> UUID | None:
            row = await session.scalar(
                select(ShopModel.id).where(ShopModel.voice_phone_e164 == phone)
            )
            if row:
                return row
            return await session.scalar(
                select(ShopModel.id).where(ShopModel.sms_phone_e164 == phone)
            )

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def is_shop_ai_paused(self, shop_id: UUID) -> bool:
        if self._fixed_session is not None:
            val = await self._fixed_session.scalar(
                select(ShopModel.ai_paused).where(ShopModel.id == shop_id)
            )
            return bool(val)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            val = await session.scalar(
                select(ShopModel.ai_paused).where(ShopModel.id == shop_id)
            )
            return bool(val)

    async def create_call(self, call: VoiceCall) -> VoiceCall:
        async def _run(session: AsyncSession) -> VoiceCall:
            await self._bind(session, call.shop_id)
            model = VoiceCallModel(
                id=call.id,
                shop_id=call.shop_id,
                customer_id=call.customer_id,
                caller_phone=call.caller_phone,
                called_phone=call.called_phone,
                status=call.status,
                twilio_call_sid=call.twilio_call_sid,
                recording_sid=call.recording_sid,
                recording_url=call.recording_url,
                recording_duration_sec=call.recording_duration_sec,
                last_intent=call.last_intent,
                transcript=call.transcript,
                call_summary=call.call_summary,
                repair_notes_json=json.dumps(call.repair_notes)
                if call.repair_notes
                else None,
                owner_summary=call.owner_summary,
                escalate=call.escalate,
                escalation_reason=call.escalation_reason,
                human_takeover=call.human_takeover,
                started_at=call.started_at or datetime.now(timezone.utc),
                ended_at=call.ended_at,
                metadata_json=json.dumps(call.metadata) if call.metadata else None,
            )
            session.add(model)
            await session.flush()
            await session.refresh(model)
            return _call(model)

        if self._fixed_session is not None:
            out = await _run(self._fixed_session)
            self._remember_sid(out)
            return out
        assert self._session_factory is not None
        async with self._session_factory() as session:
            out = await _run(session)
            await session.commit()
            self._remember_sid(out)
            return out

    async def get_call(self, shop_id: UUID, call_id: UUID) -> VoiceCall | None:
        async def _run(session: AsyncSession) -> VoiceCall | None:
            await self._bind(session, shop_id)
            row = await session.scalar(
                select(VoiceCallModel).where(
                    VoiceCallModel.shop_id == shop_id,
                    VoiceCallModel.id == call_id,
                    VoiceCallModel.deleted_at.is_(None),
                )
            )
            return _call(row) if row else None

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def get_call_by_sid(
        self, call_sid: str, shop_id: UUID | None = None
    ) -> VoiceCall | None:
        """Lookup by Twilio CallSid. Prefer shop_id (FORCE RLS safe)."""
        resolved_shop = shop_id or self._sid_shop.get(call_sid)

        async def _run_scoped(session: AsyncSession, sid: UUID) -> VoiceCall | None:
            await self._bind(session, sid)
            row = await session.scalar(
                select(VoiceCallModel).where(
                    VoiceCallModel.twilio_call_sid == call_sid,
                    VoiceCallModel.shop_id == sid,
                )
            )
            if row:
                out = _call(row)
                self._remember_sid(out)
                return out
            return None

        async def _run_unscoped(session: AsyncSession) -> VoiceCall | None:
            # Prefer GUC-based policy (0041_voice_sid_lookup_rls); fall back soft-miss.
            try:
                await self._enable_sid_lookup(session)
                row = await session.scalar(
                    select(VoiceCallModel).where(
                        VoiceCallModel.twilio_call_sid == call_sid
                    )
                )
                if row is None:
                    return None
                out = _call(row)
                self._remember_sid(out)
                return out
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "voice.sql_store.sid_unscoped_miss sid=%s err=%s", call_sid, exc
                )
                return None

        if self._fixed_session is not None:
            if resolved_shop is not None:
                return await _run_scoped(self._fixed_session, resolved_shop)
            return await _run_unscoped(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            if resolved_shop is not None:
                return await _run_scoped(session, resolved_shop)
            return await _run_unscoped(session)

    async def list_calls(
        self, shop_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[VoiceCall]:
        async def _run(session: AsyncSession) -> list[VoiceCall]:
            await self._bind(session, shop_id)
            stmt = select(VoiceCallModel).where(
                VoiceCallModel.shop_id == shop_id,
                VoiceCallModel.deleted_at.is_(None),
            )
            if status:
                stmt = stmt.where(VoiceCallModel.status == status)
            stmt = stmt.order_by(VoiceCallModel.started_at.desc().nullslast()).limit(limit)
            rows = await session.scalars(stmt)
            return [_call(r) for r in rows]

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def list_live_calls(self, shop_id: UUID) -> list[VoiceCall]:
        live = [
            VoiceCallStatus.RINGING.value,
            VoiceCallStatus.IN_PROGRESS.value,
            VoiceCallStatus.ESCALATED.value,
        ]

        async def _run(session: AsyncSession) -> list[VoiceCall]:
            await self._bind(session, shop_id)
            rows = await session.scalars(
                select(VoiceCallModel)
                .where(
                    VoiceCallModel.shop_id == shop_id,
                    VoiceCallModel.status.in_(live),
                    VoiceCallModel.ended_at.is_(None),
                    VoiceCallModel.deleted_at.is_(None),
                )
                .order_by(VoiceCallModel.started_at.desc().nullslast())
            )
            return [_call(r) for r in rows]

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def update_call(self, call: VoiceCall) -> VoiceCall:
        async def _run(session: AsyncSession) -> VoiceCall:
            await self._bind(session, call.shop_id)
            row = await session.get(VoiceCallModel, call.id)
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
            row.repair_notes_json = (
                json.dumps(call.repair_notes) if call.repair_notes else None
            )
            row.owner_summary = call.owner_summary
            row.escalate = call.escalate
            row.escalation_reason = call.escalation_reason
            row.human_takeover = call.human_takeover
            row.started_at = call.started_at
            row.ended_at = call.ended_at
            row.metadata_json = json.dumps(call.metadata) if call.metadata else None
            await session.flush()
            return _call(row)

        if self._fixed_session is not None:
            out = await _run(self._fixed_session)
            self._remember_sid(out)
            return out
        assert self._session_factory is not None
        async with self._session_factory() as session:
            out = await _run(session)
            await session.commit()
            self._remember_sid(out)
            return out

    async def add_turn(self, turn: VoiceTurn) -> VoiceTurn:
        async def _run(session: AsyncSession) -> VoiceTurn:
            await self._bind(session, turn.shop_id)
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
            session.add(model)
            await session.flush()
            await session.refresh(model)
            return _turn(model)

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            out = await _run(session)
            await session.commit()
            return out

    async def list_turns(self, shop_id: UUID, call_id: UUID) -> list[VoiceTurn]:
        async def _run(session: AsyncSession) -> list[VoiceTurn]:
            await self._bind(session, shop_id)
            # Soft-deleted calls are hidden from staff UI (including transcripts).
            call = await session.scalar(
                select(VoiceCallModel).where(
                    VoiceCallModel.shop_id == shop_id,
                    VoiceCallModel.id == call_id,
                    VoiceCallModel.deleted_at.is_(None),
                )
            )
            if call is None:
                return []
            rows = await session.scalars(
                select(VoiceTurnModel)
                .where(VoiceTurnModel.shop_id == shop_id, VoiceTurnModel.call_id == call_id)
                .order_by(VoiceTurnModel.created_at.asc())
            )
            return [_turn(r) for r in rows]

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def delete_call(self, shop_id: UUID, call_id: UUID) -> bool:
        """Soft-delete so dashboard 'AI calls handled' keeps counting the call."""

        async def _run(session: AsyncSession) -> bool:
            await self._bind(session, shop_id)
            result = await session.execute(
                text(
                    "UPDATE voice_calls"
                    " SET deleted_at = COALESCE(deleted_at, NOW()),"
                    "     ended_at = COALESCE(ended_at, NOW())"
                    " WHERE shop_id = :shop_id AND id = :id AND deleted_at IS NULL"
                ),
                {"shop_id": shop_id, "id": call_id},
            )
            return bool(result.rowcount)

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            ok = await _run(session)
            if ok:
                await session.commit()
            return ok
