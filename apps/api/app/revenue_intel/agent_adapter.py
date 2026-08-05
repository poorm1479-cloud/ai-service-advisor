"""Bridge Revenue Intelligence → Phase 5 RevenueAgent shapes."""

from __future__ import annotations

from decimal import Decimal

from app.agents.revenue.models import RevenueInsights, UpsellOpportunity
from app.revenue_intel.enums import OpportunityKind
from app.revenue_intel.models import Opportunity


def opportunities_to_agent_insights(opps: list[Opportunity]) -> RevenueInsights:
    upsells = [
        UpsellOpportunity(
            service=o.kind.value,
            reason=o.reason,
            estimated_revenue=o.expected_revenue,
            priority="high" if o.probability >= 0.5 else "medium",
        )
        for o in opps
    ]
    predicted = sum((u.estimated_revenue for u in upsells), Decimal("0")).quantize(Decimal("0.01"))
    lost = [o for o in opps if o.kind == OpportunityKind.LOST_CUSTOMER]
    lost_risk = max((o.probability for o in lost), default=0.0)
    return RevenueInsights(
        upsell_opportunities=upsells,
        predicted_revenue=predicted,
        lost_customer_risk=lost_risk,
        notes=[f"{len(opps)} opportunities from Revenue Intelligence"],
    )
