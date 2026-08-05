"""Campaign / workflow event bridge — opportunities → workflow actions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.revenue.models import RevenueOpportunity


class CampaignsPluginService:
    """Translate opportunities into workflow event payloads (no marketing rewrite)."""

    def workflow_events_for(
        self, shop_id: UUID, opportunities: list[RevenueOpportunity]
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for opp in opportunities:
            events.append(
                {
                    "event_type": "revenue.opportunity_detected",
                    "shop_id": str(shop_id),
                    "payload": {
                        "opportunity_id": str(opp.id),
                        "customer_id": str(opp.customer_id),
                        "vehicle_id": str(opp.vehicle_id) if opp.vehicle_id else None,
                        "priority": opp.priority,
                        "expected_revenue": str(opp.expected_revenue),
                        "suggested_action": opp.suggested_action,
                        "reason": opp.reason,
                        "kind": opp.kind,
                        "confidence": opp.confidence,
                    },
                }
            )
            action = opp.suggested_action.split(":")[0]
            if action in {"suggest_appointment", "send_return_reminder"}:
                events.append(
                    {
                        "event_type": "marketing.maintenance_reminder_requested",
                        "shop_id": str(shop_id),
                        "payload": {
                            "opportunity_id": str(opp.id),
                            "customer_id": str(opp.customer_id),
                            "vehicle_id": str(opp.vehicle_id) if opp.vehicle_id else None,
                            "reason": opp.reason,
                            "channel": "sms",
                        },
                    }
                )
            if action in {"recover_lost_customer", "recover_declined_estimate"} and opp.priority in {
                "high",
                "urgent",
            }:
                events.append(
                    {
                        "event_type": "workflow.human_escalation_requested",
                        "shop_id": str(shop_id),
                        "payload": {
                            "opportunity_id": str(opp.id),
                            "customer_id": str(opp.customer_id),
                            "reason": f"High-value revenue opportunity: {opp.reason}",
                            "priority": opp.priority,
                        },
                    }
                )
            if action == "create_follow_up_task":
                events.append(
                    {
                        "event_type": "revenue.updated",
                        "shop_id": str(shop_id),
                        "payload": {
                            "opportunity_id": str(opp.id),
                            "task": "follow_up",
                            "suggested_action": opp.suggested_action,
                        },
                    }
                )
        return events

    def dashboard(self, *, opportunities: list[RevenueOpportunity], intel_dashboard: Any) -> dict[str, Any]:
        """Owner dashboard slices — opportunity prioritization, not accounting."""

        def _filter(kinds: set[str]) -> list[RevenueOpportunity]:
            return [o for o in opportunities if (o.kind or "") in kinds]

        top = sorted(
            opportunities,
            key=lambda o: float(o.expected_revenue) * o.confidence,
            reverse=True,
        )[:20]
        return {
            "top_revenue_opportunities": [
                {
                    "id": str(o.id),
                    "customer_id": str(o.customer_id),
                    "priority": o.priority,
                    "expected_revenue": str(o.expected_revenue),
                    "confidence": o.confidence,
                    "suggested_action": o.suggested_action,
                    "reason": o.reason,
                    "kind": o.kind,
                }
                for o in top
            ],
            "customers_at_risk": _filter({"lost_customer", "likely_to_return"}),
            "vehicles_needing_maintenance": _filter(
                {
                    "maintenance_overdue",
                    "oil_change",
                    "brake_replacement",
                    "battery_replacement",
                    "tires",
                    "alignment",
                    "fluids",
                }
            ),
            "lost_customers": _filter({"lost_customer"}),
            "declined_estimates": _filter({"declined_estimate"}),
            "upsell_opportunities": _filter(
                {"brake_replacement", "battery_replacement", "tires", "likely_to_accept_repairs"}
            ),
            "intel": {
                "expected_daily": str(getattr(intel_dashboard, "expected_revenue_daily", 0)),
                "expected_weekly": str(getattr(intel_dashboard, "expected_revenue_weekly", 0)),
                "expected_monthly": str(getattr(intel_dashboard, "expected_revenue_monthly", 0)),
                "open_opportunities": getattr(intel_dashboard, "open_opportunities", 0),
                "avg_customer_health": getattr(intel_dashboard, "avg_customer_health", 0),
                "avg_vehicle_health": getattr(intel_dashboard, "avg_vehicle_health", 0),
                "forecast": getattr(intel_dashboard, "forecast", None),
            },
        }
