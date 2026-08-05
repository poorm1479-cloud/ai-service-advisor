"""Churn / return risk prediction — wraps revenue_intel retention scoring."""

from __future__ import annotations

from typing import Any
from uuid import UUID


class RevenuePredictor:
    def __init__(self, *, service: Any) -> None:
        self._service = service

    async def predict_customer_risk(
        self, shop_id: UUID, customer_id: UUID | None = None, *, limit: int = 50
    ) -> dict[str, Any]:
        from app.plugins.revenue.retention.service import RetentionPluginService

        retention = RetentionPluginService(service=self._service)
        if customer_id is not None:
            ltv = await retention.calculate_customer_ltv(shop_id, customer_id)
            risk = float(ltv.get("churn_risk") or 0.0)
            band = "critical" if risk >= 0.7 else ("high" if risk >= 0.45 else "moderate")
            return {
                "customer_id": str(customer_id),
                "churn_risk": risk,
                "risk_band": band,
                "ltv": ltv,
                "ai_actions_allowed": False,
            }

        at_risk = await retention.customers_at_risk(shop_id)
        returns = await retention.predict_customer_return(shop_id, limit=limit)
        items = []
        for s in at_risk[:limit]:
            score = float(getattr(s, "score", 0) or 0)
            items.append(
                {
                    "customer_id": str(getattr(s, "entity_id", "")),
                    "health_score": score,
                    "churn_risk": round(max(0.0, (100.0 - score) / 100.0), 3),
                    "band": getattr(getattr(s, "band", None), "value", None),
                }
            )
        return {
            "shop_id": str(shop_id),
            "at_risk_count": len(items),
            "customers": items,
            "return_opportunities": len(returns),
            "ai_actions_allowed": False,
        }
