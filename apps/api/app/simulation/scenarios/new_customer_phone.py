"""Scenario 1 — New Customer Phone Request simulation."""

from __future__ import annotations

from app.simulation.models import ScenarioKind, SimulationRunResult
from app.simulation.scenarios.base import BaseScenario, ScenarioContext
from app.workflows.enums import DomainEventType


class NewCustomerPhoneScenario(BaseScenario):
    kind = ScenarioKind.NEW_CUSTOMER_PHONE

    async def run(self, ctx: ScenarioContext) -> SimulationRunResult:
        customer = ctx.gen.customer()
        vehicle = ctx.gen.vehicle(customer)
        repair = ctx.gen.repair_request(customer=customer, vehicle=vehicle, complaint="brake noise")
        conversation = ctx.gen.conversation(
            customer=customer,
            channel="phone",
            body=f"Hi, my {vehicle.make} has {repair.complaint}",
            intent="maintenance_question",
        )
        appointment = ctx.gen.appointment(
            customer=customer,
            vehicle=vehicle,
            repair_type=repair.recommended_service,
        )

        ctx.result.customer = customer
        ctx.result.vehicle = vehicle
        ctx.result.conversation = conversation
        ctx.result.repair = repair
        ctx.result.appointment = appointment
        ctx.result.retention_prediction = customer.retention_score
        ctx.result.appointment_converted = appointment.booked

        conf = ctx.gen.decision_confidence(0.84)
        ctx.add_decision("CustomerDecision", confidence=conf, accurate=True, summary="create by phone")
        ctx.add_decision(
            "VehicleDecision",
            confidence=ctx.gen.decision_confidence(0.7),
            accurate=bool(vehicle.vin),
            summary="vehicle from call context",
        )
        ctx.add_decision(
            "RepairRecommendationDecision",
            confidence=ctx.gen.decision_confidence(0.86),
            accurate=True,
            summary=repair.recommended_service,
        )
        ctx.add_decision(
            "AppointmentDecision",
            confidence=ctx.gen.decision_confidence(0.75),
            accurate=appointment.booked,
            summary="book" if appointment.booked else "noop",
        )
        ctx.add_decision(
            "CustomerCommunicationDecision",
            confidence=ctx.gen.decision_confidence(0.8),
            accurate=True,
            summary="SMS confirmation draft",
        )

        await ctx.invoke_capability("CreateConversation", plugin="conversation")
        await ctx.invoke_capability("AnalyzeConversation", plugin="advisor", text=conversation.body)

        await ctx.emit(
            DomainEventType.INBOUND_MESSAGE_RECEIVED,
            {
                "channel": "phone",
                "customer_id": str(customer.id),
                "vehicle_id": str(vehicle.id),
                "conversation_id": str(conversation.id),
                "body": conversation.body,
                "appointment_id": str(appointment.id) if appointment.booked else None,
                "estimated_revenue": str(repair.estimated_cost),
            },
        )

        if appointment.booked:
            await ctx.emit(
                DomainEventType.APPOINTMENT_BOOKED,
                {
                    "appointment_id": str(appointment.id),
                    "customer_id": str(customer.id),
                    "estimated_revenue": str(repair.estimated_cost),
                },
            )

        ctx.result.notes.append("Simulated phone repair request end-to-end")
        return ctx.finish()
