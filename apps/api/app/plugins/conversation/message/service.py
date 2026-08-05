"""Message service — append / history for Conversation aggregate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.plugins.conversation.models import (
    Conversation,
    ConversationAttachment,
    ConversationMessage,
)
from app.plugins.conversation.store import InMemoryConversationStore


class ConversationMessageService:
    def __init__(self, store: InMemoryConversationStore | None = None) -> None:
        self._store = store or InMemoryConversationStore()

    async def append(
        self,
        shop_id: UUID,
        conversation_id: UUID,
        message: ConversationMessage | dict[str, Any],
    ) -> Conversation:
        if isinstance(message, dict):
            message = self._from_dict(shop_id, conversation_id, message)
        return await self._store.append_message(shop_id, conversation_id, message)

    async def history(
        self, shop_id: UUID, conversation_id: UUID
    ) -> list[ConversationMessage]:
        conv = await self._store.get(shop_id, conversation_id)
        if conv is None:
            return []
        return list(conv.messages)

    def _from_dict(
        self, shop_id: UUID, conversation_id: UUID, data: dict[str, Any]
    ) -> ConversationMessage:
        attachments = []
        for att in data.get("attachments") or []:
            if isinstance(att, ConversationAttachment):
                attachments.append(att)
            elif isinstance(att, str):
                attachments.append(ConversationAttachment(url=att))
            elif isinstance(att, dict):
                attachments.append(
                    ConversationAttachment(
                        url=att.get("url"),
                        content_type=att.get("content_type"),
                        filename=att.get("filename"),
                        metadata=dict(att.get("metadata") or {}),
                    )
                )
        return ConversationMessage(
            id=data.get("id") or uuid4(),
            conversation_id=conversation_id,
            shop_id=shop_id,
            sender=str(data.get("sender") or "customer"),
            receiver=data.get("receiver"),
            channel=str(data.get("channel") or "unknown"),
            content=str(data.get("content") or data.get("body") or ""),
            timestamp=data.get("timestamp") or datetime.now(timezone.utc),
            attachments=attachments,
            ai_summary=data.get("ai_summary"),
            intent=data.get("intent"),
            language=data.get("language"),
            confidence=data.get("confidence"),
            direction=str(data.get("direction") or "inbound"),
            metadata=dict(data.get("metadata") or {}),
        )
