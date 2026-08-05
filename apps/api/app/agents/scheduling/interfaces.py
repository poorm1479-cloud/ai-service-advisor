"""Scheduling agent ports."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.scheduling.catalog_port import CatalogServiceView, ServiceCatalogPort
from app.agents.scheduling.models import (
    AppointmentRecord,
    SchedulingRequest,
    SchedulingResult,
    TimeSlot,
)

__all__ = [
    "SchedulingStorePort",
    "SchedulingAgentPort",
    "ServiceCatalogPort",
    "CatalogServiceView",
]


class SchedulingStorePort(Protocol):
    async def list_available_slots(
        self,
        shop_id: UUID,
        *,
        days_ahead: int = 7,
        duration_minutes: int | None = None,
        repair_type: str | None = None,
    ) -> list[TimeSlot]: ...

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

    async def get(self, shop_id: UUID, appointment_id: UUID) -> AppointmentRecord | None: ...

    async def list_by_customer(
        self, shop_id: UUID, customer_id: UUID
    ) -> list[AppointmentRecord]: ...


class SchedulingAgentPort(Protocol):
    async def process(
        self, request: SchedulingRequest, context: AgentContext
    ) -> AgentResult[SchedulingResult]: ...
