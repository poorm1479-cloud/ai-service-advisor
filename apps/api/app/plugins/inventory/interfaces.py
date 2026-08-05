"""Parts & Inventory Intelligence interfaces."""

from __future__ import annotations

from typing import Any, Protocol

from app.plugins.framework.context import PluginContext
from app.plugins.inventory.models import InventoryContext, InventoryPlan
from app.plugins.inventory.store import InventoryStore


class IInventoryPlugin(Protocol):
    def plugin_id(self) -> str: ...

    def supported_capabilities(self) -> list[str]: ...

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any: ...

    def build_context(self, **kwargs: Any) -> InventoryContext: ...

    def analyze(self, ctx: InventoryContext) -> InventoryPlan: ...

    @property
    def store(self) -> InventoryStore: ...

    async def health_check(self) -> dict[str, Any]: ...
