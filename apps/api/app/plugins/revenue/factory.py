"""Revenue Plugin factory — wraps existing revenue_intel runtime."""

from __future__ import annotations

from typing import Any

from app.plugins.framework.metadata import PluginMetadata
from app.plugins.revenue.plugin import RevenuePlugin

_plugin: RevenuePlugin | None = None


def build_revenue_plugin(
    *,
    service: Any | None = None,
    engine: Any | None = None,
    store: Any | None = None,
    monitor: Any | None = None,
    register: bool = True,
) -> RevenuePlugin:
    if service is None:
        from app.revenue_intel.factory import get_revenue_intel_runtime

        rt = get_revenue_intel_runtime()
        service = rt.service
        engine = engine or rt.engine
        store = store or rt.store
        monitor = monitor or rt.monitor

    plugin = RevenuePlugin(
        service=service, engine=engine, store=store, monitor=monitor
    )
    if register:
        from app.plugins.framework.factory import get_plugin_runtime

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "revenue.detect": "DetectRevenueOpportunity",
                "revenue.maintenance": "PredictMaintenance",
                "revenue.upsell": "GenerateUpsellRecommendations",
                "revenue.clv": "CalculateCustomerLifetimeValue",
                "revenue.customer_value": "AnalyzeCustomerValue",
                "revenue.risk": "PredictCustomerRisk",
                "revenue.recommend_service": "RecommendService",
                "revenue.contact_timing": "RecommendContactTiming",
                "revenue.retention_plan": "CreateRetentionPlan",
                "revenue.lost": "AnalyzeLostRevenue",
                "revenue.campaign": "GenerateCampaignSuggestion",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
    return plugin


def get_revenue_plugin() -> RevenuePlugin:
    global _plugin
    if _plugin is None:
        from app.plugins.framework.factory import ensure_default_plugins
        from app.plugins.framework.registry import get_plugin_registry

        ensure_default_plugins()
        _plugin = get_plugin_registry().lookup("revenue")  # type: ignore[assignment]
    return _plugin


def reset_revenue_plugin() -> None:
    global _plugin
    _plugin = None


def revenue_plugin_from_ports(
    *,
    service: Any | None = None,
    store: Any | None = None,
) -> RevenuePlugin:
    return build_revenue_plugin(service=service, store=store, register=False)
