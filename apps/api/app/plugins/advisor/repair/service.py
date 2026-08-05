"""Repair recommendation / status — decide only."""

from __future__ import annotations

from typing import Any

from app.agents.decisions.types import RepairStatusDecision
from app.plugins.advisor.models import AdvisorContext


class AdvisorRepairService:
    def generate_update(self, ctx: AdvisorContext, *, status: str | None = None) -> list[Any]:
        text = (ctx.inbound_text or "").lower()
        st = status
        if st is None:
            if any(w in text for w in ("ready", "done", "finished", "complete")):
                st = "ready"
            elif any(w in text for w in ("status", "update", "progress", "where is")):
                st = "in_progress"
            else:
                return []
        messages = {
            "received": "We've received your vehicle and started the intake process.",
            "diagnosing": "Our technicians are diagnosing your vehicle now.",
            "awaiting_parts": "We're waiting on parts and will update you when work resumes.",
            "in_progress": "Repairs are in progress — we'll notify you when it's ready.",
            "ready": "Great news — your vehicle is ready for pickup.",
            "completed": "Your repair is complete. Thank you for choosing us.",
        }
        body = messages.get(st, messages["in_progress"])
        return [
            RepairStatusDecision(
                customer_id=ctx.customer_id,
                vehicle_id=ctx.vehicle_id,
                status=st,  # type: ignore[arg-type]
                message_body=body,
                channel=ctx.channel or "sms",
                advisor_notes=f"Status update decision: {st}",
                confidence=0.75,
                rationale="Repair status assistance",
            )
        ]
