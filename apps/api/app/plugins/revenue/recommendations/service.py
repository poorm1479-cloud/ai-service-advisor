"""Upsell / cross-sell recommendations — wraps messaging + opportunity kinds."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.revenue.models import RevenueOpportunity, from_intel_opportunity
from app.revenue_intel.enums import OpportunityKind, OpportunityStatus


_UPSELL_KINDS = {
    OpportunityKind.BRAKES,
    OpportunityKind.BATTERY,
    OpportunityKind.TIRES,
    OpportunityKind.LIKELY_ACCEPT,
}

_CROSS_SELL_KINDS = {
    OpportunityKind.ALIGNMENT,
    OpportunityKind.FLUIDS,
    OpportunityKind.OIL_CHANGE,
    OpportunityKind.MAINTENANCE_OVERDUE,
}


class RecommendationsPluginService:
    def __init__(self, *, service: Any) -> None:
        self._service = service

    async def generate_upsells(
        self, shop_id: UUID, *, limit: int = 50
    ) -> list[RevenueOpportunity]:
        open_opps = await self._service.list_opportunities(
            shop_id, status=OpportunityStatus.OPEN, limit=500
        )
        items = [o for o in open_opps if o.kind in _UPSELL_KINDS]
        items.sort(key=lambda o: float(o.expected_revenue) * o.probability, reverse=True)
        return [from_intel_opportunity(o) for o in items[:limit]]

    async def generate_cross_sells(
        self, shop_id: UUID, *, limit: int = 50
    ) -> list[RevenueOpportunity]:
        open_opps = await self._service.list_opportunities(
            shop_id, status=OpportunityStatus.OPEN, limit=500
        )
        items = [o for o in open_opps if o.kind in _CROSS_SELL_KINDS]
        items.sort(key=lambda o: float(o.expected_revenue) * o.probability, reverse=True)
        return [from_intel_opportunity(o) for o in items[:limit]]
