"""Estimate assistance — decide only (explanations / approval requests)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.agents.decisions.types import (
    ApprovalRequestDecision,
    EstimateExplanationDecision,
    RepairRecommendationDecision,
)
from app.plugins.advisor.models import AdvisorContext


class AdvisorEstimateService:
    def generate_summary(
        self, ctx: AdvisorContext, *, recommendations: list[RepairRecommendationDecision] | None = None
    ) -> list[Any]:
        recs = recommendations or []
        if not recs and not ctx.revenue_opportunities:
            return []
        line_items: list[dict[str, Any]] = []
        total = Decimal("0.00")
        for r in recs:
            line_items.append(
                {
                    "service": r.service_type,
                    "title": r.title,
                    "amount": str(r.estimated_cost),
                }
            )
            total += r.estimated_cost
        if not line_items:
            for opp in ctx.revenue_opportunities[:3]:
                amt = Decimal(str(opp.get("expected_revenue") or opp.get("amount") or "0"))
                line_items.append(
                    {
                        "service": opp.get("kind") or opp.get("service") or "service",
                        "title": opp.get("reason") or opp.get("title") or "Recommended service",
                        "amount": str(amt),
                    }
                )
                total += amt

        plain = (
            "Here's a clear summary of recommended work: "
            + "; ".join(f"{i['title']} (~${i['amount']})" for i in line_items)
            + f". Estimated total around ${total}."
        )
        return [
            EstimateExplanationDecision(
                customer_id=ctx.customer_id,
                vehicle_id=ctx.vehicle_id,
                amount=total,
                line_items=line_items,
                summary=f"Estimate summary totaling ${total}",
                plain_language=plain,
                channel=ctx.channel or "sms",
                confidence=0.7,
                rationale="Advisor estimate explanation from recommendations",
            )
        ]

    def generate_approval_request(
        self, ctx: AdvisorContext, *, amount: Decimal | None = None, services: list[str] | None = None
    ) -> list[Any]:
        svcs = services or []
        amt = amount or Decimal("0.00")
        if not svcs and ctx.inbound_text and any(
            w in (ctx.inbound_text or "").lower() for w in ("approve", "estimate", "how much", "cost")
        ):
            svcs = ["recommended_repairs"]
            amt = amt or Decimal("250.00")
        if not svcs and not amt:
            return []
        body = (
            f"We need your approval to proceed"
            + (f" with: {', '.join(svcs)}" if svcs else "")
            + (f" (about ${amt})" if amt else "")
            + ". Reply YES to approve or call the shop with questions."
        )
        return [
            ApprovalRequestDecision(
                customer_id=ctx.customer_id,
                vehicle_id=ctx.vehicle_id,
                amount=amt,
                services=svcs,
                message_body=body,
                channel=ctx.channel or "sms",
                priority="high",
                confidence=0.68,
                rationale="Customer approval assistance",
            )
        ]
