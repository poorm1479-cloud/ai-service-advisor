"""CRM Plugin — aggregates customer/vehicle/repair/communication services.

Existing CRM logic is wrapped, not rewritten. Implements IPlugin as the
reference plugin for the AutoRepair OS Plugin Framework.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.agents.customer.models import CustomerProfile
from app.agents.vehicle.models import RepairRecord, VehicleRecord
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.crm.communication.service import CommunicationPluginService
from app.plugins.crm.customer.service import CustomerPluginService
from app.plugins.crm.repair.service import RepairPluginService
from app.plugins.crm.vehicle.service import VehiclePluginService


class CrmPlugin:
    """Reference CRM plugin — IPlugin + ICrmPlugin without rewriting domain logic."""

    def __init__(
        self,
        *,
        customers: CustomerPluginService | None = None,
        vehicles: VehiclePluginService | None = None,
        repairs: RepairPluginService | None = None,
        communications: CommunicationPluginService | None = None,
    ) -> None:
        self._customers = customers or CustomerPluginService()
        self._vehicles = vehicles or VehiclePluginService()
        if repairs is None:
            self._repairs = RepairPluginService(self._vehicles.directory)
        else:
            self._repairs = repairs
        self._communications = communications or CommunicationPluginService()
        self._initialized = False

    # --- IPlugin ---

    def plugin_id(self) -> str:  # noqa: F811 — method shadows legacy attr intentionally
        return "crm"

    def plugin_name(self) -> str:
        return "CRM Plugin"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Customer, vehicle, repair history, communication history, "
            "and timeline management for AutoRepair OS."
        )

    def supported_capabilities(self) -> list[str]:
        return self.capabilities()

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
            "capabilities": len(self.supported_capabilities()),
        }

    @property
    def customers(self) -> CustomerPluginService:
        return self._customers

    @property
    def vehicles(self) -> VehiclePluginService:
        return self._vehicles

    @property
    def repairs(self) -> RepairPluginService:
        return self._repairs

    @property
    def communications(self) -> CommunicationPluginService:
        return self._communications

    def capabilities(self) -> list[str]:
        """Legacy alias for supported_capabilities()."""
        return [
            Capability.FIND_CUSTOMER.value,
            Capability.CREATE_CUSTOMER.value,
            Capability.UPDATE_CUSTOMER.value,
            Capability.MERGE_CUSTOMER.value,
            Capability.SEARCH_CUSTOMER.value,
            Capability.CUSTOMER_SUMMARY.value,
            Capability.FIND_VEHICLE.value,
            Capability.CREATE_VEHICLE.value,
            Capability.UPDATE_VEHICLE.value,
            Capability.SEARCH_VEHICLE.value,
            Capability.REPAIR_HISTORY.value,
            Capability.ADD_REPAIR.value,
            Capability.COMMUNICATION_HISTORY.value,
            Capability.ADD_COMMUNICATION.value,
            Capability.CUSTOMER_TIMELINE.value,
            Capability.ADD_TIMELINE.value,
        ]

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Dispatch a named capability — business logic unchanged from Phase 4."""
        # Merge PluginContext defaults without overriding explicit kwargs
        if context is not None:
            for key, value in context.to_kwargs().items():
                if key.startswith("_"):
                    continue
                kwargs.setdefault(key, value)

        shop_id: UUID = kwargs["shop_id"]

        if capability == Capability.FIND_CUSTOMER:
            customer_id = kwargs.get("customer_id")
            if customer_id:
                return await self._customers.find_by_id(shop_id, customer_id)
            phone = kwargs.get("phone")
            if phone:
                return await self._customers.find_by_phone(shop_id, phone)
            email = kwargs.get("email")
            if email:
                return await self._customers.find_by_email(shop_id, email)
            return None

        if capability == Capability.CREATE_CUSTOMER:
            profile: CustomerProfile = kwargs["profile"]
            return await self._customers.create(profile)

        if capability == Capability.UPDATE_CUSTOMER:
            profile = kwargs["profile"]
            return await self._customers.update(profile)

        if capability == Capability.MERGE_CUSTOMER:
            return await self._customers.merge(
                shop_id, kwargs["primary_id"], list(kwargs["duplicate_ids"])
            )

        if capability == Capability.SEARCH_CUSTOMER:
            return await self._customers.search(shop_id, kwargs.get("query", ""))

        if capability == Capability.CUSTOMER_SUMMARY:
            return await self._customers.summary(shop_id, kwargs["customer_id"])

        if capability == Capability.FIND_VEHICLE:
            vehicle_id = kwargs.get("vehicle_id")
            if vehicle_id:
                return await self._vehicles.find_by_id(shop_id, vehicle_id)
            vin = kwargs.get("vin")
            if vin:
                return await self._vehicles.find_by_vin(shop_id, vin)
            customer_id = kwargs.get("customer_id")
            if customer_id:
                return await self._vehicles.list_by_customer(shop_id, customer_id)
            return None

        if capability == Capability.CREATE_VEHICLE:
            vehicle: VehicleRecord = kwargs["vehicle"]
            return await self._vehicles.create(vehicle)

        if capability == Capability.UPDATE_VEHICLE:
            vehicle = kwargs["vehicle"]
            return await self._vehicles.update(vehicle)

        if capability == Capability.SEARCH_VEHICLE:
            return await self._vehicles.search(shop_id, kwargs.get("query", ""))

        if capability == Capability.REPAIR_HISTORY:
            return await self._repairs.list_by_vehicle(shop_id, kwargs["vehicle_id"])

        if capability == Capability.ADD_REPAIR:
            repair: RepairRecord = kwargs["repair"]
            return await self._repairs.add(shop_id, repair)

        if capability == Capability.COMMUNICATION_HISTORY:
            return await self._communications.list_communications(
                shop_id, kwargs["customer_id"]
            )

        if capability == Capability.ADD_COMMUNICATION:
            return await self._communications.add_communication(
                shop_id,
                kwargs["customer_id"],
                kwargs["channel"],
                kwargs["message"],
                direction=kwargs.get("direction", "incoming"),
            )

        if capability == Capability.CUSTOMER_TIMELINE:
            return await self._communications.list_timeline(shop_id, kwargs["customer_id"])

        if capability == Capability.ADD_TIMELINE:
            return await self._communications.add_timeline(
                shop_id,
                kwargs["customer_id"],
                kwargs.get("kind", "note"),
                kwargs.get("summary") or kwargs.get("note") or "Workflow CRM update",
            )

        raise ValueError(f"Unknown CRM capability: {capability}")
