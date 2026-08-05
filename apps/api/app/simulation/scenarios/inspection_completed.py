"""Scenario 3 — Inspection Completed simulation."""

from __future__ import annotations

from app.simulation.models import ScenarioKind, SimulationRunResult
from app.simulation.scenarios.base import BaseScenario, ScenarioContext
from app.workflows.enums import DomainEventType


class InspectionCompletedScenario(BaseScenario):
    kind = ScenarioKind.INSPECTION_COMPLETED

    async def run(self, ctx: ScenarioContext) -> SimulationRunResult:
        customer = ctx.gen.customer()
        vehicle = ctx.gen.vehicle(customer)
        inspection = ctx.gen.inspection(vehicle)
        estimate = ctx.gen.estimate(customer=customer, amount=ctx.gen.random().uniform(180, 900), status="sent")
        repair = ctx.gen.repair_request(customer=customer, vehicle=vehicle)

        ctx.result.customer = customer
        ctx.result.vehicle = vehicle
        ctx.result.inspection = inspection
        ctx.result.estimate = estimate
        ctx.result.repair = repair
        ctx.result.retention_prediction = customer.retention_score
        ctx.result.escalated = estimate.amount > 500

        ctx.add_decision(
            "RepairRecommendationDecision",
            confidence=ctx.gen.decision_confidence(0.87),
            accurate=True,
            summary=", ".join(inspection.findings),
        )
        ctx.add_decision(
            "EstimateExplanationDecision",
            confidence=ctx.gen.decision_confidence(0.85),
            accurate=True,
            summary=f"${estimate.amount}",
        )
        ctx.add_decision(
            "ApprovalRequestDecision",
            confidence=ctx.gen.decision_confidence(0.8),
            accurate=True,
            summary="awaiting customer approval",
        )
        ctx.add_decision(
            "CustomerCommunicationDecision",
            confidence=ctx.gen.decision_confidence(0.83),
            accurate=True,
            summary="plain-language inspection explanation",
        )

        await ctx.invoke_capability("AnalyzeConversation", plugin="advisor", text="inspection complete")
        await ctx.emit(
            DomainEventType.REPAIR_FINISHED,
            {
                "phase": "inspection",
                "customer_id": str(customer.id),
                "vehicle_id": str(vehicle.id),
                "inspection_id": str(inspection.id),
                "estimated_revenue": str(estimate.amount),
                "findings": inspection.findings,
            },
        )
        return ctx.finish()
