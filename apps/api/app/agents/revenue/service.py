"""Revenue Agent service."""

from __future__ import annotations

from decimal import Decimal

from app.agents.base.agent import Agent, AgentContext, AgentResult
from app.agents.revenue.models import (
    RevenueAnalysisRequest,
    RevenueInsights,
    UpsellOpportunity,
)

_SERVICE_REVENUE = {
    "oil_change": Decimal("79.99"),
    "tire_rotation": Decimal("49.99"),
    "cabin_filter": Decimal("89.99"),
    "brake_inspection": Decimal("129.99"),
    "transmission_service": Decimal("249.99"),
}


class RevenueAgent(Agent[RevenueAnalysisRequest, RevenueInsights]):
    name = "revenue"

    async def handle(
        self, payload: RevenueAnalysisRequest, context: AgentContext
    ) -> AgentResult[RevenueInsights]:
        return await self.analyze(payload, context)

    async def analyze(
        self, request: RevenueAnalysisRequest, context: AgentContext
    ) -> AgentResult[RevenueInsights]:
        upsells: list[UpsellOpportunity] = []
        reminders: list[dict] = []
        notes: list[str] = []

        for item in request.maintenance_timeline:
            if item.status in {"due_soon", "scheduled"}:
                est = _SERVICE_REVENUE.get(item.service, Decimal("99.00"))
                upsells.append(
                    UpsellOpportunity(
                        service=item.service,
                        reason=f"Maintenance {item.status} at {item.due_mileage} miles",
                        estimated_revenue=est,
                        priority="high" if item.status == "due_soon" else "medium",
                    )
                )
                reminders.append(
                    {
                        "service": item.service,
                        "due_mileage": item.due_mileage,
                        "status": item.status,
                    }
                )

        declined = list(request.declined_estimates)
        for est in declined:
            service = str(est.get("service", "unknown"))
            amount = Decimal(str(est.get("amount", "0")))
            upsells.append(
                UpsellOpportunity(
                    service=service,
                    reason="Previously declined estimate",
                    estimated_revenue=amount,
                    priority="high",
                )
            )

        lost_risk = 0.0
        if request.days_since_last_visit is not None:
            if request.days_since_last_visit > 365:
                lost_risk = 0.9
                notes.append("Customer inactive > 1 year — high churn risk.")
            elif request.days_since_last_visit > 180:
                lost_risk = 0.55
                notes.append("Customer inactive > 6 months.")
            elif request.days_since_last_visit > 90:
                lost_risk = 0.25

        predicted = sum((u.estimated_revenue for u in upsells), Decimal("0.00"))
        if request.intent == "price_question":
            notes.append("Price question — opportunity to present packaged maintenance.")

        insights = RevenueInsights(
            upsell_opportunities=upsells,
            declined_estimates=declined,
            maintenance_reminders=reminders,
            lost_customer_risk=lost_risk,
            predicted_revenue=predicted.quantize(Decimal("0.01")),
            notes=notes,
        )
        from app.agents.decisions.types import MarketingDecision, RevenueDecision

        marketing_actions: list[MarketingDecision] = []
        if reminders:
            r0 = reminders[0]
            marketing_actions.append(
                MarketingDecision(
                    action_type="maintenance_reminder",
                    channel="sms",
                    customer_id=request.customer_id or context.customer_id,
                    body="",  # composed by Marketing agent / executor template
                    context={
                        "service": r0.get("service", "service"),
                        "due_mileage": r0.get("due_mileage", "—"),
                    },
                    rationale="Revenue scored maintenance due — recommend reminder",
                )
            )
        insights.decision = RevenueDecision(
            upsell_opportunities=[
                {
                    "service": u.service,
                    "reason": u.reason,
                    "estimated_revenue": str(u.estimated_revenue),
                    "priority": u.priority,
                }
                for u in upsells
            ],
            declined_estimates=declined,
            maintenance_reminders=reminders,
            lost_customer_risk=lost_risk,
            predicted_revenue=insights.predicted_revenue,
            notes=notes,
            marketing_actions=marketing_actions,
            rationale="Revenue opportunity / risk scoring",
        )
        return AgentResult.ok(insights)
