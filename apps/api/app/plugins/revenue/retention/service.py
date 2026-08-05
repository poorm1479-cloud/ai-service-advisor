"""Retention / health / CLV — wraps revenue_intel.scoring."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.plugins.revenue.models import RevenueOpportunity, from_intel_opportunity
from app.revenue_intel.enums import OpportunityKind, OpportunityStatus
from app.revenue_intel.scoring import estimate_clv, score_customer, score_vehicle


class RetentionPluginService:
    def __init__(self, *, service: Any, store: Any | None = None) -> None:
        self._service = service
        self._store = store or getattr(service, "_store", None)

    async def calculate_customer_health(
        self, shop_id: UUID, customer_id: UUID | None = None
    ) -> list[Any] | Any:
        scores = await self._service.list_scores(shop_id, entity_type="customer")
        if customer_id is not None:
            match = next((s for s in scores if s.entity_id == customer_id), None)
            if match is not None:
                return match
            customer = await self._load_customer(shop_id, customer_id)
            if customer is not None:
                return score_customer(customer)
            return None
        return scores

    async def calculate_customer_ltv(
        self, shop_id: UUID, customer_id: UUID
    ) -> dict[str, Any]:
        customer = await self._load_customer(shop_id, customer_id)
        if customer is None:
            return {
                "customer_id": str(customer_id),
                "lifetime_value": "0.00",
                "found": False,
            }
        clv = estimate_clv(customer)
        health = score_customer(customer)
        return {
            "customer_id": str(customer_id),
            "lifetime_value": str(clv),
            "health_score": health.score,
            "health_band": health.band.value,
            "churn_risk": round(max(0.0, (100.0 - health.score) / 100.0), 3),
            "found": True,
        }

    async def predict_customer_return(
        self, shop_id: UUID, *, limit: int = 100
    ) -> list[RevenueOpportunity]:
        opps = await self._service.list_opportunities(
            shop_id,
            kind=OpportunityKind.LIKELY_RETURN,
            status=OpportunityStatus.OPEN,
            limit=limit,
        )
        lost = await self._service.list_opportunities(
            shop_id,
            kind=OpportunityKind.LOST_CUSTOMER,
            status=OpportunityStatus.OPEN,
            limit=limit,
        )
        return [from_intel_opportunity(o) for o in list(opps) + list(lost)]

    async def customers_at_risk(self, shop_id: UUID) -> list[Any]:
        scores = await self._service.list_scores(shop_id, entity_type="customer")
        return [s for s in scores if s.score < 50]

    async def _load_customer(self, shop_id: UUID, customer_id: UUID) -> Any | None:
        if self._store is None:
            return None
        if hasattr(self._store, "get_customer"):
            return await self._store.get_customer(shop_id, customer_id)
        customers = await self._store.list_customers(shop_id)
        return next((c for c in customers if c.id == customer_id), None)
