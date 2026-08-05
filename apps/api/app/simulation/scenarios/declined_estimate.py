"""Scenario 4 — Declined Estimate Recovery simulation."""

from __future__ import annotations

from app.simulation.models import ScenarioKind, SimulationRunResult
from app.simulation.scenarios.base import BaseScenario, ScenarioContext
from app.workflows.enums import DomainEventType


class DeclinedEstimateScenario(BaseScenario):
    kind = ScenarioKind.DECLINED_ESTIMATE

    async def run(self, ctx: ScenarioContext) -> SimulationRunResult:
        customer = ctx.gen.customer()
        vehicle = ctx.gen.vehicle(customer)
        estimate = ctx.gen.estimate(
            customer=customer,
            amount=ctx.gen.random().uniform(250, 1200),
            status="declined",
        )
        ctx.result.customer = customer
        ctx.result.vehicle = vehicle
        ctx.result.estimate = estimate
        ctx.result.retention_prediction = max(0.2, customer.retention_score - 0.15)
        ctx.result.revenue_opportunity_detected = True
        ctx.result.escalated = estimate.amount > 600

        ctx.add_decision(
            "RevenueDecision",
            confidence=ctx.gen.decision_confidence(0.82),
            accurate=True,
            summary="lost revenue detected",
        )
        ctx.add_decision(
            "RetentionDecision",
            confidence=ctx.gen.decision_confidence(0.76),
            accurate=True,
            summary="win-back plan",
        )
        ctx.add_decision(
            "CustomerCommunicationDecision",
            confidence=ctx.gen.decision_confidence(0.8),
            accurate=True,
            summary="recovery follow-up",
        )

        await ctx.invoke_capability("DetectRevenueOpportunity", plugin="revenue", run_analysis=False)
        await ctx.emit(
            DomainEventType.ESTIMATE_DECLINED,
            {
                "customer_id": str(customer.id),
                "vehicle_id": str(vehicle.id),
                "estimate_id": str(estimate.id),
                "estimated_revenue": str(estimate.amount),
            },
        )
        return ctx.finish()
