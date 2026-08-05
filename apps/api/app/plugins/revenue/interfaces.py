"""Revenue Plugin ports — Workflow uses IRevenuePlugin via Capability Registry only."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.plugins.framework.context import PluginContext
from app.plugins.revenue.models import RevenueOpportunity


class OpportunityServicePort(Protocol):
    async def detect(
        self, shop_id: UUID, *, run_analysis: bool = True, limit: int = 200
    ) -> list[RevenueOpportunity]: ...

    async def find_declined(
        self, shop_id: UUID, *, limit: int = 100
    ) -> list[RevenueOpportunity]: ...


class IRevenuePlugin(Protocol):
    def plugin_id(self) -> str: ...

    async def live_snapshot(self, shop_id: UUID, **kwargs: Any) -> dict[str, Any]: ...

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any: ...
