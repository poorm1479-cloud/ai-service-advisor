"""Dashboard runtime factory."""

from __future__ import annotations

from dataclasses import dataclass

from app.dashboard.aggregation import DashboardAggregator
from app.dashboard.plugin import DashboardPlugin
from app.dashboard.service import DashboardService
from app.plugins.framework.metadata import PluginMetadata


@dataclass(slots=True)
class DashboardRuntime:
    service: DashboardService
    aggregator: DashboardAggregator
    plugin: DashboardPlugin


_runtime: DashboardRuntime | None = None
_plugin: DashboardPlugin | None = None


def build_dashboard_plugin(*, register: bool = True, service: DashboardService | None = None) -> DashboardPlugin:
    plugin = DashboardPlugin(service=service)
    if register:
        from app.plugins.framework.factory import get_plugin_runtime

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "dashboard.summary": "GetDailySummary",
                "dashboard.activity": "GetAIActivity",
                "dashboard.pending": "GetPendingActions",
                "dashboard.revenue": "GetRevenueOpportunities",
                "dashboard.risk": "GetCustomerRisk",
                "dashboard.appointments": "GetAppointmentOverview",
                "dashboard.workflows": "GetWorkflowStatus",
                "dashboard.performance": "GetPerformanceMetrics",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
    return plugin


def build_dashboard_runtime(*, register_plugin: bool = False) -> DashboardRuntime:
    aggregator = DashboardAggregator()
    service = DashboardService(aggregator=aggregator)
    plugin = build_dashboard_plugin(register=register_plugin, service=service)
    return DashboardRuntime(service=service, aggregator=aggregator, plugin=plugin)


def get_dashboard_runtime() -> DashboardRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_dashboard_runtime(register_plugin=False)
    return _runtime


def reset_dashboard_runtime() -> None:
    global _runtime, _plugin
    _runtime = None
    _plugin = None


def reset_dashboard_plugin() -> None:
    global _plugin
    _plugin = None
    reset_dashboard_runtime()
