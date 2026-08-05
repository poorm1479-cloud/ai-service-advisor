"""Scheduling Plugin — wrap existing scheduling as Workflow-facing plugin."""

from app.plugins.scheduling.factory import (
    build_scheduling_plugin,
    get_scheduling_plugin,
    reset_scheduling_plugin,
    scheduling_plugin_from_ports,
)
from app.plugins.scheduling.interfaces import (
    AppointmentServicePort,
    AvailabilityServicePort,
    BayServicePort,
    CalendarServicePort,
    ISchedulingPlugin,
    MechanicServicePort,
)
from app.plugins.scheduling.plugin import SchedulingPlugin

__all__ = [
    "AppointmentServicePort",
    "AvailabilityServicePort",
    "BayServicePort",
    "CalendarServicePort",
    "ISchedulingPlugin",
    "MechanicServicePort",
    "SchedulingPlugin",
    "build_scheduling_plugin",
    "get_scheduling_plugin",
    "reset_scheduling_plugin",
    "scheduling_plugin_from_ports",
]
