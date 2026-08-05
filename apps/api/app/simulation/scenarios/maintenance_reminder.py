"""Scenario 2 — Maintenance Reminder simulation."""

from __future__ import annotations

from app.simulation.models import ScenarioKind, SimulationRunResult
from app.simulation.scenarios.base import BaseScenario, ScenarioContext
from app.workflows.enums import DomainEventType


class MaintenanceReminderScenario(BaseScenario):
    kind = ScenarioKind.MAINTENANCE_REMINDER

    async def run(self, ctx: ScenarioContext) -> SimulationRunResult:
        customer = ctx.gen.customer()
        vehicle = ctx.gen.vehicle(customer)
        ctx.result.customer = customer
        ctx.result.vehicle = vehicle
        ctx.result.retention_prediction = customer.retention_score
        ctx.result.revenue_opportunity_detected = vehicle.health_score < 75

        ctx.add_decision(
            "MaintenanceReminderDecision",
            confidence=ctx.gen.decision_confidence(0.88),
            accurate=True,
            summary=f"due near {vehicle.mileage + 1000}",
        )
        ctx.add_decision(
            "RetentionDecision",
            confidence=ctx.gen.decision_confidence(0.79),
            accurate=customer.retention_score > 0.5,
            summary=f"retention={customer.retention_score}",
        )
        ctx.add_decision(
            "RevenueDecision",
            confidence=ctx.gen.decision_confidence(0.77),
            accurate=ctx.result.revenue_opportunity_detected,
            summary="maintenance upsell",
        )
        ctx.add_decision(
            "MarketingDecision",
            confidence=ctx.gen.decision_confidence(0.81),
            accurate=True,
            summary="sms maintenance campaign",
        )

        await ctx.invoke_capability("CalculateVehicleHealth", plugin="revenue", vehicle_id=str(vehicle.id))
        await ctx.invoke_capability("CalculateCustomerHealth", plugin="revenue", customer_id=str(customer.id))

        await ctx.emit(
            DomainEventType.MAINTENANCE_REMINDER_REQUESTED,
            {
                "customer_id": str(customer.id),
                "vehicle_id": str(vehicle.id),
                "health_score": vehicle.health_score,
                "service": "oil_change",
            },
        )
        return ctx.finish()
