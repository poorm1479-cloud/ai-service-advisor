"""Approval requests and follow-ups from inspection — Decision Objects only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.agents.decisions.types import (
    ApprovalRequestDecision,
    FollowUpDecision,
    RepairRecommendationDecision,
)
from app.plugins.inspection.models import FindingSeverity, InspectionContext
from app.plugins.inspection.templates import render_template


class ApprovalService:
    """Create approval requests and follow-ups — never approves or sends."""

    def create_approval_request(
        self,
        ctx: InspectionContext,
        *,
        recommendations: list[RepairRecommendationDecision] | None = None,
    ) -> list[Any]:
        recs = recommendations or []
        actionable = [
            f
            for f in ctx.findings
            if f.severity
            in {
                FindingSeverity.RECOMMENDED,
                FindingSeverity.SAFETY,
                FindingSeverity.CRITICAL,
            }
        ]
        if not recs and not actionable:
            return []

        services = [r.title for r in recs] or [f.title for f in actionable]
        amount = sum((r.estimated_cost for r in recs), Decimal("0.00"))
        if not recs:
            amount = sum((f.estimated_cost for f in actionable), Decimal("0.00"))

        vehicle = "vehicle"
        if ctx.inspection and ctx.inspection.vehicle_summary:
            vs = ctx.inspection.vehicle_summary
            vehicle = " ".join(
                str(p) for p in (vs.get("year"), vs.get("make"), vs.get("model")) if p
            ) or "vehicle"

        body = render_template(
            "approval_request",
            vehicle=vehicle,
            services=", ".join(services[:5]),
            amount=f"{amount:.2f}",
        )
        priority = "urgent" if any(
            f.severity == FindingSeverity.CRITICAL for f in actionable
        ) else ("high" if any(f.severity == FindingSeverity.SAFETY for f in actionable) else "normal")

        return [
            ApprovalRequestDecision(
                customer_id=ctx.customer_id,
                vehicle_id=ctx.vehicle_id,
                amount=amount,
                services=services,
                message_body=body,
                channel=ctx.channel,
                priority=priority,  # type: ignore[arg-type]
                confidence=0.85,
                rationale="Inspection approval request (AI decide-only)",
            )
        ]

    def create_follow_up(
        self,
        ctx: InspectionContext,
        *,
        recommendations: list[RepairRecommendationDecision] | None = None,
    ) -> list[Any]:
        recs = recommendations or []
        pending = [f for f in ctx.findings if f.severity != FindingSeverity.INFO]
        if not pending and not recs:
            return []

        issue = recs[0].title if recs else pending[0].title
        amount = (
            recs[0].estimated_cost
            if recs
            else pending[0].estimated_cost
        )
        vehicle = "vehicle"
        if ctx.inspection and ctx.inspection.vehicle_summary:
            vs = ctx.inspection.vehicle_summary
            vehicle = " ".join(
                str(p) for p in (vs.get("year"), vs.get("make"), vs.get("model")) if p
            ) or "vehicle"

        body = render_template(
            "follow_up",
            vehicle=vehicle,
            issue=issue,
            amount=f"{amount:.2f}",
        )
        return [
            FollowUpDecision(
                customer_id=ctx.customer_id,
                vehicle_id=ctx.vehicle_id,
                inspection_id=ctx.inspection_id
                or (ctx.inspection.id if ctx.inspection else None),
                reason="inspection_follow_up",
                message_body=body,
                channel=ctx.channel,
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=3),
                priority="normal",
                confidence=0.8,
                rationale="Inspection follow-up decision (AI decide-only)",
            )
        ]
