"""Conversation Plugin — unified Conversation domain over channel adapters."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.conversation.channels import BaseChannelAdapter, default_channel_adapters
from app.plugins.conversation.intelligence.service import ConversationIntelligenceService
from app.plugins.conversation.message.service import ConversationMessageService
from app.plugins.conversation.session.service import ConversationSessionService
from app.plugins.conversation.store import InMemoryConversationStore
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext


class ConversationPlugin:
    """IPlugin + IConversationPlugin — wrap channels as adapters, not rewrites."""

    def __init__(
        self,
        *,
        store: InMemoryConversationStore | None = None,
        sessions: ConversationSessionService | None = None,
        messages: ConversationMessageService | None = None,
        intelligence: ConversationIntelligenceService | None = None,
        adapters: dict[str, BaseChannelAdapter] | None = None,
    ) -> None:
        self._store = store or InMemoryConversationStore()
        self._sessions = sessions or ConversationSessionService(self._store)
        self._messages = messages or ConversationMessageService(self._store)
        self._intelligence = intelligence or ConversationIntelligenceService()
        self._adapters = adapters or default_channel_adapters()
        self._initialized = False

    def plugin_id(self) -> str:
        return "conversation"

    def plugin_name(self) -> str:
        return "Conversation Plugin"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Unified Conversation domain across Phone, SMS, Email, Facebook, "
            "Website Chat, Walk-in, and future messaging channels."
        )

    def supported_capabilities(self) -> list[str]:
        return [
            Capability.CREATE_CONVERSATION.value,
            Capability.FIND_CONVERSATION.value,
            Capability.UPDATE_CONVERSATION.value,
            Capability.CLOSE_CONVERSATION.value,
            Capability.MERGE_CONVERSATION.value,
            Capability.SEARCH_CONVERSATION.value,
            Capability.CONVERSATION_HISTORY.value,
            Capability.CONVERSATION_SUMMARY.value,
        ]

    def capabilities(self) -> list[str]:
        return self.supported_capabilities()

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
            "capabilities": len(self.supported_capabilities()),
            "channels": sorted(self._adapters.keys()),
        }

    @property
    def sessions(self) -> ConversationSessionService:
        return self._sessions

    @property
    def messages(self) -> ConversationMessageService:
        return self._messages

    @property
    def intelligence(self) -> ConversationIntelligenceService:
        return self._intelligence

    @property
    def store(self) -> InMemoryConversationStore:
        return self._store

    def get_adapter(self, channel: str) -> BaseChannelAdapter:
        key = (channel or "unknown").lower()
        if key == "voice":
            key = "phone"
        adapter = self._adapters.get(key)
        if adapter is None:

            class _Unknown(BaseChannelAdapter):
                channel = key

            adapter = _Unknown()
            self._adapters[key] = adapter
        return adapter

    async def ingest_inbound(
        self,
        shop_id: UUID,
        *,
        channel: str,
        content: str,
        sender_identifier: str | None = None,
        conversation_id: UUID | None = None,
        customer_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        attachments: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Create/update Conversation + append inbound message (Workflow-facing)."""
        adapter = self.get_adapter(channel)
        inbound = adapter.normalize(
            {
                "content": content,
                "sender_identifier": sender_identifier,
                "conversation_id": conversation_id,
                "attachments": attachments or [],
                "metadata": metadata or {},
            }
        )
        cid = conversation_id
        if cid is None and inbound.external_conversation_id:
            try:
                cid = UUID(str(inbound.external_conversation_id))
            except (ValueError, TypeError):
                cid = None

        conv = await self._sessions.create(
            shop_id,
            channel=inbound.channel,
            external_key=inbound.sender_identifier or inbound.external_conversation_id,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            conversation_id=cid,
            metadata=dict(inbound.metadata),
        )
        await self._messages.append(
            shop_id,
            conv.id,
            {
                "sender": inbound.sender_identifier or "customer",
                "receiver": "shop",
                "channel": inbound.channel,
                "content": inbound.content,
                "attachments": inbound.attachments,
                "direction": "inbound",
                "language": (metadata or {}).get("language"),
                "metadata": dict(inbound.metadata),
            },
        )
        return await self._sessions.find(shop_id, conv.id)

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        if context is not None:
            for key, value in context.to_kwargs().items():
                if key.startswith("_"):
                    continue
                kwargs.setdefault(key, value)
            if context.conversation_id and "conversation_id" not in kwargs:
                try:
                    kwargs["conversation_id"] = UUID(str(context.conversation_id))
                except (ValueError, TypeError):
                    pass

        shop_id: UUID = kwargs["shop_id"]

        if capability == Capability.CREATE_CONVERSATION:
            content = kwargs.get("content") or kwargs.get("body")
            if content:
                return await self.ingest_inbound(
                    shop_id,
                    channel=str(kwargs.get("channel") or "unknown"),
                    content=str(content),
                    sender_identifier=kwargs.get("sender_identifier")
                    or kwargs.get("external_key"),
                    conversation_id=kwargs.get("conversation_id"),
                    customer_id=kwargs.get("customer_id"),
                    vehicle_id=kwargs.get("vehicle_id"),
                    attachments=list(kwargs.get("attachments") or []),
                    metadata=dict(kwargs.get("metadata") or {}),
                )
            return await self._sessions.create(
                shop_id,
                channel=str(kwargs.get("channel") or "unknown"),
                external_key=kwargs.get("external_key") or kwargs.get("sender_identifier"),
                customer_id=kwargs.get("customer_id"),
                vehicle_id=kwargs.get("vehicle_id"),
                conversation_id=kwargs.get("conversation_id"),
                priority=str(kwargs.get("priority") or "normal"),
                metadata=dict(kwargs.get("metadata") or {}),
            )

        if capability == Capability.FIND_CONVERSATION:
            cid = kwargs.get("conversation_id")
            if cid is None:
                raise ValueError("conversation_id required")
            return await self._sessions.find(shop_id, cid)

        if capability == Capability.UPDATE_CONVERSATION:
            cid = kwargs.get("conversation_id")
            if cid is None:
                raise ValueError("conversation_id required")
            return await self._sessions.update(
                shop_id,
                cid,
                patch=kwargs.get("patch"),
                ai=kwargs.get("ai"),
                message=kwargs.get("message"),
                decision=kwargs.get("decision"),
                workflow_entry=kwargs.get("workflow_entry"),
                current_workflow=kwargs.get("current_workflow"),
                assigned_advisor=kwargs.get("assigned_advisor"),
                priority=kwargs.get("priority"),
                status=kwargs.get("status"),
                customer_id=kwargs.get("customer_id"),
                vehicle_id=kwargs.get("vehicle_id"),
            )

        if capability == Capability.CLOSE_CONVERSATION:
            cid = kwargs.get("conversation_id")
            if cid is None:
                raise ValueError("conversation_id required")
            return await self._sessions.close(shop_id, cid)

        if capability == Capability.MERGE_CONVERSATION:
            primary = kwargs.get("primary_id") or kwargs.get("conversation_id")
            duplicates = list(kwargs.get("duplicate_ids") or [])
            if primary is None:
                raise ValueError("primary_id required")
            return await self._sessions.merge(shop_id, primary, duplicates)

        if capability == Capability.SEARCH_CONVERSATION:
            return await self._sessions.search(
                shop_id,
                customer_id=kwargs.get("customer_id"),
                channel=kwargs.get("channel"),
                status=kwargs.get("status"),
                query=kwargs.get("query"),
                limit=int(kwargs.get("limit") or 50),
            )

        if capability == Capability.CONVERSATION_HISTORY:
            cid = kwargs.get("conversation_id")
            if cid is None:
                raise ValueError("conversation_id required")
            return await self._messages.history(shop_id, cid)

        if capability == Capability.CONVERSATION_SUMMARY:
            cid = kwargs.get("conversation_id")
            if cid is None:
                raise ValueError("conversation_id required")
            conv = await self._sessions.find(shop_id, cid)
            if conv is None:
                raise LookupError(f"Conversation not found: {cid}")
            if kwargs.get("enrich"):
                ai = self._intelligence.enrich(
                    conv,
                    text=kwargs.get("text"),
                    intent=kwargs.get("intent"),
                    confidence=kwargs.get("confidence"),
                    escalate=bool(kwargs.get("escalate")),
                    owner_summary=kwargs.get("owner_summary") or kwargs.get("summary"),
                    suggested_reply=kwargs.get("suggested_reply"),
                    revenue_opportunity=kwargs.get("revenue_opportunity"),
                    risk_score=kwargs.get("risk_score"),
                    priority=kwargs.get("priority"),
                )
                if kwargs.get("persist", True):
                    highlights = list(kwargs.get("highlights") or ai.highlights)
                    action_items = list(kwargs.get("action_items") or ai.action_items)
                    ai.highlights = highlights
                    ai.action_items = action_items
                    conv = await self._sessions.update(shop_id, cid, ai=ai)
            return self._intelligence.summarize(conv)

        raise ValueError(f"Unknown conversation capability: {capability}")
