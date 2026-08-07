"""Availability / validation / conflict — wraps existing store (+ optional engines)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.agents.scheduling.interfaces import SchedulingStorePort
from app.agents.scheduling.models import TimeSlot
from app.agents.scheduling.service import InMemorySchedulingStore

_DEFAULT_DURATIONS = {
    "oil_change": 30,
    "brakes": 120,
    "tires": 60,
    "diagnostic": 60,
    "inspection": 45,
    "walk_in": 45,
    "general": 60,
}


class AvailabilityPluginService:
    def __init__(
        self,
        store: SchedulingStorePort | None = None,
        *,
        intelligence: Any | None = None,
    ) -> None:
        self._store = store or InMemorySchedulingStore()
        self._intelligence = intelligence

    async def find_available_slots(
        self,
        shop_id: UUID,
        *,
        days_ahead: int = 7,
        duration_minutes: int | None = None,
        repair_type: str | None = None,
    ) -> list[TimeSlot]:
        return await self._store.list_available_slots(
            shop_id,
            days_ahead=days_ahead,
            duration_minutes=duration_minutes,
            repair_type=repair_type,
        )

    async def check_availability(
        self, shop_id: UUID, *, start: datetime, end: datetime
    ) -> dict[str, Any]:
        conflict = await self.detect_conflict(shop_id, start=start, end=end)
        return {
            "available": not conflict.get("has_conflict", False),
            "start": start.isoformat(),
            "end": end.isoformat(),
            **conflict,
        }

    async def estimate_duration(self, repair_type: str | None = None) -> int:
        if self._intelligence is not None:
            try:
                from app.scheduling.store import DEFAULT_DURATIONS

                key = (repair_type or "general").lower().replace(" ", "_")
                return int(DEFAULT_DURATIONS.get(key, 60))
            except Exception:  # noqa: BLE001
                pass
        key = (repair_type or "general").lower().replace(" ", "_")
        return _DEFAULT_DURATIONS.get(key, 60)

    async def detect_conflict(
        self,
        shop_id: UUID,
        *,
        start: datetime,
        end: datetime,
        exclude_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Return whether the window has free parallel capacity (staff + bay).

        Uses the same mechanic/bay availability rules as the Schedule calendar.
        Do not treat every time overlap as a hard conflict — shops book in parallel
        up to Team size.
        """
        if self._intelligence is not None:
            try:
                store = self._intelligence._store  # noqa: SLF001
                availability = getattr(self._intelligence, "_availability", None)
                existing = await store.list_appointments(shop_id, start=start, end=end)
                if exclude_id is not None:
                    existing = [a for a in existing if a.id != exclude_id]

                conflicts: list[str] = []
                if availability is not None:
                    mechanics = await store.list_mechanics(shop_id)
                    bays = await store.list_bays(shop_id)
                    free_mech = any(
                        availability.mechanic_available(
                            m,
                            start=start,
                            end=end,
                            existing=existing,
                            ignore_id=exclude_id,
                        )
                        for m in mechanics
                    )
                    free_bay = any(
                        availability.bay_available(
                            b,
                            start=start,
                            end=end,
                            vehicle_type="sedan",
                            existing=existing,
                            required_bay=None,
                            ignore_id=exclude_id,
                        )
                        for b in bays
                    )
                    if not free_mech:
                        conflicts.append("No available staff for this time")
                    if not free_bay:
                        conflicts.append("No available bay for this time")
                    return {
                        "has_conflict": bool(conflicts),
                        "conflicts": conflicts,
                    }

                # No availability engine: fall through to overlap scan below
            except Exception:  # noqa: BLE001
                pass

        # Fallback: scan in-memory appointments (single-slot store / tests)
        raw = getattr(self._store, "_appointments", None)
        conflicts: list[str] = []
        if isinstance(raw, dict):
            for a in raw.values():
                if a.shop_id != shop_id or str(a.status).lower() in {
                    "cancelled",
                    "rescheduled",
                }:
                    continue
                if exclude_id and a.id == exclude_id:
                    continue
                if a.start < end and start < a.end:
                    conflicts.append(f"Overlaps appointment {a.id}")
        return {"has_conflict": bool(conflicts), "conflicts": conflicts}

    async def validate_appointment(
        self,
        shop_id: UUID,
        *,
        start: datetime,
        end: datetime,
        exclude_id: UUID | None = None,
    ) -> dict[str, Any]:
        if end <= start:
            return {"valid": False, "errors": ["end must be after start"]}

        errors: list[str] = []
        # Business hours + parallel capacity are authoritative for AI booking.
        if self._intelligence is not None:
            try:
                hours = await self._intelligence._store.list_business_hours(shop_id)  # noqa: SLF001
                availability = getattr(self._intelligence, "_availability", None)
                if availability is not None and hours is not None:
                    window = availability.day_window(
                        hours, availability.local_date(start)
                    )
                    if window is None:
                        errors.append("Shop is closed on the selected day")
                    elif start < window[0] or end > window[1]:
                        errors.append("Appointment falls outside business hours")
            except Exception:  # noqa: BLE001
                pass

        conflict = await self.detect_conflict(
            shop_id, start=start, end=end, exclude_id=exclude_id
        )
        errors.extend(list(conflict.get("conflicts") or []))
        return {"valid": not errors, "errors": errors, **conflict}
