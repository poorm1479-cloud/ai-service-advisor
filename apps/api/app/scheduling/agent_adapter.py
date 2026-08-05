"""Adapter — expose AppointmentIntelligence as agents.SchedulingStorePort."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.agents.base.errors import AgentValidationError
from app.agents.scheduling.models import AppointmentRecord, TimeSlot
from app.scheduling.enums import AppointmentStatus
from app.scheduling.models import BookingRequest
from app.scheduling.service import AppointmentIntelligenceService


class IntelligenceSchedulingStore:
    """Bridges Phase 5 SchedulingAgent to Phase 8 intelligence engines."""

    def __init__(self, intelligence: AppointmentIntelligenceService) -> None:
        self._intel = intelligence

    async def _ensure_synced(self, shop_id: UUID) -> None:
        from app.scheduling.catalog import ensure_shop_resources_synced

        await ensure_shop_resources_synced(shop_id, self._intel._store)  # noqa: SLF001

    async def list_available_slots(
        self,
        shop_id: UUID,
        *,
        days_ahead: int = 7,
        duration_minutes: int | None = None,
        repair_type: str | None = None,
    ) -> list[TimeSlot]:
        await self._ensure_synced(shop_id)
        skill = (repair_type or "").strip().lower()
        # Prefer the matched catalog skill. "general" is only a soft default —
        # Team sync often omits a literal general skill, which would hide real
        # openings the Schedule UI still shows for oil_change / brakes / etc.
        attempts = [skill] if skill else ["general", ""]
        if skill and skill != "general":
            attempts = [skill, "general", ""]
        elif skill == "general":
            attempts = ["general", ""]

        slots: list = []
        for attempt in attempts:
            slots = await self._intel.recommend_slots(
                BookingRequest(
                    shop_id=shop_id,
                    repair_type=attempt,
                    priority="normal",
                    estimated_duration_min=duration_minutes,
                ),
                days_ahead=days_ahead,
                limit=40,
            )
            if slots:
                break
        return [
            TimeSlot(start=s.start, end=s.end, available=True)
            for s in slots
        ]

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
    ) -> AppointmentRecord:
        await self._ensure_synced(shop_id)
        duration = max(30, int((end - start).total_seconds() / 60))
        result = await self._intel.book(
            BookingRequest(
                shop_id=shop_id,
                preferred_start=start,
                preferred_end=end,
                customer_id=customer_id,
                vehicle_id=vehicle_id,
                estimated_duration_min=duration,
                source="agent",
                notes=notes,
                service_id=service_id,
                service_name=service_name,
            )
        )
        if not result.success or result.appointment is None:
            # Do not silently book a different clock time. Falling through made
            # SMS/voice claim a booking while the customer's requested time
            # (often outside business hours) was rejected.
            raise AgentValidationError(
                result.message or "Unable to book requested slot",
                agent="scheduling",
            )
        return _to_record(result.appointment)

    async def reschedule(
        self, shop_id: UUID, appointment_id: UUID, start: datetime, end: datetime
    ) -> AppointmentRecord:
        result = await self._intel.reschedule(
            shop_id=shop_id,
            appointment_id=appointment_id,
            preferred_start=start,
        )
        if not result.success or result.appointment is None:
            raise AgentValidationError(
                result.message or "Unable to reschedule",
                agent="scheduling",
            )
        return _to_record(result.appointment)

    async def cancel(
        self, shop_id: UUID, appointment_id: UUID, reason: str | None = None
    ) -> AppointmentRecord:
        appt = await self._intel.cancel(
            shop_id=shop_id, appointment_id=appointment_id, reason=reason
        )
        if appt is None:
            raise AgentValidationError("Appointment not found", agent="scheduling")
        return _to_record(appt)

    async def get(self, shop_id: UUID, appointment_id: UUID) -> AppointmentRecord | None:
        appt = await self._intel.get_appointment(shop_id, appointment_id)
        return _to_record(appt) if appt else None

    async def list_by_customer(
        self, shop_id: UUID, customer_id: UUID
    ) -> list[AppointmentRecord]:
        """Upcoming / active appointments for conversation context."""
        now = datetime.now(timezone.utc)
        appts = await self._intel.list_appointments(
            shop_id,
            start=now - timedelta(days=1),
            end=now + timedelta(days=60),
        )
        active = {
            AppointmentStatus.BOOKED.value,
            AppointmentStatus.CONFIRMED.value,
            AppointmentStatus.IN_PROGRESS.value,
            "booked",
            "confirmed",
            "in_progress",
        }
        items = [
            _to_record(a)
            for a in appts
            if a.customer_id == customer_id and str(a.status).lower() in active
        ]
        return sorted(items, key=lambda a: a.start)


def _to_record(appt) -> AppointmentRecord:
    return AppointmentRecord(
        id=appt.id,
        shop_id=appt.shop_id,
        customer_id=appt.customer_id,
        vehicle_id=appt.vehicle_id,
        start=appt.start,
        end=appt.end,
        status=appt.status,
        notes=appt.notes,
        service_id=getattr(appt, "service_id", None),
        service_name=getattr(appt, "service_name", None)
        or (appt.metadata.get("service_name") if getattr(appt, "metadata", None) else None),
    )
