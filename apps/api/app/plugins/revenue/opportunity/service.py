"""Opportunity detection — wraps RevenueIntelService / engine."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.revenue.models import RevenueOpportunity, from_intel_opportunity
from app.revenue_intel.enums import OpportunityKind, OpportunityStatus


class OpportunityPluginService:
    def __init__(self, *, service: Any, engine: Any | None = None, store: Any | None = None) -> None:
        self._service = service
        self._engine = engine
        self._store = store

    async def detect(
        self, shop_id: UUID, *, run_analysis: bool = True, limit: int = 200
    ) -> list[RevenueOpportunity]:
        if run_analysis:
            await self._service.run_nightly_analysis(shop_id)
        opps = await self._service.list_opportunities(
            shop_id, status=OpportunityStatus.OPEN, limit=limit
        )
        return [from_intel_opportunity(o) for o in opps]

    async def list_open(
        self, shop_id: UUID, *, kind: str | None = None, limit: int = 200
    ) -> list[RevenueOpportunity]:
        kind_enum = None
        if kind:
            try:
                kind_enum = OpportunityKind(kind)
            except ValueError:
                kind_enum = None
        opps = await self._service.list_opportunities(
            shop_id, kind=kind_enum, status=OpportunityStatus.OPEN, limit=limit
        )
        return [from_intel_opportunity(o) for o in opps]

    async def find_declined(self, shop_id: UUID, *, limit: int = 100) -> list[RevenueOpportunity]:
        return await self.list_open(
            shop_id, kind=OpportunityKind.DECLINED_ESTIMATE.value, limit=limit
        )
