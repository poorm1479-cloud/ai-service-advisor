"""In-memory shop resource store for scheduling intelligence."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from app.scheduling.enums import AppointmentStatus
from app.scheduling.models import (
    Appointment,
    Bay,
    BusinessHours,
    Mechanic,
    MechanicSkill,
)


# Default duration by repair type (minutes) — align with STARTER_SERVICES
DEFAULT_DURATIONS: dict[str, int] = {
    "oil_change": 30,
    "brakes": 120,
    "tires": 60,
    "diagnostic": 90,
    "inspection": 60,
    "engine": 240,
    "transmission": 300,
    "electrical": 120,
    "body": 180,
    "general": 60,
    "walk_in": 45,
}

DEFAULT_REVENUE: dict[str, Decimal] = {
    "oil_change": Decimal("79.99"),
    "brakes": Decimal("320.00"),
    "tires": Decimal("180.00"),
    "diagnostic": Decimal("149.00"),
    "inspection": Decimal("99.00"),
    "engine": Decimal("850.00"),
    "transmission": Decimal("1200.00"),
    "electrical": Decimal("250.00"),
    "body": Decimal("400.00"),
    "general": Decimal("120.00"),
    "walk_in": Decimal("90.00"),
}


class ShopResourcePort(Protocol):
    async def list_business_hours(self, shop_id: UUID) -> list[BusinessHours]: ...

    async def list_mechanics(self, shop_id: UUID) -> list[Mechanic]: ...

    async def list_bays(self, shop_id: UUID) -> list[Bay]: ...

    async def list_appointments(
        self,
        shop_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        status: str | None = None,
    ) -> list[Appointment]: ...

    async def get_appointment(self, shop_id: UUID, appointment_id: UUID) -> Appointment | None: ...

    async def save_appointment(self, appointment: Appointment) -> Appointment: ...

    async def update_appointment(self, appointment: Appointment) -> Appointment: ...


def seed_default_shop(shop_id: UUID) -> tuple[list[BusinessHours], list[Mechanic], list[Bay]]:
    hours = [
        BusinessHours(weekday=d, open_time=time(8, 0), close_time=time(17, 0), closed=d >= 5)
        for d in range(7)
    ]
    mechanics = [
        Mechanic(
            id=uuid4(),
            shop_id=shop_id,
            name="Alex Rivera",
            skills=[
                MechanicSkill("oil_change", 5, 40),
                MechanicSkill("brakes", 4, 110),
                MechanicSkill("inspection", 5, 50),
                MechanicSkill("general", 4, 55),
            ],
            hourly_rate=Decimal("72.00"),
        ),
        Mechanic(
            id=uuid4(),
            shop_id=shop_id,
            name="Jordan Lee",
            skills=[
                MechanicSkill("engine", 5, 220),
                MechanicSkill("transmission", 4, 280),
                MechanicSkill("diagnostic", 5, 80),
                MechanicSkill("electrical", 4, 100),
            ],
            hourly_rate=Decimal("95.00"),
        ),
        Mechanic(
            id=uuid4(),
            shop_id=shop_id,
            name="Sam Patel",
            skills=[
                MechanicSkill("tires", 5, 50),
                MechanicSkill("brakes", 3, 130),
                MechanicSkill("walk_in", 4, 40),
                MechanicSkill("general", 3, 65),
            ],
            hourly_rate=Decimal("68.00"),
        ),
    ]
    bays = [
        Bay(id=uuid4(), shop_id=shop_id, name="Bay 1 — Quick", bay_type="quick_service"),
        Bay(id=uuid4(), shop_id=shop_id, name="Bay 2 — General", bay_type="general"),
        Bay(
            id=uuid4(),
            shop_id=shop_id,
            name="Bay 3 — Heavy",
            bay_type="heavy",
            supports_vehicle_types=["truck", "van", "suv", "other"],
        ),
        Bay(id=uuid4(), shop_id=shop_id, name="Bay 4 — Alignment", bay_type="alignment"),
    ]
    return hours, mechanics, bays


class InMemoryShopResourceStore:
    def __init__(self) -> None:
        self.hours: dict[UUID, list[BusinessHours]] = {}
        self.mechanics: dict[UUID, list[Mechanic]] = {}
        self.bays: dict[UUID, list[Bay]] = {}
        self.appointments: dict[UUID, Appointment] = {}
        self._by_shop: dict[UUID, list[UUID]] = defaultdict(list)

    def ensure_shop(self, shop_id: UUID) -> None:
        if shop_id not in self.hours:
            hours, mechanics, bays = seed_default_shop(shop_id)
            self.hours[shop_id] = hours
            self.mechanics[shop_id] = mechanics
            self.bays[shop_id] = bays

    def set_business_hours(self, shop_id: UUID, hours: list[BusinessHours]) -> None:
        """Replace shop hours (e.g. sync from Service Catalog / shop setup)."""
        self.ensure_shop(shop_id)
        self.hours[shop_id] = list(hours)

    def set_mechanics(self, shop_id: UUID, mechanics: list[Mechanic]) -> None:
        """Replace shop mechanics (e.g. sync from Team roster)."""
        self.ensure_shop(shop_id)
        self.mechanics[shop_id] = list(mechanics)

    def set_bays(self, shop_id: UUID, bays: list[Bay]) -> None:
        """Replace shop bays (e.g. sync from Service Catalog bay types)."""
        self.ensure_shop(shop_id)
        self.bays[shop_id] = list(bays)

    async def list_business_hours(self, shop_id: UUID) -> list[BusinessHours]:
        self.ensure_shop(shop_id)
        return list(self.hours[shop_id])

    async def list_mechanics(self, shop_id: UUID) -> list[Mechanic]:
        self.ensure_shop(shop_id)
        return [m for m in self.mechanics[shop_id] if m.active]

    async def list_bays(self, shop_id: UUID) -> list[Bay]:
        self.ensure_shop(shop_id)
        return [b for b in self.bays[shop_id] if b.active]

    async def list_appointments(
        self,
        shop_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        status: str | None = None,
    ) -> list[Appointment]:
        self.ensure_shop(shop_id)
        items = [self.appointments[i] for i in self._by_shop.get(shop_id, []) if i in self.appointments]
        if start:
            items = [a for a in items if a.end > start]
        if end:
            items = [a for a in items if a.start < end]
        if status:
            items = [a for a in items if a.status == status]
        else:
            items = [a for a in items if a.status not in {AppointmentStatus.CANCELLED.value, AppointmentStatus.RESCHEDULED.value}]
        items.sort(key=lambda a: a.start)
        return items

    async def get_appointment(self, shop_id: UUID, appointment_id: UUID) -> Appointment | None:
        appt = self.appointments.get(appointment_id)
        if appt and appt.shop_id == shop_id:
            return appt
        return None

    async def save_appointment(self, appointment: Appointment) -> Appointment:
        self.ensure_shop(appointment.shop_id)
        self.appointments[appointment.id] = appointment
        if appointment.id not in self._by_shop[appointment.shop_id]:
            self._by_shop[appointment.shop_id].append(appointment.id)
        return appointment

    async def update_appointment(self, appointment: Appointment) -> Appointment:
        self.appointments[appointment.id] = appointment
        return appointment
