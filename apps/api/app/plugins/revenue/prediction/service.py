"""Prediction — maintenance, capacity, utilization (wraps intel + scheduling snapshot)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.revenue.models import RevenueOpportunity, from_intel_opportunity
from app.revenue_intel.enums import OpportunityKind, OpportunityStatus
from app.revenue_intel.scoring import score_vehicle


class PredictionPluginService:
    def __init__(self, *, service: Any, store: Any | None = None) -> None:
        self._service = service
        self._store = store or getattr(service, "_store", None)

    async def predict_maintenance(
        self, shop_id: UUID, *, limit: int = 100
    ) -> list[RevenueOpportunity]:
        kinds = {
            OpportunityKind.MAINTENANCE_OVERDUE,
            OpportunityKind.OIL_CHANGE,
            OpportunityKind.BRAKES,
            OpportunityKind.BATTERY,
            OpportunityKind.TIRES,
            OpportunityKind.ALIGNMENT,
            OpportunityKind.FLUIDS,
        }
        open_opps = await self._service.list_opportunities(
            shop_id, status=OpportunityStatus.OPEN, limit=500
        )
        filtered = [o for o in open_opps if o.kind in kinds]
        return [from_intel_opportunity(o) for o in filtered[:limit]]

    async def calculate_vehicle_health(
        self, shop_id: UUID, vehicle_id: UUID | None = None
    ) -> list[Any] | Any:
        scores = await self._service.list_scores(shop_id, entity_type="vehicle")
        if vehicle_id is not None:
            match = next((s for s in scores if s.entity_id == vehicle_id), None)
            if match is not None:
                return match
            vehicle = await self._load_vehicle(shop_id, vehicle_id)
            if vehicle is not None:
                return score_vehicle(vehicle)
            return None
        return scores

    async def predict_shop_capacity(self, shop_id: UUID) -> dict[str, Any]:
        forecast = await self._service.get_forecast(shop_id)
        dash = await self._service.build_dashboard(shop_id)
        util = await self._technician_utilization(shop_id)
        return {
            "shop_id": str(shop_id),
            "monthly_expected_revenue": str(getattr(forecast, "total_expected", 0)),
            "open_opportunities": getattr(dash, "open_opportunities", 0),
            "expected_daily": str(getattr(dash, "expected_revenue_daily", 0)),
            "expected_weekly": str(getattr(dash, "expected_revenue_weekly", 0)),
            "technician_utilization": util.get("shop_utilization"),
            "capacity_pressure": util.get("capacity_pressure", "unknown"),
            "forecast_months": [
                {
                    "label": m.label,
                    "expected_revenue": str(m.expected_revenue),
                    "opportunity_count": m.opportunity_count,
                }
                for m in (getattr(forecast, "months", None) or [])
            ],
        }

    async def optimize_technician_utilization(self, shop_id: UUID) -> dict[str, Any]:
        util = await self._technician_utilization(shop_id)
        pressure = util.get("capacity_pressure", "unknown")
        recommendations: list[str] = []
        shop_u = float(util.get("shop_utilization") or 0)
        if shop_u >= 0.85:
            recommendations.append("Defer low-priority upsells; protect high-value appointments")
            recommendations.append("Offer off-peak slots for maintenance reminders")
        elif shop_u <= 0.45:
            recommendations.append("Prioritize lost-customer and declined-estimate recovery outreach")
            recommendations.append("Fill capacity with overdue maintenance campaigns")
        else:
            recommendations.append("Balance outreach with available bay/mechanic capacity")
        return {
            "shop_id": str(shop_id),
            "utilization": util,
            "capacity_pressure": pressure,
            "recommendations": recommendations,
        }

    async def _technician_utilization(self, shop_id: UUID) -> dict[str, Any]:
        try:
            from app.plugins.scheduling.factory import get_scheduling_plugin

            plugin = get_scheduling_plugin()
            snap = await plugin.live_snapshot(shop_id)
            mech = snap.get("mechanic_utilization") or {}
            shop_u = float(mech.get("shop") or 0.0)
            if shop_u >= 0.85:
                pressure = "high"
            elif shop_u <= 0.45:
                pressure = "low"
            else:
                pressure = "moderate"
            return {
                "shop_utilization": shop_u,
                "by_mechanic": mech,
                "appointments_today": snap.get("appointments_today"),
                "capacity_pressure": pressure,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "shop_utilization": None,
                "capacity_pressure": "unknown",
                "error": str(exc),
            }

    async def _load_vehicle(self, shop_id: UUID, vehicle_id: UUID) -> Any | None:
        if self._store is None or not hasattr(self._store, "list_customers"):
            return None
        customers = await self._store.list_customers(shop_id)
        for c in customers:
            for v in getattr(c, "vehicles", []) or []:
                if v.id == vehicle_id:
                    return v
        return None
