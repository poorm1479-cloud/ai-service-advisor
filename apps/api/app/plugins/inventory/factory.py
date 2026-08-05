"""Parts & Inventory Intelligence factory."""

from __future__ import annotations

from typing import Any

from app.plugins.framework.metadata import PluginMetadata
from app.plugins.inventory.plugin import InventoryPlugin

_plugin: InventoryPlugin | None = None


def build_inventory_plugin(*, register: bool = True) -> InventoryPlugin:
    plugin = InventoryPlugin()
    if register:
        from app.plugins.framework.factory import get_plugin_runtime

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "inventory.find": "FindPart",
                "inventory.check": "CheckInventory",
                "inventory.predict": "PredictRequiredParts",
                "inventory.reserve": "ReservePart",
                "inventory.release": "ReleasePart",
                "inventory.supplier": "FindSupplier",
                "inventory.purchase": "CreatePurchaseRecommendation",
                "inventory.cost": "EstimatePartCost",
                "inventory.readiness": "CheckRepairReadiness",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
    return plugin


def get_inventory_plugin() -> InventoryPlugin:
    global _plugin
    if _plugin is None:
        from app.plugins.framework.factory import ensure_default_plugins
        from app.plugins.framework.registry import get_plugin_registry

        ensure_default_plugins()
        _plugin = get_plugin_registry().lookup("inventory")  # type: ignore[assignment]
    return _plugin


def reset_inventory_plugin() -> None:
    global _plugin
    _plugin = None


def inventory_plugin_from_ports(**_kwargs: Any) -> InventoryPlugin:
    return build_inventory_plugin(register=False)
