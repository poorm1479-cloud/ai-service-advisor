"""Evaluate decision outcomes and compute accuracy metrics."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.learning.models.decision_result import DecisionResultRecord, OutcomeKind
from app.learning.store import LearningStorePort


class LearningEvaluator:
    def __init__(self, store: LearningStorePort) -> None:
        self._store = store

    async def evaluate_decision(
        self,
        shop_id: UUID,
        *,
        decision_kind: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        results = await self._store.list_results(
            shop_id, limit=limit, decision_kind=decision_kind
        )
        return self._summarize(shop_id, results, decision_kind=decision_kind)

    async def metrics(self, shop_id: UUID, *, limit: int = 500) -> dict[str, Any]:
        results = await self._store.list_results(shop_id, limit=limit)
        by_outcome: dict[str, list[DecisionResultRecord]] = {}
        for r in results:
            by_outcome.setdefault(r.outcome_kind.value, []).append(r)

        def rate(items: list[DecisionResultRecord]) -> float:
            if not items:
                return 0.0
            return round(sum(1 for i in items if i.success) / len(items), 4)

        appt = by_outcome.get(OutcomeKind.APPOINTMENT_CONVERSION.value, [])
        repair = by_outcome.get(OutcomeKind.REPAIR_APPROVAL.value, [])
        retention = by_outcome.get(OutcomeKind.CUSTOMER_RESPONSE.value, [])
        revenue = by_outcome.get(OutcomeKind.REVENUE.value, [])

        overall = self._summarize(shop_id, results)
        return {
            "decision_accuracy": overall["accuracy"],
            "appointment_conversion_improvement": rate(appt),
            "repair_approval_rate": rate(repair),
            "customer_retention_improvement": rate(retention),
            "revenue_impact": {
                "success_rate": rate(revenue),
                "samples": len(revenue),
                "avg_score": round(
                    sum(r.score for r in revenue) / len(revenue), 4
                )
                if revenue
                else 0.0,
            },
            "sample_count": len(results),
            "ai_actions_allowed": False,
        }

    def _summarize(
        self,
        shop_id: UUID,
        results: list[DecisionResultRecord],
        *,
        decision_kind: str | None = None,
    ) -> dict[str, Any]:
        total = len(results)
        successes = sum(1 for r in results if r.success)
        accuracy = round(successes / total, 4) if total else 0.0
        by_kind: dict[str, dict[str, Any]] = {}
        for r in results:
            bucket = by_kind.setdefault(
                r.decision_kind, {"total": 0, "success": 0, "avg_score": 0.0}
            )
            bucket["total"] += 1
            bucket["success"] += 1 if r.success else 0
            bucket["avg_score"] += r.score
        for bucket in by_kind.values():
            t = bucket["total"] or 1
            bucket["accuracy"] = round(bucket["success"] / t, 4)
            bucket["avg_score"] = round(bucket["avg_score"] / t, 4)
        return {
            "shop_id": str(shop_id),
            "decision_kind": decision_kind,
            "total": total,
            "successes": successes,
            "accuracy": accuracy,
            "by_decision_kind": by_kind,
            "ai_actions_allowed": False,
        }
