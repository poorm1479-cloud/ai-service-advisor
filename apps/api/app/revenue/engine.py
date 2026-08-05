"""Phase 20 Revenue Intelligence engine — wraps revenue_intel, proposes Decisions only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.revenue.decisions.campaign import CampaignDecisionFactory
from app.revenue.decisions.opportunity import OpportunityDecisionFactory
from app.revenue.decisions.retention import RetentionDecisionFactory
from app.revenue.intelligence.analyzer import RevenueAnalyzer
from app.revenue.intelligence.predictor import RevenuePredictor
from app.revenue.intelligence.scorer import RevenueScorer
from app.revenue.recommendations.service import ServiceRecommendationService
from app.revenue.recommendations.timing import ContactTimingService
from app.revenue.store import InMemoryRetentionInsightStore, RetentionInsightStorePort


@dataclass(slots=True)
class RetentionInsight:
    shop_id: UUID
    customer_id: UUID | None
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


class RevenueIntelligenceEngine:
    """Orchestrates Phase 20 analysis + decision proposals (no marketing/CRM writes)."""

    def __init__(
        self,
        *,
        service: Any,
        insight_store: RetentionInsightStorePort | None = None,
    ) -> None:
        self._service = service
        self.analyzer = RevenueAnalyzer(service=service)
        self.predictor = RevenuePredictor(service=service)
        self.scorer = RevenueScorer()
        self.service_recs = ServiceRecommendationService(service=service)
        self.timing = ContactTimingService()
        self.retention_factory = RetentionDecisionFactory(scorer=self.scorer)
        self.opportunity_factory = OpportunityDecisionFactory(scorer=self.scorer)
        self.campaign_factory = CampaignDecisionFactory()
        self._insights = insight_store or InMemoryRetentionInsightStore()

    @property
    def insights(self) -> RetentionInsightStorePort:
        return self._insights

    async def analyze_customer_value(
        self, shop_id: UUID, customer_id: UUID | None = None
    ) -> dict[str, Any]:
        return await self.analyzer.analyze_customer_value(shop_id, customer_id)

    async def predict_customer_risk(
        self, shop_id: UUID, customer_id: UUID | None = None, *, limit: int = 50
    ) -> dict[str, Any]:
        return await self.predictor.predict_customer_risk(
            shop_id, customer_id, limit=limit
        )

    async def detect_revenue_opportunity(
        self, shop_id: UUID, *, run_analysis: bool = False, limit: int = 100
    ) -> dict[str, Any]:
        return await self.analyzer.detect_opportunities(
            shop_id, run_analysis=run_analysis, limit=limit
        )

    async def recommend_service(self, shop_id: UUID, *, limit: int = 50) -> dict[str, Any]:
        return await self.service_recs.recommend_service(shop_id, limit=limit)

    async def recommend_contact_timing(
        self,
        shop_id: UUID,
        *,
        customer_id: UUID | None = None,
        channel: str = "sms",
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.timing.recommend_contact_timing(
            shop_id,
            customer_id=customer_id,
            channel=channel,
            preferences=preferences,
        )

    async def create_retention_plan(
        self, shop_id: UUID, customer_id: UUID
    ) -> dict[str, Any]:
        risk = await self.predict_customer_risk(shop_id, customer_id)
        ltv = float((risk.get("ltv") or {}).get("lifetime_value") or 0)
        decision = self.retention_factory.from_risk(
            customer_id=customer_id,
            churn_risk=float(risk.get("churn_risk") or 0),
            lifetime_value=ltv,
        )
        await self._insights.record(
            shop_id,
            kind="retention_plan",
            customer_id=customer_id,
            payload={
                "risk_score": decision.risk_score,
                "plan": decision.plan,
                "actions": list(decision.actions),
                "priority": decision.priority,
            },
        )
        return {"decision": decision, "risk": risk, "ai_actions_allowed": False}

    async def analyze_lost_revenue(self, shop_id: UUID, *, limit: int = 100) -> dict[str, Any]:
        return await self.analyzer.analyze_lost_revenue(shop_id, limit=limit)

    async def generate_campaign_suggestion(
        self,
        shop_id: UUID,
        *,
        customer_id: UUID | None = None,
        campaign_type: str = "retention",
        channel: str = "sms",
    ) -> dict[str, Any]:
        decision = self.campaign_factory.suggest_campaign(
            customer_id=customer_id,
            campaign_type=campaign_type,
            channel=channel,
            message_draft="We miss you — book your next service when you're ready.",
        )
        await self._insights.record(
            shop_id,
            kind="campaign_suggestion",
            customer_id=customer_id,
            payload={
                "campaign_type": campaign_type,
                "channel": channel,
                "auto_send": False,
                "message_draft": decision.message_draft,
            },
        )
        return {"decision": decision, "ai_actions_allowed": False, "auto_send": False}

    async def dashboard_metrics(self, shop_id: UUID) -> dict[str, Any]:
        lost = await self.analyze_lost_revenue(shop_id, limit=50)
        risk = await self.predict_customer_risk(shop_id, limit=50)
        opps = await self.detect_revenue_opportunity(shop_id, run_analysis=False, limit=50)
        insights = await self._insights.list_for_shop(shop_id, limit=200)
        retention_plans = [i for i in insights if i.get("kind") == "retention_plan"]
        campaigns = [i for i in insights if i.get("kind") == "campaign_suggestion"]
        recovered = [i for i in insights if i.get("kind") == "recovered_revenue"]
        at_risk = int(risk.get("at_risk_count") or 0)
        # Simple retention proxy: 1 - at_risk / max(customers,1)
        customers = max(len(risk.get("customers") or []), 1)
        retention_rate = round(max(0.0, 1.0 - (at_risk / customers)), 4)
        return {
            "customer_retention_rate": retention_rate,
            "lost_customer_risk": at_risk,
            "revenue_opportunities": int(opps.get("count") or 0),
            "recovered_revenue": len(recovered),
            "service_recommendations": int(
                (await self.recommend_service(shop_id, limit=20)).get("count") or 0
            ),
            "campaign_performance": {
                "suggestions": len(campaigns),
                "sent": 0,  # AI/engine never sends
                "auto_send_blocked": True,
            },
            "lost_revenue_estimate": lost.get("total_lost_revenue_estimate"),
            "retention_plans": len(retention_plans),
        }
