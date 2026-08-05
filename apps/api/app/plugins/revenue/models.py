"""Plugin-facing opportunity view — maps revenue_intel.Opportunity to Workflow model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class RevenueOpportunity:
    """Unified Opportunity model for Workflow / Capability Registry."""

    id: UUID
    customer_id: UUID
    vehicle_id: UUID | None
    priority: str
    confidence: float
    expected_revenue: Decimal
    suggested_action: str
    reason: str
    ai_explanation: str
    workflow_reference: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    kind: str | None = None
    status: str | None = None
    shop_id: UUID | None = None
    customer_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def priority_from_opportunity(
    *, probability: float, expected_revenue: Decimal, kind: str | None = None
) -> str:
    value = float(expected_revenue) * float(probability)
    if kind in {"lost_customer", "declined_estimate"} or value >= 400:
        return "urgent"
    if value >= 200 or probability >= 0.7:
        return "high"
    if value >= 80:
        return "normal"
    return "low"


def suggested_action_for(kind: str | None, channel: str | None = None) -> str:
    mapping = {
        "lost_customer": "recover_lost_customer",
        "likely_to_return": "send_return_reminder",
        "likely_to_accept_repairs": "follow_up_estimate",
        "declined_estimate": "recover_declined_estimate",
        "maintenance_overdue": "suggest_appointment",
        "oil_change": "suggest_appointment",
        "brake_replacement": "suggest_appointment",
        "battery_replacement": "suggest_appointment",
        "tires": "upsell_service",
        "alignment": "cross_sell_service",
        "fluids": "cross_sell_service",
    }
    action = mapping.get(kind or "", "create_follow_up_task")
    if channel:
        return f"{action}:{channel}"
    return action


def from_intel_opportunity(opp: Any) -> RevenueOpportunity:
    """Adapt revenue_intel.Opportunity → RevenueOpportunity (no rewrite)."""
    kind = getattr(getattr(opp, "kind", None), "value", None) or str(
        getattr(opp, "kind", "") or ""
    )
    channel = getattr(getattr(opp, "recommended_channel", None), "value", None)
    expected = getattr(opp, "expected_revenue", Decimal("0")) or Decimal("0")
    probability = float(getattr(opp, "probability", 0.0) or 0.0)
    created = getattr(opp, "created_at", None) or datetime.now(timezone.utc)
    expires = created + timedelta(days=30)
    message = getattr(opp, "recommended_message", "") or ""
    reason = getattr(opp, "reason", "") or ""
    return RevenueOpportunity(
        id=opp.id,
        customer_id=opp.customer_id,
        vehicle_id=getattr(opp, "vehicle_id", None),
        priority=priority_from_opportunity(
            probability=probability, expected_revenue=expected, kind=kind
        ),
        confidence=probability,
        expected_revenue=expected if isinstance(expected, Decimal) else Decimal(str(expected)),
        suggested_action=suggested_action_for(kind, channel),
        reason=reason,
        ai_explanation=message or reason,
        workflow_reference=str(getattr(opp, "analysis_job_id", None) or ""),
        created_at=created,
        expires_at=expires,
        kind=kind,
        status=getattr(getattr(opp, "status", None), "value", None)
        or str(getattr(opp, "status", "") or ""),
        shop_id=getattr(opp, "shop_id", None),
        customer_name=getattr(opp, "customer_name", "") or "",
        metadata=dict(getattr(opp, "metadata", None) or {}),
    )
