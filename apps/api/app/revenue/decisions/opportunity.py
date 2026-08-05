"""Revenue opportunity decision builders — AI propose only."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.agents.decisions.types import (
    RevenueOpportunityDecision,
    ServiceRecommendationDecision,
)
from app.revenue.intelligence.scorer import RevenueScorer


class OpportunityDecisionFactory:
    def __init__(self, *, scorer: RevenueScorer | None = None) -> None:
        self._scorer = scorer or RevenueScorer()

    def from_opportunity(
        self,
        *,
        customer_id: UUID | None,
        kind: str,
        title: str,
        expected_revenue: float = 0.0,
        probability: float = 0.5,
        vehicle_id: UUID | None = None,
        rationale: str = "",
    ) -> RevenueOpportunityDecision:
        scored = self._scorer.score_opportunity(
            expected_revenue=expected_revenue, probability=probability
        )
        return RevenueOpportunityDecision(
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            opportunity_kind=kind,
            title=title,
            expected_revenue=expected_revenue,
            probability=probability,
            opportunity_score=scored["opportunity_score"],
            rationale=rationale or title,
        )

    def service_recommendation(
        self,
        *,
        customer_id: UUID | None,
        vehicle_id: UUID | None,
        service: str,
        reason: str,
        expected_revenue: float = 0.0,
        urgency: str = "normal",
    ) -> ServiceRecommendationDecision:
        return ServiceRecommendationDecision(
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            service=service,
            reason=reason,
            expected_revenue=expected_revenue,
            urgency=urgency,  # type: ignore[arg-type]
            rationale=reason,
        )
