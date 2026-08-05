"""In-memory Conversation store — unified facade (no DB schema change)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.plugins.conversation.models import (
    Conversation,
    ConversationChannel,
    ConversationEvent,
    ConversationMessage,
    ConversationStatus,
    Participant,
    ParticipantRole,
)


def _channel_key(shop_id: UUID, channel: str, external_key: str | None) -> str:
    return f"{shop_id}:{channel}:{external_key or ''}"


class InMemoryConversationStore:
    """Process-local store. SMS/Voice remain source of truth for transport IDs."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, Conversation] = {}
        self._by_key: dict[str, UUID] = {}

    async def get(self, shop_id: UUID, conversation_id: UUID) -> Conversation | None:
        conv = self._by_id.get(conversation_id)
        if conv is None or conv.shop_id != shop_id:
            return None
        return conv

    async def find_by_external(
        self, shop_id: UUID, *, channel: str, external_key: str
    ) -> Conversation | None:
        cid = self._by_key.get(_channel_key(shop_id, channel, external_key))
        if cid is None:
            return None
        return await self.get(shop_id, cid)

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
        if external_key:
            existing = await self.find_by_external(
                shop_id, channel=channel, external_key=external_key
            )
            if existing is not None and existing.status != ConversationStatus.MERGED.value:
                if customer_id and not existing.customer_id:
                    existing.customer_id = customer_id
                if vehicle_id and not existing.vehicle_id:
                    existing.vehicle_id = vehicle_id
                existing.touch()
                return existing

        now = datetime.now(timezone.utc)
        cid = conversation_id or uuid4()
        if cid in self._by_id:
            return self._by_id[cid]

        participants = [
            Participant(
                role=ParticipantRole.CUSTOMER.value,
                identifier=external_key,
                customer_id=customer_id,
            ),
            Participant(role=ParticipantRole.SHOP.value, identifier=str(shop_id)),
            Participant(role=ParticipantRole.AI_ASSISTANT.value, identifier="asa"),
        ]
        conv = Conversation(
            id=cid,
            shop_id=shop_id,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            status=ConversationStatus.ACTIVE.value,
            channel=channel or ConversationChannel.UNKNOWN.value,
            external_key=external_key,
            channel_history=[channel] if channel else [],
            participants=participants,
            priority=priority,
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )
        conv.events.append(
            ConversationEvent(kind="created", summary=f"Conversation opened on {channel}")
        )
        self._by_id[cid] = conv
        if external_key:
            self._by_key[_channel_key(shop_id, channel, external_key)] = cid
        return conv

    async def update(self, shop_id: UUID, conversation: Conversation) -> Conversation:
        if conversation.shop_id != shop_id:
            raise ValueError("shop_id mismatch")
        conversation.touch()
        self._by_id[conversation.id] = conversation
        if conversation.external_key:
            self._by_key[
                _channel_key(shop_id, conversation.channel, conversation.external_key)
            ] = conversation.id
        return conversation

    async def close(self, shop_id: UUID, conversation_id: UUID) -> Conversation:
        conv = await self.get(shop_id, conversation_id)
        if conv is None:
            raise LookupError(f"Conversation not found: {conversation_id}")
        conv.status = ConversationStatus.CLOSED.value
        conv.events.append(ConversationEvent(kind="closed", summary="Conversation closed"))
        return await self.update(shop_id, conv)

    async def merge(
        self, shop_id: UUID, primary_id: UUID, duplicate_ids: list[UUID]
    ) -> Conversation:
        primary = await self.get(shop_id, primary_id)
        if primary is None:
            raise LookupError(f"Primary conversation not found: {primary_id}")
        for dup_id in duplicate_ids:
            if dup_id == primary_id:
                continue
            dup = await self.get(shop_id, dup_id)
            if dup is None:
                continue
            primary.messages.extend(dup.messages)
            primary.timeline.extend(dup.timeline)
            primary.events.extend(dup.events)
            primary.ai_decisions.extend(dup.ai_decisions)
            primary.workflow_history.extend(dup.workflow_history)
            for ch in dup.channel_history:
                if ch not in primary.channel_history:
                    primary.channel_history.append(ch)
            if not primary.customer_id and dup.customer_id:
                primary.customer_id = dup.customer_id
            if not primary.vehicle_id and dup.vehicle_id:
                primary.vehicle_id = dup.vehicle_id
            dup.status = ConversationStatus.MERGED.value
            dup.merged_into = primary_id
            await self.update(shop_id, dup)
        primary.messages.sort(key=lambda m: m.timestamp)
        primary.events.append(
            ConversationEvent(
                kind="merged",
                summary=f"Merged {len(duplicate_ids)} conversations",
                metadata={"duplicate_ids": [str(i) for i in duplicate_ids]},
            )
        )
        return await self.update(shop_id, primary)

    async def search(
        self,
        shop_id: UUID,
        *,
        customer_id: UUID | None = None,
        channel: str | None = None,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> list[Conversation]:
        items = [c for c in self._by_id.values() if c.shop_id == shop_id]
        if customer_id is not None:
            items = [c for c in items if c.customer_id == customer_id]
        if channel:
            items = [c for c in items if c.channel == channel]
        if status:
            items = [c for c in items if c.status == status]
        if query:
            q = query.lower()
            items = [
                c
                for c in items
                if (c.external_key and q in c.external_key.lower())
                or (c.ai.summary and q in c.ai.summary.lower())
                or any(q in (m.content or "").lower() for m in c.messages[-5:])
            ]
        items.sort(key=lambda c: c.updated_at, reverse=True)
        return items[:limit]

    async def append_message(
        self, shop_id: UUID, conversation_id: UUID, message: ConversationMessage
    ) -> Conversation:
        conv = await self.get(shop_id, conversation_id)
        if conv is None:
            raise LookupError(f"Conversation not found: {conversation_id}")
        conv.messages.append(message)
        if message.channel and message.channel not in conv.channel_history:
            conv.channel_history.append(message.channel)
        for att in message.attachments:
            conv.attachments.append(att)
        conv.timeline.append(
            ConversationEvent(
                kind="message",
                summary=f"{message.direction} via {message.channel}",
                at=message.timestamp,
            )
        )
        return await self.update(shop_id, conv)
