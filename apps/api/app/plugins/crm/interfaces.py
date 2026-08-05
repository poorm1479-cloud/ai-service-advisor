"""CRM Plugin public interfaces (ports).

Workflow Engine must communicate with CRM only through ICrmPlugin.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.agents.crm.models import TimelineEntry
from app.agents.customer.models import CustomerProfile
from app.agents.vehicle.models import RepairRecord, VehicleRecord


class CustomerServicePort(Protocol):
    """Customer management capabilities."""

    async def find_by_id(self, shop_id: UUID, customer_id: UUID) -> CustomerProfile | None: ...

    async def find_by_phone(self, shop_id: UUID, phone: str) -> list[CustomerProfile]: ...

    async def find_by_email(self, shop_id: UUID, email: str) -> list[CustomerProfile]: ...

    async def search(self, shop_id: UUID, query: str) -> list[CustomerProfile]: ...

    async def create(self, profile: CustomerProfile) -> CustomerProfile: ...

    async def update(self, profile: CustomerProfile) -> CustomerProfile: ...

    async def merge(
        self, shop_id: UUID, primary_id: UUID, duplicate_ids: list[UUID]
    ) -> CustomerProfile: ...

    async def summary(self, shop_id: UUID, customer_id: UUID) -> str: ...


class VehicleServicePort(Protocol):
    """Vehicle management capabilities."""

    async def find_by_id(self, shop_id: UUID, vehicle_id: UUID) -> VehicleRecord | None: ...

    async def find_by_vin(self, shop_id: UUID, vin: str) -> VehicleRecord | None: ...

    async def list_by_customer(self, shop_id: UUID, customer_id: UUID) -> list[VehicleRecord]: ...

    async def search(self, shop_id: UUID, query: str) -> list[VehicleRecord]: ...

    async def create(self, vehicle: VehicleRecord) -> VehicleRecord: ...

    async def update(self, vehicle: VehicleRecord) -> VehicleRecord: ...


class RepairServicePort(Protocol):
    """Repair history capabilities."""

    async def list_by_vehicle(self, shop_id: UUID, vehicle_id: UUID) -> list[RepairRecord]: ...

    async def add(self, shop_id: UUID, repair: RepairRecord) -> RepairRecord: ...


class CommunicationPort(Protocol):
    """Communication history + customer timeline capabilities."""

    async def add_communication(
        self,
        shop_id: UUID,
        customer_id: UUID,
        channel: str,
        message: str,
        direction: str = "incoming",
    ) -> TimelineEntry: ...

    async def add_repair_note(
        self, shop_id: UUID, customer_id: UUID, vehicle_id: UUID | None, note: str
    ) -> TimelineEntry: ...

    async def add_timeline(
        self, shop_id: UUID, customer_id: UUID, kind: str, summary: str
    ) -> TimelineEntry: ...

    async def list_timeline(self, shop_id: UUID, customer_id: UUID) -> list[TimelineEntry]: ...

    async def list_communications(
        self, shop_id: UUID, customer_id: UUID
    ) -> list[TimelineEntry]: ...


class ICrmPlugin(Protocol):
    """CRM Plugin contract — sole CRM entry for Workflow Engine."""

    plugin_id: str

    @property
    def customers(self) -> CustomerServicePort: ...

    @property
    def vehicles(self) -> VehicleServicePort: ...

    @property
    def repairs(self) -> RepairServicePort: ...

    @property
    def communications(self) -> CommunicationPort: ...

    def capabilities(self) -> list[str]: ...

    async def invoke(self, capability: str, **kwargs: Any) -> Any: ...
