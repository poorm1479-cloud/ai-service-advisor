"""CRM Plugin factory — wrap existing agent CRM stores without rewriting them."""

from __future__ import annotations

from typing import Any

from app.plugins.crm.communication.service import CommunicationPluginService
from app.plugins.crm.customer.service import CustomerPluginService
from app.plugins.crm.plugin import CrmPlugin
from app.plugins.crm.repair.service import RepairPluginService
from app.plugins.crm.vehicle.service import VehiclePluginService
from app.plugins.framework.metadata import PluginMetadata

_plugin: CrmPlugin | None = None


def build_crm_plugin(
    *,
    customer_directory: Any | None = None,
    vehicle_directory: Any | None = None,
    crm_store: Any | None = None,
    register: bool = True,
) -> CrmPlugin:
    """Build CrmPlugin wrapping existing directory/store implementations.

    When ports are omitted, default in-memory implementations are used
    (same as pre-plugin agent defaults).
    """
    customers = CustomerPluginService(customer_directory)
    vehicles = VehiclePluginService(vehicle_directory)
    repairs = RepairPluginService(vehicles.directory)
    communications = CommunicationPluginService(crm_store)
    plugin = CrmPlugin(
        customers=customers,
        vehicles=vehicles,
        repairs=repairs,
        communications=communications,
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
                "crm.find_customer": "FindCustomer",
                "crm.create_customer": "CreateCustomer",
                "crm.timeline": "CustomerTimeline",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
    return plugin


def get_crm_plugin() -> CrmPlugin:
    """Process-wide CRM plugin singleton (registered via Plugin Framework)."""
    global _plugin
    if _plugin is None:
        from app.plugins.framework.factory import ensure_default_plugins

        ensure_default_plugins()
        from app.plugins.framework.registry import get_plugin_registry

        _plugin = get_plugin_registry().lookup("crm")  # type: ignore[assignment]
    return _plugin


def reset_crm_plugin() -> None:
    global _plugin
    _plugin = None


def crm_plugin_from_ports(
    *,
    customer_directory: Any | None = None,
    vehicle_directory: Any | None = None,
    crm_store: Any | None = None,
) -> CrmPlugin:
    """Build an unregistered plugin from DecisionPorts (Workflow execution path)."""
    return build_crm_plugin(
        customer_directory=customer_directory,
        vehicle_directory=vehicle_directory,
        crm_store=crm_store,
        register=False,
    )
