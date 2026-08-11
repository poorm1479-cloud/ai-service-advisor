"""Scheduling Plugin — IPlugin reference wrapping existing scheduling stores/services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.agents.scheduling.interfaces import SchedulingStorePort
from app.agents.scheduling.models import AppointmentRecord, Reminder
from app.agents.scheduling.service import InMemorySchedulingStore
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.scheduling.appointment.service import AppointmentPluginService
from app.plugins.scheduling.availability.service import AvailabilityPluginService
from app.plugins.scheduling.bay.service import BayPluginService
from app.plugins.scheduling.calendar.service import CalendarPluginService
from app.plugins.scheduling.mechanic.service import MechanicPluginService


class SchedulingPlugin:
    """Reference Scheduling plugin — wraps existing SchedulingStorePort / intelligence."""

    def __init__(
        self,
        *,
        store: SchedulingStorePort | None = None,
        intelligence: Any | None = None,
        monitor: Any | None = None,
    ) -> None:
        self._store = store or InMemorySchedulingStore()
        self._intelligence = intelligence
        self._monitor = monitor
        self._appointments = AppointmentPluginService(self._store)
        self._calendar = CalendarPluginService(self._store)
        self._availability = AvailabilityPluginService(
            self._store, intelligence=intelligence
        )
        self._mechanics = MechanicPluginService(
            intelligence=intelligence, store=self._store
        )
        self._bays = BayPluginService(intelligence=intelligence, store=self._store)
        self._agents: Any | None = None
        self._initialized = False

    def plugin_id(self) -> str:
        return "scheduling"

    def plugin_name(self) -> str:
        return "Scheduling Plugin"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Appointment, calendar, mechanic/bay assignment, availability, "
            "conflict detection, and walk-in check-in for AutoRepair OS."
        )

    def supported_capabilities(self) -> list[str]:
        return [
            Capability.FIND_AVAILABLE_SLOT.value,
            Capability.BOOK_APPOINTMENT.value,
            Capability.RESCHEDULE_APPOINTMENT.value,
            Capability.CANCEL_APPOINTMENT.value,
            Capability.ASSIGN_MECHANIC.value,
            Capability.ASSIGN_BAY.value,
            Capability.ESTIMATE_DURATION.value,
            Capability.WALK_IN_CHECK_IN.value,
            Capability.CHECK_AVAILABILITY.value,
            Capability.APPOINTMENT_HISTORY.value,
            Capability.VALIDATE_APPOINTMENT.value,
            Capability.DETECT_CONFLICT.value,
        ]

    def capabilities(self) -> list[str]:
        return self.supported_capabilities()

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
            "has_intelligence": self._intelligence is not None,
        }

    @property
    def appointments(self) -> AppointmentPluginService:
        return self._appointments

    @property
    def calendar(self) -> CalendarPluginService:
        return self._calendar

    @property
    def availability(self) -> AvailabilityPluginService:
        return self._availability

    @property
    def mechanics(self) -> MechanicPluginService:
        return self._mechanics

    @property
    def bays(self) -> BayPluginService:
        return self._bays

    @property
    def store(self) -> SchedulingStorePort:
        """Underlying store for agent DI compatibility."""
        return self._store

    @property
    def intelligence(self) -> Any | None:
        return self._intelligence

    @property
    def monitor(self) -> Any | None:
        return self._monitor

    @property
    def agents(self) -> Any | None:
        """Optional agent façade when intelligence runtime is attached."""
        return self._agents

    async def live_snapshot(self, shop_id: UUID, *, now: datetime | None = None) -> dict[str, Any]:
        """Used by Workflow coordinator live aggregation — no direct scheduling import needed."""
        from datetime import timezone
        from decimal import Decimal

        from app.scheduling.engines.availability import AvailabilityEngine

        now = now or datetime.now(timezone.utc)
        # Match Schedule board day bounds (shop timezone, default America/Los_Angeles).
        avail = AvailabilityEngine()
        day = avail.today(now)
        day_start, day_end = avail.day_bounds_utc(day)
        out: dict[str, Any] = {}
        if self._monitor is not None and hasattr(self._monitor, "snapshot"):
            out["monitor"] = self._monitor.snapshot()
        if self._intelligence is not None:
            try:
                # list_appointments already omits cancelled/rescheduled → 총 예약 건수.
                appts = await self._intelligence.list_appointments(
                    shop_id, start=day_start, end=day_end
                )
                forecast = await self._intelligence.capacity_forecast(shop_id, day)
                completed = [
                    a
                    for a in appts
                    if str(getattr(a, "status", "") or "").lower() == "completed"
                ]
                completed_revenue = sum(
                    (
                        Decimal(str(getattr(a, "estimated_revenue", 0) or 0))
                        for a in completed
                    ),
                    Decimal("0"),
                ).quantize(Decimal("0.01"))
                # AI Activity "Appointments created" — count by created_at (shop day),
                # not scheduled start. List without day filter so future bookings count.
                created_today = await self._intelligence.list_appointments(shop_id)
                ai_created = sum(
                    1
                    for a in created_today
                    if _is_ai_appointment_source(getattr(a, "source", None))
                    and _created_in_day_bounds(
                        getattr(a, "created_at", None),
                        day_start=day_start,
                        day_end=day_end,
                    )
                )
                out["appointments_today"] = len(appts)
                out["appointments"] = appts
                out["completed_appointments_today"] = len(completed)
                out["completed_revenue_today"] = str(completed_revenue)
                out["ai_appointments_created_today"] = ai_created
                out["expected_daily_revenue"] = str(
                    getattr(forecast, "expected_revenue", 0) or 0
                )
                out["mechanic_utilization"] = {
                    "shop": float(getattr(forecast, "utilization", 0) or 0)
                }
                return out
            except Exception as exc:  # noqa: BLE001
                out["error"] = str(exc)
        slots = await self._calendar.list_slots(shop_id, days_ahead=1)
        out.setdefault("appointments_today", 0)
        out.setdefault("completed_appointments_today", 0)
        out.setdefault("completed_revenue_today", "0.00")
        out.setdefault("ai_appointments_created_today", 0)
        out["slots_today"] = len(slots)
        return out

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        if context is not None:
            for key, value in context.to_kwargs().items():
                if key.startswith("_"):
                    continue
                kwargs.setdefault(key, value)

        shop_id: UUID = kwargs["shop_id"]

        if capability == Capability.FIND_AVAILABLE_SLOT:
            duration = kwargs.get("duration_minutes")
            repair_type = kwargs.get("repair_type") or kwargs.get("required_skill")
            return await self._availability.find_available_slots(
                shop_id,
                days_ahead=int(kwargs.get("days_ahead", 7)),
                duration_minutes=int(duration) if duration else None,
                repair_type=str(repair_type) if repair_type else None,
            )

        if capability == Capability.CHECK_AVAILABILITY:
            return await self._availability.check_availability(
                shop_id, start=kwargs["start"], end=kwargs["end"]
            )

        if capability == Capability.VALIDATE_APPOINTMENT:
            return await self._availability.validate_appointment(
                shop_id,
                start=kwargs["start"],
                end=kwargs["end"],
                exclude_id=kwargs.get("exclude_id"),
            )

        if capability == Capability.DETECT_CONFLICT:
            return await self._availability.detect_conflict(
                shop_id,
                start=kwargs["start"],
                end=kwargs["end"],
                exclude_id=kwargs.get("exclude_id"),
            )

        if capability == Capability.ESTIMATE_DURATION:
            return await self._availability.estimate_duration(kwargs.get("repair_type"))

        if capability == Capability.BOOK_APPOINTMENT:
            return await self._appointments.book(
                shop_id,
                start=kwargs["start"],
                end=kwargs["end"],
                customer_id=kwargs.get("customer_id"),
                vehicle_id=kwargs.get("vehicle_id"),
                notes=kwargs.get("notes"),
                service_id=kwargs.get("service_id"),
                service_name=kwargs.get("service_name"),
                duration_minutes=kwargs.get("duration_minutes"),
                repair_type=kwargs.get("repair_type") or kwargs.get("required_skill"),
                required_bay=kwargs.get("required_bay"),
                estimated_revenue=kwargs.get("estimated_revenue"),
            )

        if capability == Capability.RESCHEDULE_APPOINTMENT:
            return await self._appointments.reschedule(
                shop_id,
                kwargs["appointment_id"],
                kwargs["start"],
                kwargs["end"],
                service_id=kwargs.get("service_id"),
                service_name=kwargs.get("service_name"),
                duration_minutes=kwargs.get("duration_minutes"),
                repair_type=kwargs.get("repair_type") or kwargs.get("required_skill"),
                required_bay=kwargs.get("required_bay"),
                estimated_revenue=kwargs.get("estimated_revenue"),
            )

        if capability == Capability.CANCEL_APPOINTMENT:
            return await self._appointments.cancel(
                shop_id, kwargs["appointment_id"], kwargs.get("reason")
            )

        if capability == Capability.APPOINTMENT_HISTORY:
            return await self._appointments.history(
                shop_id, customer_id=kwargs.get("customer_id")
            )

        if capability == Capability.ASSIGN_MECHANIC:
            return await self._mechanics.assign(
                shop_id, kwargs["appointment_id"], kwargs.get("mechanic_id")
            )

        if capability == Capability.ASSIGN_BAY:
            return await self._bays.assign(
                shop_id, kwargs["appointment_id"], kwargs.get("bay_id")
            )

        if capability == Capability.WALK_IN_CHECK_IN:
            # Walk-in = book soonest slot (or explicit window) with walk-in note
            start = kwargs.get("start")
            end = kwargs.get("end")
            if start is None or end is None:
                slots = await self._availability.find_available_slots(shop_id, days_ahead=7)
                if not slots:
                    return {"success": False, "message": "No walk-in slots available"}
                start, end = slots[0].start, slots[0].end
            appt = await self._appointments.book(
                shop_id,
                start=start,
                end=end,
                customer_id=kwargs.get("customer_id"),
                vehicle_id=kwargs.get("vehicle_id"),
                notes=kwargs.get("notes") or "walk_in_check_in",
            )
            return {"success": True, "appointment": appt, "walk_in": True}

        raise ValueError(f"Unknown scheduling capability: {capability}")


_AI_APPOINTMENT_SOURCES = frozenset({"agent", "sms", "phone"})


def _is_ai_appointment_source(source: Any) -> bool:
    return str(source or "").strip().lower() in _AI_APPOINTMENT_SOURCES


def _created_in_day_bounds(
    created_at: Any,
    *,
    day_start: datetime,
    day_end: datetime,
) -> bool:
    """True when created_at falls in [day_start, day_end) (UTC-aware bounds)."""
    if created_at is None:
        return False
    if isinstance(created_at, str):
        raw = created_at.strip()
        if not raw:
            return False
        try:
            created_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return False
    if not isinstance(created_at, datetime):
        return False
    if created_at.tzinfo is None:
        created_utc = created_at.replace(tzinfo=timezone.utc)
    else:
        created_utc = created_at.astimezone(timezone.utc)
    return day_start <= created_utc < day_end


def reminders_for(appointment: AppointmentRecord) -> list[Reminder]:
    return [
        Reminder(
            appointment_id=appointment.id,
            channel="sms",
            send_at=appointment.start - timedelta(hours=24),
            message="Reminder: your appointment is tomorrow.",
        ),
        Reminder(
            appointment_id=appointment.id,
            channel="sms",
            send_at=appointment.start - timedelta(hours=2),
            message="Reminder: your appointment is in 2 hours.",
        ),
    ]
