"""Adapter — expose AppointmentIntelligence as agents.SchedulingStorePort."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from app.agents.base.errors import AgentValidationError
from app.agents.scheduling.models import AppointmentRecord, TimeSlot
from app.domain.exceptions import ValidationError
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

    async def _resolve_catalog_revenue(
        self,
        shop_id: UUID,
        *,
        service_id: UUID | None,
        estimated_revenue: Decimal | None,
        repair_type: str | None = None,
        service_name: str | None = None,
    ) -> Decimal | None:
        """Prefer decision revenue; else load shop catalog list price by id/name/skill."""
        if estimated_revenue is not None:
            return Decimal(str(estimated_revenue))
        return await self._intel._catalog_list_price(  # noqa: SLF001
            shop_id,
            service_id,
            skill=repair_type,
            service_name=service_name,
        )

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
                limit=80,
            )
            if slots:
                break
        return [
            TimeSlot(start=s.start, end=s.end, available=True)
            for s in slots
        ]

    async def probe_slot_at(
        self,
        shop_id: UUID,
        *,
        preferred_start: datetime,
        duration_minutes: int | None = None,
        repair_type: str | None = None,
        required_bay: str | None = None,
        exclude_appointment_id: UUID | None = None,
    ) -> TimeSlot | None:
        """True capacity check at an exact preferred start (ignores top-N rank list).

        Ranking only surfaces a subset of free windows. Voice/SMS clock times must
        probe the same builder the UI / book path uses so free staff is honored.
        ``exclude_appointment_id`` frees capacity held by the visit being moved
        (reschedule / same-time service swap must not fail on itself).
        """
        await self._ensure_synced(shop_id)
        skill = (repair_type or "").strip().lower() or "general"
        start = preferred_start
        if start.tzinfo is None:
            start = start.replace(tzinfo=self._intel._availability._shop_tz)  # noqa: SLF001
        start = start.replace(second=0, microsecond=0)
        duration = (
            int(duration_minutes)
            if duration_minutes and int(duration_minutes) > 0
            else None
        )
        attempts = [skill]
        if skill and skill != "general":
            attempts = [skill, "general", ""]
        elif skill == "general":
            attempts = ["general", ""]
        for attempt in attempts:
            exact, _reason = await self._intel._build_slot_at(  # noqa: SLF001
                BookingRequest(
                    shop_id=shop_id,
                    preferred_start=start,
                    repair_type=attempt or "general",
                    priority="normal",
                    estimated_duration_min=duration,
                    required_bay=(required_bay or "").strip().lower() or None,
                ),
                start,
                ignore_appointment_id=exclude_appointment_id,
            )
            if exact is not None:
                return TimeSlot(start=exact.start, end=exact.end, available=True)
        return None

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
        await self._ensure_synced(shop_id)
        span = max(1, int((end - start).total_seconds() / 60))
        duration = (
            int(duration_minutes)
            if duration_minutes and int(duration_minutes) > 0
            else max(30, span)
        )
        skill = (repair_type or "").strip().lower() or "general"
        revenue = await self._resolve_catalog_revenue(
            shop_id,
            service_id=service_id,
            estimated_revenue=estimated_revenue,
            repair_type=skill,
            service_name=service_name,
        )
        result = await self._intel.book(
            BookingRequest(
                shop_id=shop_id,
                preferred_start=start,
                preferred_end=end,
                customer_id=customer_id,
                vehicle_id=vehicle_id,
                estimated_duration_min=duration,
                repair_type=skill,
                required_bay=(required_bay or "").strip().lower() or None,
                source="agent",
                notes=notes,
                service_id=service_id,
                service_name=service_name,
                estimated_revenue=revenue,
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
        del end  # intelligence path derives end from duration + preferred_start
        revenue = await self._resolve_catalog_revenue(
            shop_id,
            service_id=service_id,
            estimated_revenue=estimated_revenue,
            repair_type=repair_type,
            service_name=service_name,
        )
        result = await self._intel.reschedule(
            shop_id=shop_id,
            appointment_id=appointment_id,
            preferred_start=start,
            service_id=service_id,
            service_name=service_name,
            estimated_duration_min=duration_minutes,
            repair_type=repair_type,
            required_bay=required_bay,
            estimated_revenue=revenue,
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
        try:
            appt = await self._intel.cancel(
                shop_id=shop_id, appointment_id=appointment_id, reason=reason
            )
        except ValidationError as exc:
            raise AgentValidationError(str(exc), agent="scheduling") from exc
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
