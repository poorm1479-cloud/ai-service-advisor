"""Conflict engine — overlaps, overbooking, capacity pressure."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from app.scheduling.models import Appointment, ConflictReport, Mechanic, Bay


class ConflictEngine:
    ACTIVE = {"booked", "confirmed", "in_progress"}

    def check_appointment(
        self,
        *,
        start: datetime,
        end: datetime,
        mechanic_id: UUID | None,
        bay_id: UUID | None,
        existing: list[Appointment],
        ignore_id: UUID | None = None,
        priority: str = "normal",
    ) -> ConflictReport:
        conflicts: list[str] = []
        for a in existing:
            if ignore_id and a.id == ignore_id:
                continue
            if a.status not in self.ACTIVE:
                continue
            overlaps = a.start < end and start < a.end
            if not overlaps:
                continue
            if mechanic_id and a.mechanic_id == mechanic_id:
                conflicts.append(f"Mechanic double-booked with appointment {a.id}")
            if bay_id and a.bay_id == bay_id:
                conflicts.append(f"Bay double-booked with appointment {a.id}")
            if not mechanic_id and not bay_id:
                conflicts.append(f"Time overlap with appointment {a.id}")

        overbooked = len(conflicts) > 0
        severity = "none"
        if overbooked:
            severity = "high" if priority == "emergency" else "medium"
        elif self._near_capacity(existing, start):
            severity = "low"
            conflicts.append("Day approaching capacity — consider spreading load")

        return ConflictReport(
            has_conflict=overbooked,
            conflicts=conflicts,
            overbooked=overbooked,
            severity=severity,
        )

    def detect_schedule_conflicts(
        self, appointments: list[Appointment]
    ) -> list[str]:
        issues: list[str] = []
        active = [a for a in appointments if a.status in self.ACTIVE]
        for i, a in enumerate(active):
            for b in active[i + 1 :]:
                if not (a.start < b.end and b.start < a.end):
                    continue
                if a.mechanic_id and a.mechanic_id == b.mechanic_id:
                    issues.append(f"Mechanic conflict: {a.id} vs {b.id}")
                if a.bay_id and a.bay_id == b.bay_id:
                    issues.append(f"Bay conflict: {a.id} vs {b.id}")
        return issues

    def _near_capacity(self, existing: list[Appointment], day_anchor: datetime) -> bool:
        day_start = day_anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_appts = [
            a
            for a in existing
            if a.status in self.ACTIVE and a.start >= day_start and a.start < day_end
        ]
        return len(day_appts) >= 8
