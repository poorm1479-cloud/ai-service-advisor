"""Scheduling Plugin ports — Workflow communicates only through ISchedulingPlugin."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.agents.scheduling.models import AppointmentRecord, TimeSlot
from app.plugins.framework.context import PluginContext


class AppointmentServicePort(Protocol):
    async def get(self, shop_id: UUID, appointment_id: UUID) -> AppointmentRecord | None: ...

    async def book(
        self,
        shop_id: UUID,
        *,
        start: datetime,
        end: datetime,
        customer_id: UUID | None,
        vehicle_id: UUID | None,
        notes: str | None = None,
        service_id: UUID | None = None,
        service_name: str | None = None,
    ) -> AppointmentRecord: ...

    async def reschedule(
        self, shop_id: UUID, appointment_id: UUID, start: datetime, end: datetime
    ) -> AppointmentRecord: ...

    async def cancel(
        self, shop_id: UUID, appointment_id: UUID, reason: str | None = None
    ) -> AppointmentRecord: ...

    async def history(self, shop_id: UUID, *, customer_id: UUID | None = None) -> list[AppointmentRecord]: ...


class CalendarServicePort(Protocol):
    async def list_slots(self, shop_id: UUID, *, days_ahead: int = 7) -> list[TimeSlot]: ...


class AvailabilityServicePort(Protocol):
    async def find_available_slots(
        self,
        shop_id: UUID,
        *,
        days_ahead: int = 7,
        duration_minutes: int | None = None,
        repair_type: str | None = None,
    ) -> list[TimeSlot]: ...

    async def check_availability(
        self, shop_id: UUID, *, start: datetime, end: datetime
    ) -> dict[str, Any]: ...

    async def estimate_duration(self, repair_type: str | None = None) -> int: ...

    async def detect_conflict(
        self, shop_id: UUID, *, start: datetime, end: datetime, exclude_id: UUID | None = None
    ) -> dict[str, Any]: ...

    async def validate_appointment(
        self, shop_id: UUID, *, start: datetime, end: datetime
    ) -> dict[str, Any]: ...


class MechanicServicePort(Protocol):
    async def list_mechanics(self, shop_id: UUID) -> list[Any]: ...

    async def assign(
        self, shop_id: UUID, appointment_id: UUID, mechanic_id: UUID | None = None
    ) -> dict[str, Any]: ...


class BayServicePort(Protocol):
    async def list_bays(self, shop_id: UUID) -> list[Any]: ...

    async def assign(
        self, shop_id: UUID, appointment_id: UUID, bay_id: UUID | None = None
    ) -> dict[str, Any]: ...


class ISchedulingPlugin(Protocol):
    """Scheduling Plugin contract — sole scheduling entry for Workflow Engine."""

    def plugin_id(self) -> str: ...

    @property
    def appointments(self) -> AppointmentServicePort: ...

    @property
    def calendar(self) -> CalendarServicePort: ...

    @property
    def availability(self) -> AvailabilityServicePort: ...

    @property
    def mechanics(self) -> MechanicServicePort: ...

    @property
    def bays(self) -> BayServicePort: ...

    @property
    def store(self) -> Any: ...

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any: ...
