"""CRM Plugin — wrap existing CRM as a Workflow-facing plugin."""

from app.plugins.crm.factory import (
    build_crm_plugin,
    crm_plugin_from_ports,
    get_crm_plugin,
    reset_crm_plugin,
)
from app.plugins.crm.interfaces import (
    CommunicationPort,
    CustomerServicePort,
    ICrmPlugin,
    RepairServicePort,
    VehicleServicePort,
)
from app.plugins.crm.plugin import CrmPlugin

__all__ = [
    "CommunicationPort",
    "CrmPlugin",
    "CustomerServicePort",
    "ICrmPlugin",
    "RepairServicePort",
    "VehicleServicePort",
    "build_crm_plugin",
    "crm_plugin_from_ports",
    "get_crm_plugin",
    "reset_crm_plugin",
]
