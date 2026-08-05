"""Read-only Dashboard plugin — exposes Get* capabilities (no mutations)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.dashboard.service import DashboardService
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext


class DashboardPlugin:
    """IPlugin — Owner Dashboard / AI Operations Center (read-only)."""

    def __init__(self, service: DashboardService | None = None) -> None:
        self._service = service or DashboardService()
        self._initialized = False

    def plugin_id(self) -> str:
        return "dashboard"

    def plugin_name(self) -> str:
        return "Owner Dashboard & AI Operations Center"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Read-only owner dashboard: AI activity, appointments, revenue opportunities, "
            "risks, approvals, workflow status, and system health."
        )

    def supported_capabilities(self) -> list[str]:
        return [
            Capability.GET_DAILY_SUMMARY.value,
            Capability.GET_AI_ACTIVITY.value,
            Capability.GET_PENDING_ACTIONS.value,
            Capability.GET_REVENUE_OPPORTUNITIES.value,
            Capability.GET_CUSTOMER_RISK.value,
            Capability.GET_APPOINTMENT_OVERVIEW.value,
            Capability.GET_WORKFLOW_STATUS.value,
            Capability.GET_PERFORMANCE_METRICS.value,
        ]

    def capabilities(self) -> list[str]:
        return self.supported_capabilities()

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
            "capabilities": len(self.supported_capabilities()),
            "read_only": True,
        }

    @property
    def service(self) -> DashboardService:
        return self._service

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        shop_id = kwargs.get("shop_id") or (context.shop_id if context else None)
        if shop_id is None:
            raise ValueError("shop_id required for dashboard capabilities")
        if isinstance(shop_id, str):
            shop_id = UUID(shop_id)

        cap = capability if isinstance(capability, str) else str(capability)
        svc = self._service

        if cap in {Capability.GET_DAILY_SUMMARY.value, "GetDailySummary"}:
            return await svc.daily_summary(shop_id)
        if cap in {Capability.GET_AI_ACTIVITY.value, "GetAIActivity"}:
            return await svc.ai_activity(shop_id)
        if cap in {Capability.GET_PENDING_ACTIONS.value, "GetPendingActions"}:
            return await svc.pending_actions(shop_id)
        if cap in {Capability.GET_REVENUE_OPPORTUNITIES.value, "GetRevenueOpportunities"}:
            return await svc.revenue_opportunities(shop_id)
        if cap in {Capability.GET_CUSTOMER_RISK.value, "GetCustomerRisk"}:
            return await svc.customer_risk(shop_id)
        if cap in {Capability.GET_APPOINTMENT_OVERVIEW.value, "GetAppointmentOverview"}:
            return await svc.appointment_overview(shop_id)
        if cap in {Capability.GET_WORKFLOW_STATUS.value, "GetWorkflowStatus"}:
            return await svc.workflow_status(shop_id)
        if cap in {Capability.GET_PERFORMANCE_METRICS.value, "GetPerformanceMetrics"}:
            return await svc.performance_metrics(shop_id)

        # Full snapshot convenience (not a listed capability name but useful)
        if cap in {"GetOwnerDashboard", "GetDashboardSnapshot"}:
            snap = await svc.get_snapshot(shop_id, force=bool(kwargs.get("force")))
            return snap.to_dict()

        raise LookupError(f"Unsupported dashboard capability: {cap}")
