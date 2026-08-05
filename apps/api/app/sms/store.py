"""SMS store ports and in-memory implementation (tests + local)."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from app.sms.enums import SmsConversationStatus
from app.sms.models import SmsConversation, SmsMessage

_DIGITS = re.compile(r"\D+")


def normalize_phone(phone: str) -> str:
    digits = _DIGITS.sub("", phone or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if digits.startswith("1") and len(digits) == 11:
        return f"+{digits}"
    if phone.startswith("+") and digits:
        return f"+{digits}"
    return f"+{digits}" if digits else phone


class SmsStorePort(Protocol):
    async def get_or_create_conversation(
        self, *, shop_id: UUID, customer_phone: str, customer_id: UUID | None = None
    ) -> SmsConversation: ...

    async def get_conversation(
        self, shop_id: UUID, conversation_id: UUID
    ) -> SmsConversation | None: ...

    async def list_conversations(
        self, shop_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[SmsConversation]: ...

    async def update_conversation(self, conversation: SmsConversation) -> SmsConversation: ...

    async def add_message(self, message: SmsMessage) -> SmsMessage: ...

    async def find_message_by_twilio_sid(self, twilio_sid: str) -> SmsMessage | None: ...

    async def list_messages(
        self, shop_id: UUID, conversation_id: UUID, *, limit: int = 200
    ) -> list[SmsMessage]: ...

    async def find_shop_id_by_sms_number(self, phone_e164: str) -> UUID | None: ...


class InMemorySmsStore:
    """Concurrent-safe enough for unit tests; production uses SQL adapter."""

    def __init__(self) -> None:
        self.conversations: dict[UUID, SmsConversation] = {}
        self.messages: dict[UUID, list[SmsMessage]] = defaultdict(list)
        self.shop_numbers: dict[str, UUID] = {}
        self._by_phone: dict[tuple[UUID, str], UUID] = {}

    def register_shop_number(self, shop_id: UUID, phone_e164: str) -> None:
        self.shop_numbers[normalize_phone(phone_e164)] = shop_id

    async def find_shop_id_by_sms_number(self, phone_e164: str) -> UUID | None:
        return self.shop_numbers.get(normalize_phone(phone_e164))

    async def get_or_create_conversation(
        self, *, shop_id: UUID, customer_phone: str, customer_id: UUID | None = None
    ) -> SmsConversation:
        key = (shop_id, normalize_phone(customer_phone))
        existing_id = self._by_phone.get(key)
        if existing_id and existing_id in self.conversations:
            conv = self.conversations[existing_id]
            if customer_id and not conv.customer_id:
                conv.customer_id = customer_id
            return conv
        now = datetime.now(timezone.utc)
        conv = SmsConversation(
            id=uuid4(),
            shop_id=shop_id,
            customer_phone=normalize_phone(customer_phone),
            customer_id=customer_id,
            status=SmsConversationStatus.ACTIVE.value,
            created_at=now,
            last_message_at=now,
        )
        self.conversations[conv.id] = conv
        self._by_phone[key] = conv.id
        return conv

    async def get_conversation(
        self, shop_id: UUID, conversation_id: UUID
    ) -> SmsConversation | None:
        conv = self.conversations.get(conversation_id)
        if conv and conv.shop_id == shop_id:
            return conv
        return None

    async def list_conversations(
        self, shop_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[SmsConversation]:
        items = [c for c in self.conversations.values() if c.shop_id == shop_id]
        if status:
            items = [c for c in items if c.status == status]
        items.sort(key=lambda c: c.last_message_at or c.created_at or datetime.min, reverse=True)
        return items[:limit]

    async def update_conversation(self, conversation: SmsConversation) -> SmsConversation:
        self.conversations[conversation.id] = conversation
        return conversation

    async def add_message(self, message: SmsMessage) -> SmsMessage:
        self.messages[message.conversation_id].append(message)
        conv = self.conversations.get(message.conversation_id)
        if conv:
            conv.last_message_at = message.created_at or datetime.now(timezone.utc)
        return message

    async def find_message_by_twilio_sid(self, twilio_sid: str) -> SmsMessage | None:
        if not twilio_sid:
            return None
        for msgs in self.messages.values():
            for m in msgs:
                if m.twilio_sid == twilio_sid:
                    return m
        return None

    async def list_messages(
        self, shop_id: UUID, conversation_id: UUID, *, limit: int = 200
    ) -> list[SmsMessage]:
        conv = await self.get_conversation(shop_id, conversation_id)
        if conv is None:
            return []
        msgs = list(self.messages.get(conversation_id, []))
        return msgs[-limit:]
