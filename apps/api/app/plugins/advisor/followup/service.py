"""Follow-up / maintenance / review — decide only."""

from __future__ import annotations

from typing import Any

from app.agents.decisions.types import (
    MaintenanceReminderDecision,
    ReviewRequestDecision,
)
from app.plugins.advisor.models import AdvisorContext


class AdvisorFollowUpService:
    def generate_follow_up(self, ctx: AdvisorContext) -> list[Any]:
        # Prefer maintenance reminders from revenue opportunities / metadata
        decisions: list[Any] = []
        reminders = list((ctx.metadata or {}).get("maintenance_reminders") or [])
        for rem in reminders[:2]:
            service = str(rem.get("service") or "service")
            due = rem.get("due_mileage")
            decisions.append(
                MaintenanceReminderDecision(
                    customer_id=ctx.customer_id,
                    vehicle_id=ctx.vehicle_id,
                    service=service,
                    due_mileage=str(due) if due is not None else None,
                    message_body=(
                        f"Friendly reminder: your {service.replace('_', ' ')} may be due"
                        + (f" around {due} miles" if due else "")
                        + ". Reply to book a convenient time."
                    ),
                    channel=ctx.channel or "sms",
                    confidence=0.7,
                    rationale="Maintenance reminder from advisor follow-up",
                )
            )
        intent = (ctx.intent or "").lower()
        if intent in {"thank_you", "completed", "pickup"} or (
            ctx.inbound_text and "thank" in ctx.inbound_text.lower()
        ):
            decisions.append(
                ReviewRequestDecision(
                    customer_id=ctx.customer_id,
                    channel=ctx.channel or "sms",
                    message_body=(
                        "Thanks for visiting us! If you have 30 seconds, a quick review "
                        "helps other drivers find a trusted shop."
                    ),
                    confidence=0.6,
                    rationale="Post-service review request",
                )
            )
        return decisions

    def generate_maintenance_reminder(
        self, ctx: AdvisorContext, *, service: str = "service", due_mileage: str | None = None
    ) -> list[Any]:
        return [
            MaintenanceReminderDecision(
                customer_id=ctx.customer_id,
                vehicle_id=ctx.vehicle_id,
                service=service,
                due_mileage=due_mileage,
                message_body=(
                    f"Reminder: {service.replace('_', ' ')} is coming due"
                    + (f" near {due_mileage} miles" if due_mileage else "")
                    + ". Want us to hold an appointment?"
                ),
                channel=ctx.channel or "sms",
                confidence=0.75,
                rationale="Explicit maintenance reminder generation",
            )
        ]

    def generate_review_request(self, ctx: AdvisorContext) -> list[Any]:
        return [
            ReviewRequestDecision(
                customer_id=ctx.customer_id,
                channel=ctx.channel or "sms",
                message_body=(
                    "We'd love your feedback! A short review helps us keep improving."
                ),
                confidence=0.7,
                rationale="Explicit review request generation",
            )
        ]
