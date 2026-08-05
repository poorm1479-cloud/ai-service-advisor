"""Memory Plugin factory."""

from __future__ import annotations

from typing import Any

from app.memory.core.manager import MemoryManager
from app.plugins.framework.metadata import PluginMetadata
from app.plugins.memory.plugin import MemoryPlugin

_plugin: MemoryPlugin | None = None


def build_memory_plugin(
    *,
    manager: MemoryManager | None = None,
    register: bool = True,
) -> MemoryPlugin:
    plugin = MemoryPlugin(manager=manager)
    if register:
        from app.plugins.framework.factory import get_plugin_runtime

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "memory.save": "SaveMemory",
                "memory.search": "SearchMemory",
                "memory.customer_history": "GetCustomerHistory",
                "memory.vehicle_history": "GetVehicleHistory",
                "memory.shop_preference": "GetShopPreference",
                "memory.knowledge": "RetrieveKnowledge",
                "memory.update_customer": "UpdateCustomerProfile",
                "memory.update_vehicle_health": "UpdateVehicleHealth",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
        global _plugin
        _plugin = plugin
    return plugin


def get_memory_plugin() -> MemoryPlugin:
    global _plugin
    if _plugin is None:
        from app.plugins.framework.factory import ensure_default_plugins
        from app.plugins.framework.registry import get_plugin_registry

        ensure_default_plugins()
        _plugin = get_plugin_registry().lookup("memory")  # type: ignore[assignment]
    return _plugin


def reset_memory_plugin() -> None:
    global _plugin
    _plugin = None


def memory_plugin_from_ports(**_kwargs: Any) -> MemoryPlugin:
    return build_memory_plugin(register=False)
