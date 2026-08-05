"""Customer explanations from inspection findings — plain language only."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.agents.decisions.types import (
    CustomerExplanationDecision,
    SafetyAlertDecision,
)
from app.plugins.inspection.models import FindingSeverity, InspectionContext
from app.plugins.inspection.templates import render_template


class ExplanationService:
    """Generate customer-facing explanations — Decision Objects only."""

    def explain(self, ctx: InspectionContext, *, safety_alerts: list[Any] | None = None) -> list[Any]:
        vehicle = self._vehicle_label(ctx)
        decisions: list[Any] = []
        alerts = safety_alerts or []

        for alert in alerts:
            if isinstance(alert, SafetyAlertDecision):
                body = render_template(
                    "safety_warning",
                    vehicle=vehicle,
                    issue=alert.issue or alert.title,
                    amount=self._amount_for_title(ctx, alert.title),
                )
                decisions.append(
                    CustomerExplanationDecision(
                        customer_id=ctx.customer_id,
                        vehicle_id=ctx.vehicle_id,
                        inspection_id=ctx.inspection_id
                        or (ctx.inspection.id if ctx.inspection else None),
                        template="safety_warning",
                        category="safety",
                        title=alert.title,
                        plain_language=body,
                        channel=ctx.channel,
                        urgency="urgent" if alert.urgent else "high",
                        confidence=0.9,
                        rationale="Safety warning explanation from inspection",
                    )
                )

        for f in ctx.findings:
            if f.severity in {FindingSeverity.SAFETY, FindingSeverity.CRITICAL}:
                continue  # covered via safety alerts
            if f.severity == FindingSeverity.OPTIONAL:
                template = "optional_repair"
                category = "optional"
                urgency = "low"
            elif f.severity == FindingSeverity.INFO:
                template = "maintenance_reminder"
                category = "maintenance"
                urgency = "low"
            else:
                template = "recommended_repair"
                category = "recommended"
                urgency = "normal"
            body = render_template(
                template,
                vehicle=vehicle,
                issue=f.description or f.title,
                amount=f"{f.estimated_cost:.2f}",
            )
            decisions.append(
                CustomerExplanationDecision(
                    customer_id=ctx.customer_id,
                    vehicle_id=ctx.vehicle_id,
                    inspection_id=ctx.inspection_id
                    or (ctx.inspection.id if ctx.inspection else None),
                    template=template,
                    category=category,
                    title=f.title,
                    plain_language=body,
                    channel=ctx.channel,
                    urgency=urgency,  # type: ignore[arg-type]
                    confidence=0.84,
                    rationale=f"Customer explanation template={template}",
                )
            )
        return decisions

    def _vehicle_label(self, ctx: InspectionContext) -> str:
        summary = (ctx.inspection.vehicle_summary if ctx.inspection else {}) or {}
        year = summary.get("year")
        make = summary.get("make")
        model = summary.get("model")
        parts = [str(p) for p in (year, make, model) if p]
        return " ".join(parts) if parts else "vehicle"

    def _amount_for_title(self, ctx: InspectionContext, title: str) -> str:
        for f in ctx.findings:
            if f.title == title:
                return f"{f.estimated_cost:.2f}"
        total = sum((f.estimated_cost for f in ctx.findings), Decimal("0.00"))
        return f"{total:.2f}"
