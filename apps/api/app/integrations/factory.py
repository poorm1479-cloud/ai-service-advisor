"""Integrations runtime factory."""

from __future__ import annotations

from dataclasses import dataclass

from app.integrations.bridge import IntegrationBridge
from app.integrations.core.registry import (
    AdapterRegistry,
    build_default_registry,
    reset_adapter_registry,
)
from app.integrations.plugin import IntegrationPlugin
from app.integrations.service import IntegrationsService
from app.integrations.store import InMemoryIntegrationStore, IntegrationStorePort

_plugin: IntegrationPlugin | None = None
_runtime = None  # IntegrationsRuntime | None


@dataclass(slots=True)
class IntegrationsRuntime:
    service: IntegrationsService
    store: IntegrationStorePort
    registry: AdapterRegistry
    bridge: IntegrationBridge
    plugin: IntegrationPlugin | None = None


def build_integration_plugin(*, register: bool = True) -> IntegrationPlugin:
    """Build (and optionally register) the Integration Plugin into Plugin Framework."""
    global _plugin
    plugin = IntegrationPlugin()
    if register:
        from app.plugins.framework.factory import get_plugin_runtime
        from app.plugins.framework.metadata import PluginMetadata

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "integrations.import_customer": "ImportCustomerData",
                "integrations.import_vehicle": "ImportVehicleData",
                "integrations.import_repair": "ImportRepairHistory",
                "integrations.sync_appointment": "SyncAppointment",
                "integrations.sync_invoice": "SyncInvoice",
                "integrations.sync_payment": "SyncPayment",
                "integrations.send_message": "SendCustomerMessage",
                "integrations.receive_message": "ReceiveCustomerMessage",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
        _plugin = plugin
    return plugin


def get_integration_plugin() -> IntegrationPlugin:
    global _plugin
    if _plugin is None:
        return build_integration_plugin(register=True)
    return _plugin


def reset_integration_plugin() -> None:
    global _plugin
    _plugin = None


def build_integrations_runtime(
    *,
    store: IntegrationStorePort | None = None,
    registry: AdapterRegistry | None = None,
    register_plugin: bool = False,
) -> IntegrationsRuntime:
    resource_store = store or InMemoryIntegrationStore()
    adapter_registry = registry or build_default_registry()
    bridge = IntegrationBridge()
    service = IntegrationsService(
        store=resource_store,
        registry=adapter_registry,
        bridge=bridge,
    )
    plugin = build_integration_plugin(register=register_plugin)
    return IntegrationsRuntime(
        service=service,
        store=resource_store,
        registry=adapter_registry,
        bridge=bridge,
        plugin=plugin,
    )


# Aliases expected by plugin framework factory
build_integration_runtime = build_integrations_runtime


def get_integrations_runtime() -> IntegrationsRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_integrations_runtime(register_plugin=False)
    return _runtime


get_integration_runtime = get_integrations_runtime


def reset_integrations_runtime() -> None:
    global _runtime
    _runtime = None
    reset_integration_plugin()
    reset_adapter_registry()


reset_integration_runtime = reset_integrations_runtime
