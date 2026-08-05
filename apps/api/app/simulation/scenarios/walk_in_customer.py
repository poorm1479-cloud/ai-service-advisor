"""Scenario 5 — Walk-in Customer simulation."""

from __future__ import annotations

from uuid import uuid4

from app.simulation.models import ScenarioKind, SimulationRunResult
from app.simulation.scenarios.base import BaseScenario, ScenarioContext
from app.workflows.enums import DomainEventType


class WalkInCustomerScenario(BaseScenario):
    kind = ScenarioKind.WALK_IN

    async def run(self, ctx: ScenarioContext) -> SimulationRunResult:
        # Temporary intake — customer may be None initially then merged
        vehicle = ctx.gen.vehicle(None)
        repair = ctx.gen.repair_request(customer=None, vehicle=vehicle)
        customer = ctx.gen.customer()  # merge target
        vehicle.customer_id = customer.id
        repair.customer_id = customer.id

        ctx.result.customer = customer
        ctx.result.vehicle = vehicle
        ctx.result.repair = repair
        ctx.result.retention_prediction = customer.retention_score
        ctx.result.escalated = True  # merge pending

        ctx.add_decision(
            "VehicleDecision",
            confidence=ctx.gen.decision_confidence(0.9),
            accurate=True,
            summary=vehicle.vin,
        )
        ctx.add_decision(
            "CustomerDecision",
            confidence=ctx.gen.decision_confidence(0.7),
            accurate=True,
            summary="temporary → merge",
        )
        ctx.add_decision(
            "RepairRecommendationDecision",
            confidence=ctx.gen.decision_confidence(0.78),
            accurate=True,
            summary=repair.recommended_service,
        )

        await ctx.invoke_capability("CreateVehicle", plugin="crm")
        await ctx.emit(
            DomainEventType.WALK_IN_CREATED,
            {
                "visit_id": str(uuid4()),
                "vehicle_id": str(vehicle.id),
                "customer_id": str(customer.id),
                "complaint": repair.complaint,
                "vin": vehicle.vin,
            },
        )
        return ctx.finish()
