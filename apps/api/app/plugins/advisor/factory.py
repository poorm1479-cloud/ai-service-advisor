"""AI Service Advisor factory."""

from __future__ import annotations

from typing import Any

from app.plugins.advisor.advisor import AdvisorPlugin
from app.plugins.framework.metadata import PluginMetadata

_plugin: AdvisorPlugin | None = None


def build_advisor_plugin(*, register: bool = True) -> AdvisorPlugin:
    plugin = AdvisorPlugin()
    if register:
        from app.plugins.framework.factory import get_plugin_runtime

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "advisor.analyze": "AnalyzeConversation",
                "advisor.repair": "GenerateRepairRecommendation",
                "advisor.estimate": "GenerateEstimateSummary",
                "advisor.followup": "GenerateFollowUp",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
    return plugin


def get_advisor_plugin() -> AdvisorPlugin:
    global _plugin
    if _plugin is None:
        from app.plugins.framework.factory import ensure_default_plugins
        from app.plugins.framework.registry import get_plugin_registry

        ensure_default_plugins()
        _plugin = get_plugin_registry().lookup("advisor")  # type: ignore[assignment]
    return _plugin


def reset_advisor_plugin() -> None:
    global _plugin
    _plugin = None


def advisor_plugin_from_ports(**_kwargs: Any) -> AdvisorPlugin:
    return build_advisor_plugin(register=False)
