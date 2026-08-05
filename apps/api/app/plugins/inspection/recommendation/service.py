"""Repair recommendations and prioritization from inspection findings."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from app.agents.decisions.types import RepairRecommendationDecision
from app.plugins.inspection.models import FindingSeverity, InspectionContext, InspectionFinding, RepairPriority


_SEVERITY_URGENCY: dict[FindingSeverity, Literal["low", "normal", "high", "urgent"]] = {
    FindingSeverity.INFO: "low",
    FindingSeverity.OPTIONAL: "low",
    FindingSeverity.RECOMMENDED: "normal",
    FindingSeverity.SAFETY: "high",
    FindingSeverity.CRITICAL: "urgent",
}

_SEVERITY_PRIORITY: dict[FindingSeverity, RepairPriority] = {
    FindingSeverity.INFO: RepairPriority.LOW,
    FindingSeverity.OPTIONAL: RepairPriority.LOW,
    FindingSeverity.RECOMMENDED: RepairPriority.NORMAL,
    FindingSeverity.SAFETY: RepairPriority.HIGH,
    FindingSeverity.CRITICAL: RepairPriority.URGENT,
}


class RecommendationService:
    """Create / prioritize repair recommendations — Decision Objects only."""

    def recommend(self, ctx: InspectionContext) -> list[RepairRecommendationDecision]:
        out: list[RepairRecommendationDecision] = []
        for f in self._actionable(ctx.findings):
            out.append(self._to_decision(ctx, f))
        return out

    def prioritize(self, ctx: InspectionContext) -> list[RepairRecommendationDecision]:
        recs = self.recommend(ctx)
        order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        return sorted(recs, key=lambda d: (order.get(d.urgency, 9), -float(d.estimated_cost)))

    def estimate_suggestion(self, ctx: InspectionContext) -> dict[str, Any]:
        recs = self.prioritize(ctx)
        total = sum((r.estimated_cost for r in recs), Decimal("0.00"))
        line_items = [
            {
                "service": r.service_type,
                "title": r.title,
                "amount": str(r.estimated_cost),
                "urgency": r.urgency,
                "priority": _SEVERITY_PRIORITY.get(
                    next(
                        (f.severity for f in ctx.findings if f.title == r.title),
                        FindingSeverity.RECOMMENDED,
                    ),
                    RepairPriority.NORMAL,
                ).value,
            }
            for r in recs
        ]
        return {
            "line_items": line_items,
            "estimated_total": str(total),
            "count": len(line_items),
            "decisions": recs,
        }

    def _actionable(self, findings: list[InspectionFinding]) -> list[InspectionFinding]:
        skip = {FindingSeverity.INFO}
        return [f for f in findings if f.severity not in skip]

    def _to_decision(
        self, ctx: InspectionContext, f: InspectionFinding
    ) -> RepairRecommendationDecision:
        urgency = _SEVERITY_URGENCY[f.severity]
        plain = (
            f"{f.title}: {f.description or 'Needs service'} "
            f"(priority: {_SEVERITY_PRIORITY[f.severity].value})."
        )
        return RepairRecommendationDecision(
            customer_id=ctx.customer_id,
            vehicle_id=ctx.vehicle_id,
            service_type=f.recommended_service or f"{f.system}_service",
            title=f.title,
            description=f.description or f.title,
            estimated_cost=f.estimated_cost,
            urgency=urgency,
            plain_language=plain,
            advisor_notes=f.technician_notes or f"Inspection finding {f.code}",
            confidence=0.86,
            rationale=f"Inspection recommendation severity={f.severity.value}",
        )
