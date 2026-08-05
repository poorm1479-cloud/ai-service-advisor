"""Customer / opportunity / lost-revenue analysis — wraps revenue_intel."""

from __future__ import annotations

from typing import Any
from uuid import UUID


class RevenueAnalyzer:
    """Analyze customer value, lost revenue, and opportunity signals (decide-support)."""

    def __init__(self, *, service: Any) -> None:
        self._service = service

    async def analyze_customer_value(
        self, shop_id: UUID, customer_id: UUID | None = None
    ) -> dict[str, Any]:
        from app.plugins.revenue.retention.service import RetentionPluginService

        retention = RetentionPluginService(service=self._service)
        if customer_id is not None:
            ltv = await retention.calculate_customer_ltv(shop_id, customer_id)
            health = await retention.calculate_customer_health(shop_id, customer_id)
            return {
                "customer_id": str(customer_id),
                "ltv": ltv,
                "health": _score_dict(health),
                "ai_actions_allowed": False,
            }
        scores = await retention.calculate_customer_health(shop_id, None)
        items = [_score_dict(s) for s in (scores or [])]
        return {
            "shop_id": str(shop_id),
            "customers": items,
            "count": len(items),
            "ai_actions_allowed": False,
        }

    async def analyze_lost_revenue(self, shop_id: UUID, *, limit: int = 100) -> dict[str, Any]:
        from app.revenue_intel.enums import OpportunityKind, OpportunityStatus

        lost = await self._service.list_opportunities(
            shop_id,
            kind=OpportunityKind.LOST_CUSTOMER,
            status=OpportunityStatus.OPEN,
            limit=limit,
        )
        declined = await self._service.list_opportunities(
            shop_id,
            kind=OpportunityKind.DECLINED_ESTIMATE,
            status=OpportunityStatus.OPEN,
            limit=limit,
        )
        lost_amount = _sum_expected(lost)
        declined_amount = _sum_expected(declined)
        return {
            "shop_id": str(shop_id),
            "lost_customers": len(lost),
            "declined_estimates": len(declined),
            "lost_revenue_estimate": str(lost_amount),
            "declined_revenue_estimate": str(declined_amount),
            "total_lost_revenue_estimate": str(lost_amount + declined_amount),
            "opportunities": [_opp_brief(o) for o in list(lost) + list(declined)],
            "ai_actions_allowed": False,
        }

    async def detect_opportunities(
        self, shop_id: UUID, *, run_analysis: bool = False, limit: int = 100
    ) -> dict[str, Any]:
        if run_analysis:
            report = await self._service.run_nightly_analysis(shop_id)
            opps = list(report.opportunities)[:limit]
        else:
            opps = await self._service.list_opportunities(shop_id, limit=limit)
        return {
            "shop_id": str(shop_id),
            "count": len(opps),
            "opportunities": [_opp_brief(o) for o in opps],
            "ai_actions_allowed": False,
        }


def _score_dict(score: Any) -> dict[str, Any]:
    if score is None:
        return {}
    if isinstance(score, dict):
        return score
    return {
        "entity_id": str(getattr(score, "entity_id", "")),
        "score": getattr(score, "score", None),
        "band": getattr(getattr(score, "band", None), "value", getattr(score, "band", None)),
        "factors": dict(getattr(score, "factors", None) or {}),
        "notes": list(getattr(score, "notes", None) or []),
    }


def _sum_expected(opps: list[Any]) -> Any:
    from decimal import Decimal

    total = Decimal("0.00")
    for o in opps:
        val = getattr(o, "expected_revenue", None) or getattr(o, "estimated_value", None)
        if val is None:
            continue
        total += Decimal(str(val))
    return total


def _opp_brief(o: Any) -> dict[str, Any]:
    kind = getattr(o, "kind", None)
    return {
        "id": str(getattr(o, "id", "")),
        "customer_id": str(getattr(o, "customer_id", "") or ""),
        "kind": getattr(kind, "value", kind),
        "title": getattr(o, "title", None) or getattr(o, "summary", ""),
        "expected_revenue": str(
            getattr(o, "expected_revenue", None) or getattr(o, "estimated_value", "") or ""
        ),
        "priority": getattr(o, "priority", None),
    }
