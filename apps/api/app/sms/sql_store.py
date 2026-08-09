"""SQLAlchemy SMS store adapter (session-per-call, survives API restarts)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.models import ShopModel, SmsConversationModel, SmsMessageModel
from app.sms.enums import SmsConversationStatus
from app.sms.models import SmsConversation, SmsMessage
from app.sms.store import normalize_phone

logger = logging.getLogger("asa.sms.sql_store")


def _conv(m: SmsConversationModel) -> SmsConversation:
    return SmsConversation(
        id=m.id,
        shop_id=m.shop_id,
        customer_phone=m.customer_phone,
        customer_id=m.customer_id,
        status=m.status,
        subject=m.subject,
        last_intent=m.last_intent,
        owner_summary=m.owner_summary,
        reply_preview=m.reply_preview,
        escalate=m.escalate,
        escalation_reason=m.escalation_reason,
        human_takeover=m.human_takeover,
        last_message_at=m.last_message_at,
        created_at=m.created_at,
    )


def _msg(m: SmsMessageModel) -> SmsMessage:
    return SmsMessage(
        id=m.id,
        conversation_id=m.conversation_id,
        shop_id=m.shop_id,
        direction=m.direction,
        body=m.body,
        twilio_sid=m.twilio_sid,
        intent=m.intent,
        created_at=m.created_at,
    )


class SqlAlchemySmsStore:
    """Postgres-backed SMS conversation store for production runtime."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        # Prefer session_factory (singleton runtime). A single session arg is
        # kept for ad-hoc scripts that already open a transaction.
        if session is not None and session_factory is None:
            self._fixed_session = session
            self._session_factory = None
        else:
            self._fixed_session = None
            if session_factory is None:
                from app.infrastructure.database import SessionLocal

                session_factory = SessionLocal
            self._session_factory = session_factory

    async def _bind(self, session: AsyncSession, shop_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )
        await session.execute(text("SELECT set_config('app.sid_lookup', '', true)"))

    async def _bypass_rls(self, session: AsyncSession) -> bool:
        """Enable SELECT-by-SID via app.sid_lookup GUC (migration 0041)."""
        try:
            await session.execute(text("SELECT set_config('app.sid_lookup', '1', true)"))
            return True
        except Exception:  # noqa: BLE001
            logger.warning("sms.sql_store.sid_lookup_unavailable")
            return False

    async def find_shop_id_by_sms_number(self, phone_e164: str) -> UUID | None:
        phone = normalize_phone(phone_e164)
        if self._fixed_session is not None:
            return await self._fixed_session.scalar(
                select(ShopModel.id).where(ShopModel.sms_phone_e164 == phone)
            )
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await session.scalar(
                select(ShopModel.id).where(ShopModel.sms_phone_e164 == phone)
            )

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

    async def get_or_create_conversation(
        self, *, shop_id: UUID, customer_phone: str, customer_id: UUID | None = None
    ) -> SmsConversation:
        phone = normalize_phone(customer_phone)

        async def _run(session: AsyncSession) -> SmsConversation:
            await self._bind(session, shop_id)
            existing = await session.scalar(
                select(SmsConversationModel).where(
                    SmsConversationModel.shop_id == shop_id,
                    SmsConversationModel.customer_phone == phone,
                )
            )
            if existing:
                if customer_id and existing.customer_id is None:
                    existing.customer_id = customer_id
                    await session.flush()
                return _conv(existing)

            now = datetime.now(timezone.utc)
            model = SmsConversationModel(
                id=uuid4(),
                shop_id=shop_id,
                customer_phone=phone,
                customer_id=customer_id,
                status=SmsConversationStatus.ACTIVE.value,
                last_message_at=now,
            )
            session.add(model)
            await session.flush()
            await session.refresh(model)
            return _conv(model)

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            out = await _run(session)
            await session.commit()
            return out

    async def get_conversation(
        self, shop_id: UUID, conversation_id: UUID
    ) -> SmsConversation | None:
        async def _run(session: AsyncSession) -> SmsConversation | None:
            await self._bind(session, shop_id)
            row = await session.scalar(
                select(SmsConversationModel).where(
                    SmsConversationModel.shop_id == shop_id,
                    SmsConversationModel.id == conversation_id,
                )
            )
            return _conv(row) if row else None

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def list_conversations(
        self, shop_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[SmsConversation]:
        async def _run(session: AsyncSession) -> list[SmsConversation]:
            await self._bind(session, shop_id)
            stmt = select(SmsConversationModel).where(SmsConversationModel.shop_id == shop_id)
            if status:
                stmt = stmt.where(SmsConversationModel.status == status)
            stmt = stmt.order_by(
                SmsConversationModel.last_message_at.desc().nullslast()
            ).limit(limit)
            rows = await session.scalars(stmt)
            return [_conv(r) for r in rows]

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def update_conversation(self, conversation: SmsConversation) -> SmsConversation:
        async def _run(session: AsyncSession) -> SmsConversation:
            await self._bind(session, conversation.shop_id)
            row = await session.get(SmsConversationModel, conversation.id)
            if row is None:
                raise ValueError("Conversation not found")
            row.customer_id = conversation.customer_id
            row.status = conversation.status
            row.subject = conversation.subject
            row.last_intent = conversation.last_intent
            row.owner_summary = conversation.owner_summary
            row.reply_preview = conversation.reply_preview
            row.escalate = conversation.escalate
            row.escalation_reason = conversation.escalation_reason
            row.human_takeover = conversation.human_takeover
            row.last_message_at = conversation.last_message_at
            await session.flush()
            return _conv(row)

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            out = await _run(session)
            await session.commit()
            return out

    async def add_message(self, message: SmsMessage) -> SmsMessage:
        async def _run(session: AsyncSession) -> SmsMessage:
            await self._bind(session, message.shop_id)
            if message.twilio_sid:
                existing = await session.scalar(
                    select(SmsMessageModel).where(
                        SmsMessageModel.twilio_sid == message.twilio_sid
                    )
                )
                if existing is not None:
                    return _msg(existing)
            model = SmsMessageModel(
                id=message.id,
                conversation_id=message.conversation_id,
                shop_id=message.shop_id,
                direction=message.direction,
                body=message.body,
                twilio_sid=message.twilio_sid,
                intent=message.intent,
                created_at=message.created_at or datetime.now(timezone.utc),
            )
            session.add(model)
            conv = await session.get(SmsConversationModel, message.conversation_id)
            if conv:
                conv.last_message_at = model.created_at
            await session.flush()
            await session.refresh(model)
            return _msg(model)

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            out = await _run(session)
            await session.commit()
            return out

    async def find_message_by_twilio_sid(
        self, twilio_sid: str, shop_id: UUID | None = None
    ) -> SmsMessage | None:
        if not twilio_sid:
            return None

        async def _run(session: AsyncSession) -> SmsMessage | None:
            if shop_id is not None:
                await self._bind(session, shop_id)
                row = await session.scalar(
                    select(SmsMessageModel).where(
                        SmsMessageModel.twilio_sid == twilio_sid,
                        SmsMessageModel.shop_id == shop_id,
                    )
                )
                return _msg(row) if row else None
            try:
                await self._bypass_rls(session)
                row = await session.scalar(
                    select(SmsMessageModel).where(
                        SmsMessageModel.twilio_sid == twilio_sid
                    )
                )
                return _msg(row) if row else None
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "sms.sql_store.sid_unscoped_miss sid=%s err=%s", twilio_sid, exc
                )
                return None

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def list_messages(
        self, shop_id: UUID, conversation_id: UUID, *, limit: int = 200
    ) -> list[SmsMessage]:
        async def _run(session: AsyncSession) -> list[SmsMessage]:
            await self._bind(session, shop_id)
            rows = await session.scalars(
                select(SmsMessageModel)
                .where(
                    SmsMessageModel.shop_id == shop_id,
                    SmsMessageModel.conversation_id == conversation_id,
                )
                .order_by(SmsMessageModel.created_at.asc())
                .limit(limit)
            )
            return [_msg(r) for r in rows]

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def delete_conversation(self, shop_id: UUID, conversation_id: UUID) -> bool:
        async def _run(session: AsyncSession) -> bool:
            await self._bind(session, shop_id)
            result = await session.execute(
                text(
                    "DELETE FROM sms_conversations WHERE shop_id = :shop_id AND id = :id"
                ),
                {"shop_id": shop_id, "id": conversation_id},
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
