"""Learning Plugin factory."""

from __future__ import annotations

from typing import Any

from app.learning.engine import LearningEngine
from app.plugins.framework.metadata import PluginMetadata
from app.plugins.learning.plugin import LearningPlugin

_plugin: LearningPlugin | None = None


def build_learning_plugin(
    *,
    engine: LearningEngine | None = None,
    register: bool = True,
) -> LearningPlugin:
    plugin = LearningPlugin(engine=engine)
    if register:
        from app.plugins.framework.factory import get_plugin_runtime

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "learning.collect": "CollectDecisionResult",
                "learning.evaluate": "EvaluateDecision",
                "learning.customer_response": "LearnCustomerResponse",
                "learning.patterns": "AnalyzeSuccessPattern",
                "learning.optimize": "OptimizeRecommendation",
                "learning.insight": "GenerateLearningInsight",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
        global _plugin
        _plugin = plugin
    return plugin


def get_learning_plugin() -> LearningPlugin:
    global _plugin
    if _plugin is None:
        from app.plugins.framework.factory import ensure_default_plugins
        from app.plugins.framework.registry import get_plugin_registry

        ensure_default_plugins()
        _plugin = get_plugin_registry().lookup("learning")  # type: ignore[assignment]
    return _plugin


def reset_learning_plugin() -> None:
    global _plugin
    _plugin = None


def learning_plugin_from_ports(**_kwargs: Any) -> LearningPlugin:
    return build_learning_plugin(register=False)
