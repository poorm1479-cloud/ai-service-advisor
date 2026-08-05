"""Scheduling Plugin factory — wrap existing scheduling stores without rewriting."""

from __future__ import annotations

from typing import Any

from app.plugins.framework.metadata import PluginMetadata
from app.plugins.scheduling.appointment.service import AppointmentPluginService
from app.plugins.scheduling.availability.service import AvailabilityPluginService
from app.plugins.scheduling.bay.service import BayPluginService
from app.plugins.scheduling.calendar.service import CalendarPluginService
from app.plugins.scheduling.mechanic.service import MechanicPluginService
from app.plugins.scheduling.plugin import SchedulingPlugin

_plugin: SchedulingPlugin | None = None


def _default_store_and_intel() -> tuple[Any, Any | None, Any | None]:
    """Default to in-memory store — avoid circular import with scheduling.factory."""
    from app.agents.scheduling.service import InMemorySchedulingStore

    return InMemorySchedulingStore(), None, None


def attach_intelligence_runtime(plugin: SchedulingPlugin) -> SchedulingPlugin:
    """Lazily attach Phase 8 intelligence when safe (after agent graph is built)."""
    if plugin.intelligence is not None:
        return plugin
    try:
        from app.scheduling.factory import get_scheduling_runtime

        rt = get_scheduling_runtime()
        plugin._store = rt.agent_store
        plugin._intelligence = rt.service
        plugin._monitor = rt.monitor
        plugin._agents = rt.agents
        plugin._appointments = AppointmentPluginService(plugin._store)
        plugin._calendar = CalendarPluginService(plugin._store)
        plugin._availability = AvailabilityPluginService(
            plugin._store, intelligence=rt.service
        )
        plugin._mechanics = MechanicPluginService(
            intelligence=rt.service, store=plugin._store
        )
        plugin._bays = BayPluginService(intelligence=rt.service, store=plugin._store)
    except Exception:  # noqa: BLE001
        pass
    return plugin


def build_scheduling_plugin(
    *,
    store: Any | None = None,
    intelligence: Any | None = None,
    monitor: Any | None = None,
    register: bool = True,
) -> SchedulingPlugin:
    if store is None and intelligence is None and monitor is None:
        store, intelligence, monitor = _default_store_and_intel()
    plugin = SchedulingPlugin(store=store, intelligence=intelligence, monitor=monitor)
    if register:
        from app.plugins.framework.factory import get_plugin_runtime

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "scheduling.find_slot": "FindAvailableSlot",
                "scheduling.book": "BookAppointment",
                "scheduling.cancel": "CancelAppointment",
                "scheduling.reschedule": "RescheduleAppointment",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
    return plugin


def get_scheduling_plugin() -> SchedulingPlugin:
    global _plugin
    if _plugin is None:
        from app.plugins.framework.factory import ensure_default_plugins
        from app.plugins.framework.registry import get_plugin_registry

        ensure_default_plugins()
        _plugin = get_plugin_registry().lookup("scheduling")  # type: ignore[assignment]
    return attach_intelligence_runtime(_plugin)


def reset_scheduling_plugin() -> None:
    global _plugin
    _plugin = None


def scheduling_plugin_from_ports(
    *,
    scheduling_store: Any | None = None,
    intelligence: Any | None = None,
    monitor: Any | None = None,
) -> SchedulingPlugin:
    """Build unregistered plugin from DecisionPorts (scoped Workflow execution)."""
    return build_scheduling_plugin(
        store=scheduling_store,
        intelligence=intelligence,
        monitor=monitor,
        register=False,
    )
