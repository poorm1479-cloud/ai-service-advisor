"""Inspection Intelligence factory."""

from __future__ import annotations

from typing import Any

from app.plugins.framework.metadata import PluginMetadata
from app.plugins.inspection.plugin import InspectionPlugin

_plugin: InspectionPlugin | None = None


def build_inspection_plugin(*, register: bool = True) -> InspectionPlugin:
    plugin = InspectionPlugin()
    if register:
        from app.plugins.framework.factory import get_plugin_runtime

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "inspection.analyze": "AnalyzeInspection",
                "inspection.safety": "DetectSafetyIssue",
                "inspection.repair": "GenerateInspectionRepairRecommendation",
                "inspection.explain": "GenerateInspectionCustomerExplanation",
                "inspection.estimate": "GenerateEstimateSuggestion",
                "inspection.approval": "CreateApprovalRequest",
                "inspection.prioritize": "PrioritizeRepair",
                "inspection.followup": "CreateFollowUp",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
    return plugin


def get_inspection_plugin() -> InspectionPlugin:
    global _plugin
    if _plugin is None:
        from app.plugins.framework.factory import ensure_default_plugins
        from app.plugins.framework.registry import get_plugin_registry

        ensure_default_plugins()
        _plugin = get_plugin_registry().lookup("inspection")  # type: ignore[assignment]
    return _plugin


def reset_inspection_plugin() -> None:
    global _plugin
    _plugin = None


def inspection_plugin_from_ports(**_kwargs: Any) -> InspectionPlugin:
    return build_inspection_plugin(register=False)
