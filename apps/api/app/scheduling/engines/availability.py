"""Availability engine — business hours, mechanic/bay free windows."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from app.scheduling.models import Appointment, Bay, BusinessHours, Mechanic
from app.scheduling.store import DEFAULT_DURATIONS

# Platform default shop timezone (matches ShopModel / setup defaults).
DEFAULT_SHOP_TZ = ZoneInfo("America/Los_Angeles")

# Only live schedule holds block capacity (matches ConflictEngine.ACTIVE).
_ACTIVE_STATUSES = frozenset({"booked", "confirmed", "in_progress"})


class AvailabilityEngine:
    def __init__(self, *, shop_tz: ZoneInfo | None = None) -> None:
        self._shop_tz = shop_tz or DEFAULT_SHOP_TZ

    def to_shop(self, when: datetime) -> datetime:
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when.astimezone(self._shop_tz)

    def local_date(self, when: datetime) -> date:
        return self.to_shop(when).date()

    def day_bounds_utc(self, day: date) -> tuple[datetime, datetime]:
        """UTC [start, end) covering a full calendar day in the shop timezone."""
        start_local = datetime(day.year, day.month, day.day, tzinfo=self._shop_tz)
        end_local = start_local + timedelta(days=1)
        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

    def today(self, now: datetime | None = None) -> date:
        now = now or datetime.now(timezone.utc)
        return self.local_date(now)

    def estimate_duration(
        self,
        *,
        repair_type: str,
        mechanic: Mechanic | None = None,
        override_min: int | None = None,
    ) -> int:
        if override_min and override_min > 0:
            return override_min
        if mechanic:
            for skill in mechanic.skills:
                if skill.repair_type == repair_type and skill.avg_minutes:
                    return skill.avg_minutes
        return DEFAULT_DURATIONS.get(repair_type, 60)

    def is_shop_open(self, hours: list[BusinessHours], when: datetime) -> bool:
        local = self.to_shop(when)
        weekday = local.weekday()
        for h in hours:
            if h.weekday != weekday:
                continue
            if h.closed:
                return False
            t = local.timetz().replace(tzinfo=None)
            return h.open_time <= t < h.close_time
        return False

    def day_window(
        self, hours: list[BusinessHours], day: date
    ) -> tuple[datetime, datetime] | None:
        """Business-hour window for a calendar day in the shop timezone."""
        for h in hours:
            if h.weekday == day.weekday():
                if h.closed:
                    return None
                start = datetime(
                    day.year,
                    day.month,
                    day.day,
                    h.open_time.hour,
                    h.open_time.minute,
                    tzinfo=self._shop_tz,
                )
                end = datetime(
                    day.year,
                    day.month,
                    day.day,
                    h.close_time.hour,
                    h.close_time.minute,
                    tzinfo=self._shop_tz,
                )
                return start, end
        return None

    def mechanic_available(
        self,
        mechanic: Mechanic,
        *,
        start: datetime,
        end: datetime,
        existing: list[Appointment],
        ignore_id: UUID | None = None,
    ) -> bool:
        if not mechanic.active:
            return False
        local_start = self.to_shop(start)
        local_end = self.to_shop(end)
        workdays = self._workday_set(mechanic.workdays)
        if local_start.weekday() not in workdays:
            return False
        start_t = local_start.timetz().replace(tzinfo=None)
        end_t = local_end.timetz().replace(tzinfo=None)
        if start_t < mechanic.work_start or end_t > mechanic.work_end:
            return False
        for a in existing:
            if ignore_id is not None and a.id == ignore_id:
                continue
            if str(getattr(a, "status", "") or "").lower() not in _ACTIVE_STATUSES:
                continue
            if a.mechanic_id != mechanic.id:
                continue
            if a.start < end and start < a.end:
                return False
        return True

    def bay_available(
        self,
        bay: Bay,
        *,
        start: datetime,
        end: datetime,
        vehicle_type: str,
        existing: list[Appointment],
        required_bay: str | None = None,
        ignore_id: UUID | None = None,
    ) -> bool:
        if not bay.active:
            return False
        if required_bay and bay.bay_type != required_bay:
            return False
        need = (vehicle_type or "").strip().lower()
        if need:
            supported = {
                (v or "").strip().lower() for v in (bay.supports_vehicle_types or [])
            }
            # Empty support list = no restriction (legacy / misconfigured bay).
            if supported and need not in supported:
                return False
        for a in existing:
            if ignore_id is not None and a.id == ignore_id:
                continue
            if str(getattr(a, "status", "") or "").lower() not in _ACTIVE_STATUSES:
                continue
            if a.bay_id != bay.id:
                continue
            if a.start < end and start < a.end:
                return False
        return True

    def mechanic_meets_skill(self, mechanic: Mechanic, required_skill: str) -> bool:
        """True when mechanic has the service's required skill."""
        if not required_skill:
            return True
        return self.skill_match(mechanic, required_skill) > 0

    def generate_candidate_starts(
        self,
        *,
        hours: list[BusinessHours],
        days_ahead: int,
        duration_min: int,
        now: datetime | None = None,
        step_min: int = 30,
        preferred_start: datetime | None = None,
    ) -> list[datetime]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        local_now = self.to_shop(now)
        starts: list[datetime] = []
        for offset in range(days_ahead):
            day = (local_now + timedelta(days=offset)).date()
            window = self.day_window(hours, day)
            if window is None:
                continue
            day_start, day_end = window
            cursor = max(day_start, now + timedelta(minutes=15))
            # Align to step in shop-local wall clock
            local_cursor = self.to_shop(cursor)
            minute = (local_cursor.minute // step_min) * step_min
            aligned_local = local_cursor.replace(
                minute=0, second=0, microsecond=0
            ) + timedelta(minutes=minute)
            cursor = aligned_local
            if cursor < now + timedelta(minutes=15):
                cursor += timedelta(minutes=step_min)
            while cursor + timedelta(minutes=duration_min) <= day_end:
                starts.append(cursor)
                cursor += timedelta(minutes=step_min)
        if preferred_start:
            preferred = preferred_start
            if preferred.tzinfo is None:
                preferred = preferred.replace(tzinfo=self._shop_tz)
            preferred = preferred.replace(second=0, microsecond=0)
            window = self.day_window(hours, self.local_date(preferred))
            if (
                window is not None
                and preferred >= now
                and preferred + timedelta(minutes=duration_min) <= window[1]
                and preferred >= window[0]
                and preferred not in starts
            ):
                starts.insert(0, preferred)
            starts.sort(key=lambda s: abs((s - preferred).total_seconds()))
        return starts

    def skill_match(self, mechanic: Mechanic, repair_type: str) -> int:
        need = self._normalize_skill(repair_type)
        if not need:
            return 1
        best = 0
        for skill in mechanic.skills:
            tag = self._normalize_skill(skill.repair_type)
            if not tag:
                continue
            if tag == need or tag in need or need in tag:
                best = max(best, skill.proficiency)
        return best

    @staticmethod
    def _normalize_skill(value: str | None) -> str:
        raw = (value or "").strip().lower()
        if not raw:
            return ""
        return raw.replace("-", "_").replace(" ", "_")

    @staticmethod
    def _workday_set(workdays: list[int] | list[str] | None) -> set[int]:
        """Normalize workday tags (ints or JSON strings) to weekday 0–6 set."""
        days: set[int] = set()
        for raw in workdays or []:
            try:
                day = int(raw)
            except (TypeError, ValueError):
                continue
            if 0 <= day <= 6:
                days.add(day)
        # Empty list would lock every day; treat as Mon–Fri shop default.
        return days if days else {0, 1, 2, 3, 4}
