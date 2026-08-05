"""Opportunity / retention priority scoring helpers."""

from __future__ import annotations

from typing import Any


class RevenueScorer:
    """Score retention plans and opportunities for prioritization (no side effects)."""

    def score_retention_priority(
        self, *, churn_risk: float, lifetime_value: float, days_inactive: int = 0
    ) -> dict[str, Any]:
        risk = max(0.0, min(1.0, float(churn_risk)))
        clv = max(0.0, float(lifetime_value))
        inactivity = min(1.0, max(0.0, days_inactive) / 365.0)
        score = round((risk * 0.5 + inactivity * 0.2) * (1.0 + min(clv / 5000.0, 1.0) * 0.3), 4)
        if score >= 0.75:
            priority = "urgent"
        elif score >= 0.5:
            priority = "high"
        elif score >= 0.3:
            priority = "normal"
        else:
            priority = "low"
        return {
            "priority_score": score,
            "priority": priority,
            "churn_risk": risk,
            "lifetime_value": clv,
            "days_inactive": days_inactive,
        }

    def score_opportunity(
        self, *, expected_revenue: float, probability: float = 0.5, urgency: float = 0.5
    ) -> dict[str, Any]:
        rev = max(0.0, float(expected_revenue))
        prob = max(0.0, min(1.0, float(probability)))
        urg = max(0.0, min(1.0, float(urgency)))
        score = round(rev * prob * (0.7 + 0.3 * urg), 2)
        return {
            "opportunity_score": score,
            "expected_revenue": rev,
            "probability": prob,
            "urgency": urg,
        }
