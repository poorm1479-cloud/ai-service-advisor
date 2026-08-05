"""Conversation session service — create/find/update/close/merge/search."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.conversation.models import Conversation, ConversationAiInsights
from app.plugins.conversation.store import InMemoryConversationStore


class ConversationSessionService:
    def __init__(self, store: InMemoryConversationStore | None = None) -> None:
        self._store = store or InMemoryConversationStore()

    @property
    def store(self) -> InMemoryConversationStore:
        return self._store

    async def create(
        self,
        shop_id: UUID,
        *,
        channel: str,
        external_key: str | None = None,
        customer_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        conversation_id: UUID | None = None,
        priority: str = "normal",
        metadata: dict[str, Any] | None = None,
    ) -> Conversation:
        return await self._store.create(
            shop_id,
            channel=channel,
            external_key=external_key,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            conversation_id=conversation_id,
            priority=priority,
            metadata=metadata,
        )

    async def find(self, shop_id: UUID, conversation_id: UUID) -> Conversation | None:
        return await self._store.get(shop_id, conversation_id)

    async def update(
        self,
        shop_id: UUID,
        conversation_id: UUID,
        *,
        patch: dict[str, Any] | None = None,
        ai: ConversationAiInsights | dict[str, Any] | None = None,
        message: Any | None = None,
        decision: dict[str, Any] | None = None,
        workflow_entry: dict[str, Any] | None = None,
        current_workflow: str | None = None,
        assigned_advisor: str | None = None,
        priority: str | None = None,
        status: str | None = None,
        customer_id: UUID | None = None,
        vehicle_id: UUID | None = None,
    ) -> Conversation:
        conv = await self._store.get(shop_id, conversation_id)
        if conv is None:
            raise LookupError(f"Conversation not found: {conversation_id}")

        if customer_id is not None:
            conv.customer_id = customer_id
        if vehicle_id is not None:
            conv.vehicle_id = vehicle_id
        if current_workflow is not None:
            conv.current_workflow = current_workflow
        if assigned_advisor is not None:
            conv.assigned_advisor = assigned_advisor
        if priority is not None:
            conv.priority = priority
        if status is not None:
            conv.status = status
        if patch:
            conv.metadata.update(patch)

        if ai is not None:
            if isinstance(ai, ConversationAiInsights):
                conv.ai = ai
            else:
                for key, value in ai.items():
                    if hasattr(conv.ai, key):
                        setattr(conv.ai, key, value)

        if decision is not None:
            conv.ai_decisions.append(decision)
        if workflow_entry is not None:
            conv.workflow_history.append(workflow_entry)

        if message is not None:
            from app.plugins.conversation.message.service import ConversationMessageService

            return await ConversationMessageService(self._store).append(
                shop_id, conversation_id, message
            )

        return await self._store.update(shop_id, conv)

    async def close(self, shop_id: UUID, conversation_id: UUID) -> Conversation:
        return await self._store.close(shop_id, conversation_id)

    async def merge(
        self, shop_id: UUID, primary_id: UUID, duplicate_ids: list[UUID]
    ) -> Conversation:
        return await self._store.merge(shop_id, primary_id, duplicate_ids)

    async def search(self, shop_id: UUID, **kwargs: Any) -> list[Conversation]:
        return await self._store.search(shop_id, **kwargs)
