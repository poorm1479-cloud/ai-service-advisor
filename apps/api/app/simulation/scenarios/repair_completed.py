"""Scenario 6 — Repair Completed simulation."""

from __future__ import annotations

from app.simulation.models import ScenarioKind, SimulationRunResult
from app.simulation.scenarios.base import BaseScenario, ScenarioContext
from app.workflows.enums import DomainEventType


class RepairCompletedScenario(BaseScenario):
    kind = ScenarioKind.REPAIR_COMPLETED

    async def run(self, ctx: ScenarioContext) -> SimulationRunResult:
        customer = ctx.gen.customer()
        vehicle = ctx.gen.vehicle(customer)
        repair = ctx.gen.repair_request(customer=customer, vehicle=vehicle)
        payment = ctx.gen.payment(amount=repair.estimated_cost)
        estimate = ctx.gen.estimate(customer=customer, amount=repair.estimated_cost, status="approved")

        ctx.result.customer = customer
        ctx.result.vehicle = vehicle
        ctx.result.repair = repair
        ctx.result.payment = payment
        ctx.result.estimate = estimate
        ctx.result.retention_prediction = min(0.99, customer.retention_score + 0.05)
        ctx.result.revenue_opportunity_detected = True
        ctx.result.appointment_converted = True

        ctx.add_decision(
            "RepairStatusDecision",
            confidence=ctx.gen.decision_confidence(0.92),
            accurate=True,
            summary="completed",
        )
        ctx.add_decision(
            "ReviewRequestDecision",
            confidence=ctx.gen.decision_confidence(0.84),
            accurate=True,
            summary="ask for review",
        )
        ctx.add_decision(
            "MaintenanceReminderDecision",
            confidence=ctx.gen.decision_confidence(0.86),
            accurate=True,
            summary="schedule next service",
        )
        ctx.add_decision(
            "RevenueDecision",
            confidence=ctx.gen.decision_confidence(0.88),
            accurate=payment.paid,
            summary=f"payment={'paid' if payment.paid else 'due'}",
        )

        await ctx.invoke_capability("AddRepair", plugin="crm")
        await ctx.emit(
            DomainEventType.REPAIR_FINISHED,
            {
                "phase": "repair",
                "customer_id": str(customer.id),
                "vehicle_id": str(vehicle.id),
                "estimated_revenue": str(repair.estimated_cost),
                "invoice_id": str(payment.invoice_id),
                "paid": payment.paid,
            },
        )
        return ctx.finish()
