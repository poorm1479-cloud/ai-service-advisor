"""Service recommendation orchestration — wraps plugin recommendations."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.revenue.decisions.opportunity import OpportunityDecisionFactory


class ServiceRecommendationService:
    def __init__(self, *, service: Any) -> None:
        self._service = service
        self._factory = OpportunityDecisionFactory()

    async def recommend_service(
        self, shop_id: UUID, *, limit: int = 50
    ) -> dict[str, Any]:
        from app.plugins.revenue.recommendations.service import RecommendationsPluginService

        recs = RecommendationsPluginService(service=self._service)
        upsells = await recs.generate_upsells(shop_id, limit=limit)
        cross = await recs.generate_cross_sells(shop_id, limit=limit)
        decisions = []
        for item in list(upsells) + list(cross):
            decisions.append(
                self._factory.service_recommendation(
                    customer_id=_as_uuid(getattr(item, "customer_id", None)),
                    vehicle_id=_as_uuid(getattr(item, "vehicle_id", None)),
                    service=str(
                        getattr(item, "service_type", None)
                        or getattr(item, "title", None)
                        or "service"
                    ),
                    reason=str(getattr(item, "summary", None) or getattr(item, "rationale", "") or ""),
                    expected_revenue=float(
                        getattr(item, "expected_revenue", None)
                        or getattr(item, "estimated_value", 0)
                        or 0
                    ),
                )
            )
        return {
            "shop_id": str(shop_id),
            "count": len(decisions),
            "decisions": decisions,
            "upsell_count": len(upsells) if hasattr(upsells, "__len__") else 0,
            "cross_sell_count": len(cross) if hasattr(cross, "__len__") else 0,
            "ai_actions_allowed": False,
        }


def _as_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None
