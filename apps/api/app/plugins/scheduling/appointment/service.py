"""Appointment service — wraps existing SchedulingStorePort (no rewrite)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.agents.scheduling.interfaces import SchedulingStorePort
from app.agents.scheduling.models import AppointmentRecord
from app.agents.scheduling.service import InMemorySchedulingStore


class AppointmentPluginService:
    def __init__(self, store: SchedulingStorePort | None = None) -> None:
        self._store = store or InMemorySchedulingStore()

    @property
    def store(self) -> SchedulingStorePort:
        return self._store

    async def get(self, shop_id: UUID, appointment_id: UUID) -> AppointmentRecord | None:
        return await self._store.get(shop_id, appointment_id)

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
        duration_minutes: int | None = None,
        repair_type: str | None = None,
        required_bay: str | None = None,
        estimated_revenue: Decimal | None = None,
    ) -> AppointmentRecord:
        return await self._store.book(
            shop_id,
            start=start,
            end=end,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            notes=notes,
            service_id=service_id,
            service_name=service_name,
            duration_minutes=duration_minutes,
            repair_type=repair_type,
            required_bay=required_bay,
            estimated_revenue=estimated_revenue,
        )

    async def reschedule(
        self,
        shop_id: UUID,
        appointment_id: UUID,
        start: datetime,
        end: datetime,
        *,
        service_id: UUID | None = None,
        service_name: str | None = None,
        duration_minutes: int | None = None,
        repair_type: str | None = None,
        required_bay: str | None = None,
        estimated_revenue: Decimal | None = None,
    ) -> AppointmentRecord:
        return await self._store.reschedule(
            shop_id,
            appointment_id,
            start,
            end,
            service_id=service_id,
            service_name=service_name,
            duration_minutes=duration_minutes,
            repair_type=repair_type,
            required_bay=required_bay,
            estimated_revenue=estimated_revenue,
        )

    async def cancel(
        self, shop_id: UUID, appointment_id: UUID, reason: str | None = None
    ) -> AppointmentRecord:
        return await self._store.cancel(shop_id, appointment_id, reason)

    async def history(
        self, shop_id: UUID, *, customer_id: UUID | None = None
    ) -> list[AppointmentRecord]:
        # Best-effort: InMemory store keeps appointments dict; intelligence adapter may not
        raw = getattr(self._store, "_appointments", None)
        if isinstance(raw, dict):
            items = [a for a in raw.values() if a.shop_id == shop_id]
            if customer_id:
                items = [a for a in items if a.customer_id == customer_id]
            return sorted(items, key=lambda a: a.start, reverse=True)
        if customer_id and hasattr(self._store, "list_by_customer"):
            return await self._store.list_by_customer(shop_id, customer_id)  # type: ignore[no-any-return]
        return []
