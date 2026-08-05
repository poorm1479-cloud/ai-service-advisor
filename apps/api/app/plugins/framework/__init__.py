"""Plugin Framework — reusable plugin system for AutoRepair OS."""

from app.plugins.framework.capability import (
    Capability,
    CapabilityBinding,
    CapabilityRegistry,
    get_capability_registry,
    reset_capability_registry,
)
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import (
    ensure_default_plugins,
    ensure_workflow_plugins,
    get_plugin_runtime,
    reset_plugin_runtime,
)
from app.plugins.framework.lifecycle import LifecycleState, PluginLifecycle
from app.plugins.framework.loader import PluginLoader
from app.plugins.framework.metadata import PluginMetadata, validate_metadata
from app.plugins.framework.plugin import BasePlugin, IPlugin
from app.plugins.framework.registry import PluginRegistry, get_plugin_registry, reset_plugin_registry

__all__ = [
    "BasePlugin",
    "Capability",
    "CapabilityBinding",
    "CapabilityRegistry",
    "IPlugin",
    "LifecycleState",
    "PluginContext",
    "PluginLifecycle",
    "PluginLoader",
    "PluginMetadata",
    "PluginRegistry",
    "ensure_default_plugins",
    "ensure_workflow_plugins",
    "get_capability_registry",
    "get_plugin_registry",
    "get_plugin_runtime",
    "reset_capability_registry",
    "reset_plugin_registry",
    "reset_plugin_runtime",
    "validate_metadata",
]
