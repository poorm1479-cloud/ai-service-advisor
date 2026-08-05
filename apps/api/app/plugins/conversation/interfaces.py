"""Conversation Plugin ports — Workflow uses ConversationId via IConversationPlugin."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.plugins.conversation.models import Conversation, ConversationMessage
from app.plugins.framework.context import PluginContext


class ConversationSessionPort(Protocol):
    async def create(self, shop_id: UUID, **kwargs: Any) -> Conversation: ...

    async def find(self, shop_id: UUID, conversation_id: UUID) -> Conversation | None: ...

    async def update(self, shop_id: UUID, conversation_id: UUID, **kwargs: Any) -> Conversation: ...

    async def close(self, shop_id: UUID, conversation_id: UUID) -> Conversation: ...

    async def merge(
        self, shop_id: UUID, primary_id: UUID, duplicate_ids: list[UUID]
    ) -> Conversation: ...

    async def search(self, shop_id: UUID, **kwargs: Any) -> list[Conversation]: ...


class ConversationMessagePort(Protocol):
    async def append(
        self, shop_id: UUID, conversation_id: UUID, message: Any
    ) -> Conversation: ...

    async def history(
        self, shop_id: UUID, conversation_id: UUID
    ) -> list[ConversationMessage]: ...


class IConversationPlugin(Protocol):
    """Conversation Plugin contract — sole conversation entry for Workflow Engine."""

    def plugin_id(self) -> str: ...

    @property
    def sessions(self) -> ConversationSessionPort: ...

    @property
    def messages(self) -> ConversationMessagePort: ...

    def get_adapter(self, channel: str) -> Any: ...

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any: ...
