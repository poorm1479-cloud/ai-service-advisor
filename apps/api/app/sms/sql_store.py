"""SQLAlchemy SMS store adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import ShopModel, SmsConversationModel, SmsMessageModel
from app.sms.enums import SmsConversationStatus
from app.sms.models import SmsConversation, SmsMessage
from app.sms.store import normalize_phone


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
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_shop_id_by_sms_number(self, phone_e164: str) -> UUID | None:
        phone = normalize_phone(phone_e164)
        row = await self._session.scalar(
            select(ShopModel.id).where(ShopModel.sms_phone_e164 == phone)
        )
        return row

    async def get_or_create_conversation(
        self, *, shop_id: UUID, customer_phone: str, customer_id: UUID | None = None
    ) -> SmsConversation:
        phone = normalize_phone(customer_phone)
        await self._session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )
        existing = await self._session.scalar(
            select(SmsConversationModel).where(
                SmsConversationModel.shop_id == shop_id,
                SmsConversationModel.customer_phone == phone,
            )
        )
        if existing:
            if customer_id and existing.customer_id is None:
                existing.customer_id = customer_id
                await self._session.flush()
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
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _conv(model)

    async def get_conversation(
        self, shop_id: UUID, conversation_id: UUID
    ) -> SmsConversation | None:
        row = await self._session.scalar(
            select(SmsConversationModel).where(
                SmsConversationModel.shop_id == shop_id,
                SmsConversationModel.id == conversation_id,
            )
        )
        return _conv(row) if row else None

    async def list_conversations(
        self, shop_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[SmsConversation]:
        stmt = select(SmsConversationModel).where(SmsConversationModel.shop_id == shop_id)
        if status:
            stmt = stmt.where(SmsConversationModel.status == status)
        stmt = stmt.order_by(SmsConversationModel.last_message_at.desc().nullslast()).limit(limit)
        rows = await self._session.scalars(stmt)
        return [_conv(r) for r in rows]

    async def update_conversation(self, conversation: SmsConversation) -> SmsConversation:
        row = await self._session.get(SmsConversationModel, conversation.id)
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
        await self._session.flush()
        return _conv(row)

    async def add_message(self, message: SmsMessage) -> SmsMessage:
        if message.twilio_sid:
            existing = await self.find_message_by_twilio_sid(message.twilio_sid)
            if existing is not None:
                return existing
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
        self._session.add(model)
        conv = await self._session.get(SmsConversationModel, message.conversation_id)
        if conv:
            conv.last_message_at = model.created_at
        await self._session.flush()
        await self._session.refresh(model)
        return _msg(model)

    async def find_message_by_twilio_sid(self, twilio_sid: str) -> SmsMessage | None:
        if not twilio_sid:
            return None
        row = await self._session.scalar(
            select(SmsMessageModel).where(SmsMessageModel.twilio_sid == twilio_sid)
        )
        return _msg(row) if row else None

    async def list_messages(
        self, shop_id: UUID, conversation_id: UUID, *, limit: int = 200
    ) -> list[SmsMessage]:
        rows = await self._session.scalars(
            select(SmsMessageModel)
            .where(
                SmsMessageModel.shop_id == shop_id,
                SmsMessageModel.conversation_id == conversation_id,
            )
            .order_by(SmsMessageModel.created_at.asc())
            .limit(limit)
        )
        return [_msg(r) for r in rows]

    async def delete_conversation(self, shop_id: UUID, conversation_id: UUID) -> bool:
        await self._session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )
        row = await self._session.scalar(
            select(SmsConversationModel).where(
                SmsConversationModel.shop_id == shop_id,
                SmsConversationModel.id == conversation_id,
            )
        )
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True
