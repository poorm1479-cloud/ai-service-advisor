"""Plugin system — AutoRepair OS Plugin Framework + reference plugins."""

from app.plugins.framework import (
    Capability,
    CapabilityRegistry,
    IPlugin,
    PluginContext,
    PluginRegistry,
    ensure_default_plugins,
    ensure_workflow_plugins,
    get_capability_registry,
    get_plugin_registry,
    get_plugin_runtime,
    reset_capability_registry,
    reset_plugin_registry,
    reset_plugin_runtime,
)

__all__ = [
    "Capability",
    "CapabilityRegistry",
    "IPlugin",
    "PluginContext",
    "PluginRegistry",
    "ensure_default_plugins",
    "ensure_workflow_plugins",
    "get_capability_registry",
    "get_plugin_registry",
    "get_plugin_runtime",
    "reset_capability_registry",
    "reset_plugin_registry",
    "reset_plugin_runtime",
]
