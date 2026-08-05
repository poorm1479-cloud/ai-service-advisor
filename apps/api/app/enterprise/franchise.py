"""Franchise / multi-location analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.enterprise.models import FranchiseAnalytics, LocationMetrics
from app.enterprise.store import EnterpriseStorePort


class FranchiseAnalyticsEngine:
    def __init__(self, store: EnterpriseStorePort) -> None:
        self._store = store

    def build(self, org_id: UUID) -> FranchiseAnalytics:
        locations = self._store.list_locations(org_id)
        metrics: list[LocationMetrics] = []
        for loc in locations:
            # Real facts only — do not invent demo revenue/appointments for empty shops.
            revenue = 0.0
            appts = 0
            ai = 0.0
            retention = 0.0
            customers = 0
            try:
                from app.workflows.factory import get_workflow_runtime

                overlay = get_workflow_runtime().coordinator.get_shop_analytics_overlay_sync(
                    loc.shop_id
                )
                if "error" not in overlay:
                    revenue = float(overlay.get("revenue") or 0)
                    retention = float(overlay.get("retention") or 0)
                    ai = float(overlay.get("ai_success_rate") or 0)
                    appts = int(overlay.get("appointments") or 0)
                    customers = int(overlay.get("customers") or 0)
            except Exception:
                pass
            metrics.append(
                LocationMetrics(
                    location_id=loc.id,
                    location_name=loc.name,
                    code=loc.code,
                    revenue=round(revenue, 2),
                    appointments=appts,
                    ai_success_rate=round(ai, 4),
                    retention=round(retention, 4),
                    customers=customers,
                )
            )

        totals = {
            "revenue": round(sum(m.revenue for m in metrics), 2),
            "appointments": float(sum(m.appointments for m in metrics)),
            "customers": float(sum(m.customers for m in metrics)),
            "avg_ai_success_rate": round(
                (sum(m.ai_success_rate for m in metrics) / len(metrics)) if metrics else 0.0,
                4,
            ),
            "avg_retention": round(
                (sum(m.retention for m in metrics) / len(metrics)) if metrics else 0.0,
                4,
            ),
        }
        rankings = {
            "revenue": [m.code for m in sorted(metrics, key=lambda x: x.revenue, reverse=True)],
            "ai_success_rate": [m.code for m in sorted(metrics, key=lambda x: x.ai_success_rate, reverse=True)],
            "retention": [m.code for m in sorted(metrics, key=lambda x: x.retention, reverse=True)],
        }
        return FranchiseAnalytics(
            organization_id=org_id,
            generated_at=datetime.now(timezone.utc),
            locations=metrics,
            totals=totals,
            rankings=rankings,
        )
