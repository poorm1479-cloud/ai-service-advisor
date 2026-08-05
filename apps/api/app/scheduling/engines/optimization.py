"""Optimization engine — best mechanic/bay/slot, forecasts, schedule improvements."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from app.scheduling.engines.availability import AvailabilityEngine
from app.scheduling.engines.conflict import ConflictEngine
from app.scheduling.models import (
    Appointment,
    Bay,
    BusinessHours,
    CapacityForecast,
    Mechanic,
    OptimizedSchedule,
    SlotCandidate,
)
from app.scheduling.store import DEFAULT_REVENUE


class OptimizationEngine:
    def __init__(
        self,
        availability: AvailabilityEngine | None = None,
        conflict: ConflictEngine | None = None,
    ) -> None:
        self._availability = availability or AvailabilityEngine()
        self._conflict = conflict or ConflictEngine()

    def recommend_mechanic(
        self,
        *,
        mechanics: list[Mechanic],
        repair_type: str,
        start: datetime,
        end: datetime,
        existing: list[Appointment],
        priority: str = "normal",
        require_skill: bool = True,
    ) -> tuple[Mechanic | None, list[str]]:
        ranked: list[tuple[float, Mechanic, list[str]]] = []
        for m in mechanics:
            if not self._availability.mechanic_available(
                m, start=start, end=end, existing=existing
            ):
                continue
            skill = self._availability.skill_match(m, repair_type)
            if require_skill and skill <= 0:
                continue
            reasons = []
            score = float(skill) * 20.0
            if skill >= 4:
                reasons.append(f"Strong skill match ({skill}/5) for {repair_type}")
            elif skill > 0:
                reasons.append(f"Capable for {repair_type} ({skill}/5)")
            else:
                score -= 30
                reasons.append("No listed skill — backup assignment")

            load = sum(
                1
                for a in existing
                if a.mechanic_id == m.id
                and self._availability.local_date(a.start)
                == self._availability.local_date(start)
            )
            score -= load * 8
            reasons.append(f"Current day load: {load}")
            # Soft tie-break: prefer floor staff over owner when otherwise equal
            # so Auto assign does not dump every first booking on the owner.
            if (m.role or "").strip().lower() == "owner":
                score -= 0.5
            if priority == "emergency" and skill >= 4:
                score += 25
                reasons.append("Preferred for emergency")
            ranked.append((score, m, reasons))

        if not ranked:
            if require_skill:
                return None, [f"No available mechanic with required skill '{repair_type}'"]
            return None, ["No available mechanic for this time window"]
        # Highest score first; name ASC breaks remaining ties deterministically.
        ranked.sort(key=lambda x: (-x[0], x[1].name.lower()))
        best_score, best, reasons = ranked[0]
        reasons.append(f"Score {best_score:.1f}")
        return best, reasons

    def recommend_bay(
        self,
        *,
        bays: list[Bay],
        vehicle_type: str,
        repair_type: str,
        start: datetime,
        end: datetime,
        existing: list[Appointment],
        required_bay: str | None = None,
    ) -> tuple[Bay | None, list[str]]:
        # Catalog bay type is a soft preference. Hard-filtering by type caps parallel
        # intake below Team size when only one typed bay is free.
        preferred_type = (required_bay or "").strip().lower() or None
        if not preferred_type:
            preferred_type = (
                "quick_service"
                if repair_type in {"oil_change", "inspection", "walk_in"}
                else "general"
            )
            if repair_type in {"engine", "transmission"} or vehicle_type in {"truck", "van"}:
                preferred_type = "heavy"
            if repair_type == "tires":
                preferred_type = "alignment"

        ranked: list[tuple[float, Bay, list[str]]] = []
        for b in bays:
            if not self._availability.bay_available(
                b,
                start=start,
                end=end,
                vehicle_type=vehicle_type,
                existing=existing,
                required_bay=None,
            ):
                continue
            score = 10.0
            reasons: list[str] = []
            if b.bay_type == preferred_type:
                score += 40
                reasons.append(f"Bay type matches preferred ({b.bay_type})")
            elif b.bay_type == "general":
                score += 15
                reasons.append("General bay fallback")
            else:
                reasons.append(f"Alternate bay type ({b.bay_type})")
            load = sum(
                1
                for a in existing
                if a.bay_id == b.id
                and self._availability.local_date(a.start)
                == self._availability.local_date(start)
            )
            score -= load * 6
            reasons.append(f"Bay day load: {load}")
            ranked.append((score, b, reasons))

        if not ranked:
            return None, ["No available bay for this time"]
        ranked.sort(key=lambda x: x[0], reverse=True)
        _, best, reasons = ranked[0]
        return best, reasons

    def rank_slots(
        self,
        *,
        hours: list[BusinessHours],
        mechanics: list[Mechanic],
        bays: list[Bay],
        existing: list[Appointment],
        repair_type: str,
        vehicle_type: str,
        priority: str,
        duration_min: int,
        preferred_start: datetime | None = None,
        required_bay: str | None = None,
        days_ahead: int = 7,
        limit: int = 12,
    ) -> list[SlotCandidate]:
        starts = self._availability.generate_candidate_starts(
            hours=hours,
            days_ahead=days_ahead,
            duration_min=duration_min,
            preferred_start=preferred_start,
        )
        candidates: list[SlotCandidate] = []
        for start in starts:
            end = start + timedelta(minutes=duration_min)
            mechanic, m_reasons = self.recommend_mechanic(
                mechanics=mechanics,
                repair_type=repair_type,
                start=start,
                end=end,
                existing=existing,
                priority=priority,
                require_skill=True,
            )
            if mechanic is None:
                continue
            bay, b_reasons = self.recommend_bay(
                bays=bays,
                vehicle_type=vehicle_type,
                repair_type=repair_type,
                start=start,
                end=end,
                existing=existing,
                required_bay=required_bay,
            )
            if bay is None:
                continue
            report = self._conflict.check_appointment(
                start=start,
                end=end,
                mechanic_id=mechanic.id,
                bay_id=bay.id,
                existing=existing,
                priority=priority,
            )
            if report.has_conflict:
                continue

            score = 50.0
            reasons = list(m_reasons) + list(b_reasons)
            if preferred_start:
                delta_h = abs((start - preferred_start).total_seconds()) / 3600
                score -= delta_h * 5
                reasons.append(f"{delta_h:.1f}h from preferred time")
            if priority == "emergency":
                score += max(0, 40 - (start - datetime.now(timezone.utc)).total_seconds() / 3600)
                reasons.append("Emergency urgency boost")
            wait = self.predict_wait_minutes(existing, start)
            score -= wait * 0.5
            reasons.append(f"Predicted wait ~{wait} min")

            candidates.append(
                SlotCandidate(
                    start=start,
                    end=end,
                    mechanic_id=mechanic.id,
                    bay_id=bay.id,
                    score=score,
                    reasons=reasons,
                    estimated_wait_min=wait,
                    estimated_completion=end,
                )
            )

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:limit]

    def predict_wait_minutes(self, existing: list[Appointment], arrival: datetime) -> int:
        """Simple queue model: unfinished jobs ahead / parallel capacity."""
        day = self._availability.local_date(arrival)
        ahead = [
            a
            for a in existing
            if self._availability.local_date(a.start) == day
            and a.start < arrival
            and a.status in ConflictEngine.ACTIVE
        ]
        if not ahead:
            return 0
        remaining = sum(max(0, int((a.end - arrival).total_seconds() / 60)) for a in ahead if a.end > arrival)
        parallel = max(1, len({a.bay_id for a in ahead if a.bay_id}))
        return int(remaining / parallel)

    def forecast_day(
        self,
        *,
        day: date,
        hours: list[BusinessHours],
        mechanics: list[Mechanic],
        bays: list[Bay],
        appointments: list[Appointment],
    ) -> CapacityForecast:
        window = self._availability.day_window(hours, day)
        if window is None:
            return CapacityForecast(
                day=day,
                total_minutes=0,
                booked_minutes=0,
                utilization=0.0,
                remaining_slots=0,
                overbook_risk=0.0,
                expected_wait_min=0.0,
                expected_revenue=Decimal("0.00"),
            )
        day_start, day_end = window
        open_min = int((day_end - day_start).total_seconds() / 60)
        capacity = open_min * max(1, len(mechanics))
        day_appts = [
            a
            for a in appointments
            if self._availability.local_date(a.start) == day
            and a.status in ConflictEngine.ACTIVE
        ]
        booked = sum(a.estimated_duration_min for a in day_appts)
        util = min(1.0, booked / capacity) if capacity else 0.0
        remaining = max(0, int((capacity - booked) / 60))
        revenue = sum((a.estimated_revenue for a in day_appts), Decimal("0.00"))
        waits = [self.predict_wait_minutes(day_appts, a.start) for a in day_appts]
        avg_wait = sum(waits) / len(waits) if waits else 0.0
        overbook_risk = max(0.0, util - 0.85) * 2 if util > 0.85 else util * 0.2
        return CapacityForecast(
            day=day,
            total_minutes=capacity,
            booked_minutes=booked,
            utilization=round(util, 3),
            remaining_slots=remaining,
            overbook_risk=round(min(1.0, overbook_risk), 3),
            expected_wait_min=round(avg_wait, 1),
            expected_revenue=revenue.quantize(Decimal("0.01")),
        )

    def optimize_day(
        self,
        *,
        shop_id: UUID,
        day: date,
        hours: list[BusinessHours],
        mechanics: list[Mechanic],
        bays: list[Bay],
        appointments: list[Appointment],
    ) -> OptimizedSchedule:
        day_appts = [
            a
            for a in appointments
            if self._availability.local_date(a.start) == day
            and a.status in ConflictEngine.ACTIVE
        ]
        improvements: list[str] = []
        # Re-score assignments and suggest swaps for weak skill matches
        for a in day_appts:
            if not a.mechanic_id:
                improvements.append(f"Assign mechanic to appointment {a.id}")
                continue
            current = next((m for m in mechanics if m.id == a.mechanic_id), None)
            better, reasons = self.recommend_mechanic(
                mechanics=mechanics,
                repair_type=a.repair_type,
                start=a.start,
                end=a.end,
                existing=[x for x in day_appts if x.id != a.id],
                priority=a.priority,
            )
            if better and current and better.id != current.id:
                cur_skill = self._availability.skill_match(current, a.repair_type)
                new_skill = self._availability.skill_match(better, a.repair_type)
                if new_skill > cur_skill:
                    improvements.append(
                        f"Move {a.repair_type} from {current.name} to {better.name} "
                        f"(skill {cur_skill}→{new_skill})"
                    )

        conflicts = self._conflict.detect_schedule_conflicts(day_appts)
        if conflicts:
            improvements.append("Resolve detected conflicts before peak hours")

        mech_util: dict[str, float] = {}
        window = self._availability.day_window(hours, day)
        open_min = int((window[1] - window[0]).total_seconds() / 60) if window else 480
        for m in mechanics:
            booked = sum(
                a.estimated_duration_min for a in day_appts if a.mechanic_id == m.id
            )
            mech_util[m.name] = round(min(1.0, booked / open_min), 3) if open_min else 0.0

        bay_util: dict[str, float] = {}
        for b in bays:
            booked = sum(a.estimated_duration_min for a in day_appts if a.bay_id == b.id)
            bay_util[b.name] = round(min(1.0, booked / open_min), 3) if open_min else 0.0

        revenue = sum((a.estimated_revenue for a in day_appts), Decimal("0.00"))
        waits = [self.predict_wait_minutes(day_appts, a.start) for a in day_appts]
        avg_wait = sum(waits) / len(waits) if waits else 0.0

        # Packing suggestion
        if any(u < 0.4 for u in mech_util.values()) and any(u > 0.85 for u in mech_util.values()):
            improvements.append("Balance load: some mechanics under 40% while others over 85%")

        forecast = self.forecast_day(
            day=day, hours=hours, mechanics=mechanics, bays=bays, appointments=appointments
        )
        if forecast.overbook_risk > 0.5:
            improvements.append("High overbook risk — protect emergency buffer slots")

        return OptimizedSchedule(
            shop_id=shop_id,
            day=day,
            appointments=day_appts,
            improvements=improvements,
            mechanic_utilization=mech_util,
            bay_utilization=bay_util,
            expected_daily_revenue=revenue.quantize(Decimal("0.01")),
            avg_customer_wait_min=round(avg_wait, 1),
            conflicts=conflicts,
        )

    def estimate_revenue(self, repair_type: str, override: Decimal | None = None) -> Decimal:
        if override is not None:
            return override
        return DEFAULT_REVENUE.get(repair_type, Decimal("120.00"))
