"""Retention decision builders — AI propose only, never contact customers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.agents.decisions.types import CustomerRetentionDecision, CustomerValueDecision
from app.revenue.intelligence.scorer import RevenueScorer


class RetentionDecisionFactory:
    def __init__(self, *, scorer: RevenueScorer | None = None) -> None:
        self._scorer = scorer or RevenueScorer()

    def from_risk(
        self,
        *,
        customer_id: UUID,
        churn_risk: float,
        lifetime_value: float = 0.0,
        days_inactive: int = 0,
        actions: list[str] | None = None,
        rationale: str = "",
    ) -> CustomerRetentionDecision:
        scored = self._scorer.score_retention_priority(
            churn_risk=churn_risk,
            lifetime_value=lifetime_value,
            days_inactive=days_inactive,
        )
        plan_actions = list(actions or [])
        if not plan_actions:
            if scored["priority"] in {"urgent", "high"}:
                plan_actions = [
                    "personal_check_in",
                    "service_reminder",
                    "review_declined_estimates",
                ]
            else:
                plan_actions = ["maintenance_nudge"]
        return CustomerRetentionDecision(
            customer_id=customer_id,
            risk_score=float(churn_risk),
            priority=scored["priority"],  # type: ignore[arg-type]
            plan=f"Retain customer (priority={scored['priority']})",
            actions=plan_actions,
            suggested_offer=None,  # AI must not apply discounts
            lifetime_value=lifetime_value,
            rationale=rationale or "Predicted churn risk from revenue intelligence",
        )

    def value_decision(
        self,
        *,
        customer_id: UUID,
        lifetime_value: float,
        health_score: float | None = None,
        churn_risk: float | None = None,
        rationale: str = "",
    ) -> CustomerValueDecision:
        return CustomerValueDecision(
            customer_id=customer_id,
            lifetime_value=lifetime_value,
            health_score=health_score,
            churn_risk=churn_risk,
            rationale=rationale or "Customer value analysis",
        )
