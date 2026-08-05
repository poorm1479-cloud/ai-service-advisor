"""Appointment Intelligence Service — book/reschedule/cancel + AI optimization."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.scheduling.engines.availability import AvailabilityEngine
from app.scheduling.engines.conflict import ConflictEngine
from app.scheduling.engines.optimization import OptimizationEngine
from app.scheduling.enums import AppointmentStatus
from app.scheduling.models import (
    Appointment,
    Bay,
    BookingRequest,
    BookingResult,
    CapacityForecast,
    ConflictReport,
    Mechanic,
    OptimizedSchedule,
    SlotCandidate,
)
from app.scheduling.store import ShopResourcePort

logger = logging.getLogger("asa.scheduling.intelligence")


class AppointmentIntelligenceService:
    """Production scheduling brain used by dashboard + agent adapter."""

    def __init__(
        self,
        *,
        store: ShopResourcePort,
        availability: AvailabilityEngine | None = None,
        conflict: ConflictEngine | None = None,
        optimization: OptimizationEngine | None = None,
    ) -> None:
        self._store = store
        self._availability = availability or AvailabilityEngine()
        self._conflict = conflict or ConflictEngine()
        self._optimization = optimization or OptimizationEngine(
            self._availability, self._conflict
        )

    async def recommend_slots(
        self,
        request: BookingRequest,
        *,
        days_ahead: int = 7,
        limit: int = 10,
    ) -> list[SlotCandidate]:
        hours = await self._store.list_business_hours(request.shop_id)
        mechanics = await self._store.list_mechanics(request.shop_id)
        bays = await self._store.list_bays(request.shop_id)
        existing = await self._store.list_appointments(request.shop_id)
        if request.mechanic_id:
            mechanics = [m for m in mechanics if m.id == request.mechanic_id]
        if request.bay_id:
            bays = [b for b in bays if b.id == request.bay_id]
        preferred = request.preferred_start
        if preferred is not None and preferred.tzinfo is None:
            preferred = preferred.replace(tzinfo=self._availability._shop_tz)
        duration = self._availability.estimate_duration(
            repair_type=request.repair_type,
            override_min=request.estimated_duration_min,
        )
        return self._optimization.rank_slots(
            hours=hours,
            mechanics=mechanics,
            bays=bays,
            existing=existing,
            repair_type=request.repair_type,
            vehicle_type=request.vehicle_type,
            priority=request.priority,
            duration_min=duration,
            preferred_start=preferred,
            required_bay=request.required_bay,
            days_ahead=days_ahead,
            limit=limit,
        )

    async def book(self, request: BookingRequest) -> BookingResult:
        preferred: datetime | None = None
        if request.preferred_start is not None:
            preferred = request.preferred_start
            # Naive timestamps from clients mean shop-local wall clock, not UTC.
            if preferred.tzinfo is None:
                preferred = preferred.replace(tzinfo=self._availability._shop_tz)
            preferred = preferred.replace(second=0, microsecond=0)
            # Keep request in sync so recommend_slots can compare aware datetimes.
            request.preferred_start = preferred
            now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            if preferred.astimezone(timezone.utc) < now:
                return BookingResult(
                    success=False,
                    message="Preferred start cannot be in the past. Pick a current or future time.",
                )

        # Prefer exact start when free. If that minute is at capacity / conflicted,
        # reject with alternatives so the UI can warn — do not silently book the
        # next free slot (often the next day). Emergency still optimizes soonest.
        optimized_away_from_preferred = False
        if preferred is not None and request.priority != "emergency":
            exact, exact_reason = await self._build_slot_at(request, preferred)
            if exact is not None:
                chosen = exact
                slots = [exact]
            else:
                alternatives = await self.recommend_slots(request, limit=5)
                if request.mechanic_id:
                    mech_alts = [
                        s for s in alternatives if s.mechanic_id == request.mechanic_id
                    ]
                    if not mech_alts:
                        return BookingResult(
                            success=False,
                            recommended_slot=alternatives[0] if alternatives else None,
                            alternatives=alternatives[:5],
                            message="Requested teammate has no available slots",
                            conflicts=ConflictReport(
                                has_conflict=True,
                                conflicts=["Requested teammate has no available slots"],
                                overbooked=False,
                                severity="medium",
                            ),
                        )
                    alternatives = mech_alts
                if not alternatives:
                    return BookingResult(
                        success=False,
                        message=exact_reason or "No optimized slots available",
                        conflicts=ConflictReport(
                            has_conflict=True,
                            conflicts=[exact_reason or "Preferred start unavailable"],
                            overbooked=False,
                            severity="medium",
                        ),
                    )
                return BookingResult(
                    success=False,
                    recommended_slot=alternatives[0],
                    alternatives=alternatives[:5],
                    message=exact_reason
                    or (
                        "Requested start time is unavailable. "
                        "Pick another time or try a suggested alternative."
                    ),
                    conflicts=ConflictReport(
                        has_conflict=True,
                        conflicts=[exact_reason or "Preferred start unavailable"],
                        overbooked=False,
                        severity="medium",
                    ),
                )
        else:
            slots = await self.recommend_slots(request)
            if not slots:
                return BookingResult(
                    success=False,
                    message="No optimized slots available",
                    conflicts=self._conflict.check_appointment(
                        start=preferred or datetime.now(timezone.utc),
                        end=(preferred or datetime.now(timezone.utc))
                        + timedelta(hours=1),
                        mechanic_id=None,
                        bay_id=None,
                        existing=await self._store.list_appointments(request.shop_id),
                        priority=request.priority,
                    ),
                )

            chosen = slots[0]
            if request.mechanic_id and chosen.mechanic_id != request.mechanic_id:
                return BookingResult(
                    success=False,
                    message="Requested teammate has no available slots",
                    alternatives=slots[:5],
                    conflicts=ConflictReport(
                        has_conflict=True,
                        conflicts=["Requested teammate has no available slots"],
                        overbooked=False,
                        severity="medium",
                    ),
                )
            if request.bay_id and chosen.bay_id != request.bay_id:
                return BookingResult(
                    success=False,
                    message="Requested bay has no available slots",
                    alternatives=slots[:5],
                    conflicts=ConflictReport(
                        has_conflict=True,
                        conflicts=["Requested bay has no available slots"],
                        overbooked=False,
                        severity="medium",
                    ),
                )

        duration = int((chosen.end - chosen.start).total_seconds() / 60)
        # Catalog duration is authoritative when provided (drives end_time)
        if request.estimated_duration_min and request.estimated_duration_min > 0:
            duration = request.estimated_duration_min
            chosen_end = chosen.start + timedelta(minutes=duration)
        else:
            chosen_end = chosen.end

        # Reject slots that fall outside business hours (full appointment window)
        hours = await self._store.list_business_hours(request.shop_id)
        window = self._availability.day_window(
            hours, self._availability.local_date(chosen.start)
        )
        if window is None or chosen.start < window[0] or chosen_end > window[1]:
            return BookingResult(
                success=False,
                recommended_slot=chosen,
                alternatives=slots[1:5],
                message="Appointment falls outside business hours",
                conflicts=ConflictReport(
                    has_conflict=True,
                    conflicts=["Outside business hours"],
                    overbooked=False,
                    severity="high",
                ),
            )

        existing = await self._store.list_appointments(request.shop_id)
        mechanics = await self._store.list_mechanics(request.shop_id)
        bays = await self._store.list_bays(request.shop_id)

        # Exact preferred path already assigned a free mechanic/bay at that time.
        # Keep skill/bay-type as soft preferences there so availability wins.
        from_preferred = (
            preferred is not None
            and request.priority != "emergency"
            and not optimized_away_from_preferred
            and chosen.start == preferred
        )
        requirement_conflicts = self._check_resource_requirements(
            request=request,
            start=chosen.start,
            end=chosen_end,
            mechanic_id=chosen.mechanic_id,
            bay_id=chosen.bay_id,
            mechanics=mechanics,
            bays=bays,
            existing=existing,
            enforce_skill=not from_preferred,
        )
        if requirement_conflicts:
            return BookingResult(
                success=False,
                recommended_slot=chosen,
                alternatives=slots[1:5],
                conflicts=ConflictReport(
                    has_conflict=True,
                    conflicts=requirement_conflicts,
                    overbooked=False,
                    severity="high",
                ),
                message=requirement_conflicts[0],
            )

        report = self._conflict.check_appointment(
            start=chosen.start,
            end=chosen_end,
            mechanic_id=chosen.mechanic_id,
            bay_id=chosen.bay_id,
            existing=existing,
            priority=request.priority,
        )
        if report.has_conflict and request.priority != "emergency":
            return BookingResult(
                success=False,
                recommended_slot=chosen,
                alternatives=slots[1:5],
                conflicts=report,
                message="Conflict detected — see alternatives",
            )

        revenue = self._optimization.estimate_revenue(
            request.repair_type, request.estimated_revenue
        )
        meta: dict = {
            "ai_reasons": chosen.reasons,
            "score": chosen.score,
            "required_skill": request.repair_type,
        }
        if request.required_bay:
            meta["required_bay"] = request.required_bay
        if request.service_id:
            meta["service_id"] = str(request.service_id)
        if request.service_name:
            meta["service_name"] = request.service_name
        appt = Appointment(
            id=uuid4(),
            shop_id=request.shop_id,
            start=chosen.start,
            end=chosen_end,
            status=AppointmentStatus.BOOKED.value,
            priority=request.priority,
            repair_type=request.repair_type,
            vehicle_type=request.vehicle_type,
            estimated_duration_min=duration,
            service_id=request.service_id,
            customer_id=request.customer_id,
            vehicle_id=request.vehicle_id,
            mechanic_id=chosen.mechanic_id,
            bay_id=chosen.bay_id,
            walk_in_id=request.walk_in_id,
            source=request.source,
            notes=request.notes,
            estimated_revenue=revenue,
            estimated_completion=chosen_end,
            wait_time_min=chosen.estimated_wait_min,
            created_at=datetime.now(timezone.utc),
            metadata=meta,
        )
        saved = await self._store.save_appointment(appt)
        mech_name = next((m.name for m in mechanics if m.id == saved.mechanic_id), None)
        bay_name = next((b.name for b in bays if b.id == saved.bay_id), None)

        logger.info(
            "scheduling.booked id=%s mechanic=%s bay=%s",
            saved.id,
            mech_name,
            bay_name,
        )
        try:
            from app.workflows.emitter import emit_domain_event
            from app.workflows.enums import DomainEventType

            await emit_domain_event(
                shop_id=request.shop_id,
                event_type=DomainEventType.APPOINTMENT_BOOKED,
                payload={
                    "appointment_id": str(saved.id),
                    "service_id": str(saved.service_id) if saved.service_id else None,
                    "service_name": saved.metadata.get("service_name"),
                    "customer_id": str(saved.customer_id) if saved.customer_id else None,
                    "vehicle_id": str(saved.vehicle_id) if saved.vehicle_id else None,
                    "mechanic_id": str(saved.mechanic_id) if saved.mechanic_id else None,
                    "bay_id": str(saved.bay_id) if saved.bay_id else None,
                    "repair_type": saved.repair_type,
                    "priority": saved.priority,
                    "estimated_duration_min": saved.estimated_duration_min,
                    "estimated_revenue": str(saved.estimated_revenue),
                    "start_time": saved.start.isoformat(),
                    "end_time": saved.end.isoformat(),
                    "start": saved.start.isoformat(),
                    "end": saved.end.isoformat(),
                },
                source="scheduling",
                correlation_id=str(saved.id),
            )
        except Exception:  # noqa: BLE001 — workflows must not break booking
            logger.exception("workflow.emit appointment.booked failed")

        return BookingResult(
            success=True,
            appointment=saved,
            recommended_slot=chosen,
            alternatives=slots[1:5],
            conflicts=report,
            message="Appointment booked",
            ai_decisions={
                "preferred_start": preferred.isoformat() if preferred else None,
                "optimized_away_from_preferred": optimized_away_from_preferred,
                "mechanic_id": str(saved.mechanic_id) if saved.mechanic_id else None,
                "mechanic_name": mech_name,
                "bay_id": str(saved.bay_id) if saved.bay_id else None,
                "bay_name": bay_name,
                "estimated_duration_min": duration,
                "estimated_completion": saved.estimated_completion.isoformat()
                if saved.estimated_completion
                else None,
                "estimated_wait_min": saved.wait_time_min,
                "estimated_revenue": str(saved.estimated_revenue),
                "reasons": chosen.reasons,
            },
        )

    async def reschedule(
        self,
        *,
        shop_id: UUID,
        appointment_id: UUID,
        preferred_start: datetime | None = None,
    ) -> BookingResult:
        existing = await self._store.get_appointment(shop_id, appointment_id)
        if existing is None:
            return BookingResult(success=False, message="Appointment not found")

        # Free the current slot only while we attempt rebook; restore on failure.
        original_status = existing.status
        existing.status = AppointmentStatus.RESCHEDULED.value
        await self._store.update_appointment(existing)

        meta = existing.metadata or {}
        # Default to next day so one-click reschedule does not silently rebook
        # the exact same freed slot (looks like the button did nothing).
        target_start = preferred_start or (existing.start + timedelta(days=1))
        booking = BookingRequest(
            shop_id=shop_id,
            preferred_start=target_start,
            customer_id=existing.customer_id,
            vehicle_id=existing.vehicle_id,
            service_id=existing.service_id,
            service_name=meta.get("service_name"),
            repair_type=existing.repair_type,
            required_bay=meta.get("required_bay"),
            vehicle_type=existing.vehicle_type,
            priority=existing.priority,
            estimated_duration_min=existing.estimated_duration_min,
            source=existing.source,
            notes=f"Rescheduled from {existing.id}",
            walk_in_id=existing.walk_in_id,
            estimated_revenue=existing.estimated_revenue,
        )
        result = await self.book(booking)
        # Catalog bay types may have changed since original book — retry soft.
        if not result.success and booking.required_bay:
            booking.required_bay = None
            result = await self.book(booking)

        if not result.success:
            existing.status = original_status
            await self._store.update_appointment(existing)
            return result

        if result.appointment:
            result.appointment.metadata["rescheduled_from"] = str(existing.id)
            await self._store.update_appointment(result.appointment)
        return result

    async def cancel(
        self, *, shop_id: UUID, appointment_id: UUID, reason: str | None = None
    ) -> Appointment | None:
        appt = await self._store.get_appointment(shop_id, appointment_id)
        if appt is None:
            return None
        appt.status = AppointmentStatus.CANCELLED.value
        if reason:
            appt.notes = f"{appt.notes or ''} | Cancelled: {reason}".strip(" |")
        updated = await self._store.update_appointment(appt)
        try:
            from app.workflows.emitter import emit_domain_event
            from app.workflows.enums import DomainEventType

            await emit_domain_event(
                shop_id=shop_id,
                event_type=DomainEventType.APPOINTMENT_CANCELLED,
                payload={
                    "appointment_id": str(appt.id),
                    "customer_id": str(appt.customer_id) if appt.customer_id else None,
                    "reason": reason,
                    "estimated_revenue": str(appt.estimated_revenue),
                },
                source="scheduling",
                correlation_id=str(appt.id),
            )
        except Exception:  # noqa: BLE001
            logger.exception("workflow.emit appointment.cancelled failed")
        return updated

    async def get_appointment(self, shop_id: UUID, appointment_id: UUID) -> Appointment | None:
        return await self._store.get_appointment(shop_id, appointment_id)

    async def list_appointments(
        self,
        shop_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Appointment]:
        return await self._store.list_appointments(shop_id, start=start, end=end)

    async def capacity_forecast(
        self, shop_id: UUID, day: date
    ) -> CapacityForecast:
        hours = await self._store.list_business_hours(shop_id)
        mechanics = await self._store.list_mechanics(shop_id)
        bays = await self._store.list_bays(shop_id)
        day_start, day_end = self._availability.day_bounds_utc(day)
        appts = await self._store.list_appointments(shop_id, start=day_start, end=day_end)
        return self._optimization.forecast_day(
            day=day, hours=hours, mechanics=mechanics, bays=bays, appointments=appts
        )

    async def optimize_schedule(
        self, shop_id: UUID, day: date
    ) -> OptimizedSchedule:
        hours = await self._store.list_business_hours(shop_id)
        mechanics = await self._store.list_mechanics(shop_id)
        bays = await self._store.list_bays(shop_id)
        day_start, day_end = self._availability.day_bounds_utc(day)
        appts = await self._store.list_appointments(shop_id, start=day_start, end=day_end)
        return self._optimization.optimize_day(
            shop_id=shop_id,
            day=day,
            hours=hours,
            mechanics=mechanics,
            bays=bays,
            appointments=appts,
        )

    async def detect_conflicts(self, shop_id: UUID, day: date) -> list[str]:
        day_start, day_end = self._availability.day_bounds_utc(day)
        appts = await self._store.list_appointments(shop_id, start=day_start, end=day_end)
        return self._conflict.detect_schedule_conflicts(appts)

    async def list_mechanics(self, shop_id: UUID):
        return await self._store.list_mechanics(shop_id)

    async def list_bays(self, shop_id: UUID):
        return await self._store.list_bays(shop_id)

    async def list_business_hours(self, shop_id: UUID):
        return await self._store.list_business_hours(shop_id)

    def _check_resource_requirements(
        self,
        *,
        request: BookingRequest,
        start: datetime,
        end: datetime,
        mechanic_id: UUID | None,
        bay_id: UUID | None,
        mechanics: list[Mechanic],
        bays: list[Bay],
        existing: list[Appointment],
        enforce_skill: bool = True,
    ) -> list[str]:
        """Validate required skill + mechanic/bay availability for the chosen slot."""
        conflicts: list[str] = []
        mechanic = next((m for m in mechanics if m.id == mechanic_id), None)
        if mechanic is None:
            conflicts.append("No mechanic assigned for appointment")
        else:
            if enforce_skill and not self._availability.mechanic_meets_skill(
                mechanic, request.repair_type
            ):
                conflicts.append(
                    f"Mechanic lacks required skill '{request.repair_type}'"
                )
            elif not self._availability.mechanic_available(
                mechanic, start=start, end=end, existing=existing
            ):
                conflicts.append("Mechanic is not available for this time window")

        bay = next((b for b in bays if b.id == bay_id), None)
        if bay is None:
            conflicts.append("No bay assigned for appointment")
        else:
            # Bay type is a soft preference — only occupancy/vehicle matter here.
            if not self._availability.bay_available(
                bay,
                start=start,
                end=end,
                vehicle_type=request.vehicle_type,
                existing=existing,
                required_bay=None,
            ):
                conflicts.append("Bay is not available for this time window")
        return conflicts

    async def _build_slot_at(
        self,
        request: BookingRequest,
        start: datetime,
    ) -> tuple[SlotCandidate | None, str | None]:
        """Assign the best free mechanic/bay at an exact start time."""
        hours = await self._store.list_business_hours(request.shop_id)
        mechanics = await self._store.list_mechanics(request.shop_id)
        bays = await self._store.list_bays(request.shop_id)
        existing = await self._store.list_appointments(request.shop_id)
        duration = self._availability.estimate_duration(
            repair_type=request.repair_type,
            override_min=request.estimated_duration_min,
        )
        end = start + timedelta(minutes=duration)

        window = self._availability.day_window(hours, self._availability.local_date(start))
        if window is None:
            return None, "Shop is closed on the selected day"
        if start < window[0] or end > window[1]:
            return None, "Appointment falls outside business hours"

        pool = mechanics
        if request.mechanic_id:
            pool = [m for m in mechanics if m.id == request.mechanic_id]
            if not pool:
                return None, "Requested mechanic was not found"

        mechanic, m_reasons = self._optimization.recommend_mechanic(
            mechanics=pool,
            repair_type=request.repair_type,
            start=start,
            end=end,
            existing=existing,
            priority=request.priority,
            require_skill=True,
        )
        if mechanic is None:
            # Team roster may not have catalog skill tags; still allow free staff.
            mechanic, m_reasons = self._optimization.recommend_mechanic(
                mechanics=pool,
                repair_type=request.repair_type,
                start=start,
                end=end,
                existing=existing,
                priority=request.priority,
                require_skill=False,
            )
        if mechanic is None:
            if request.mechanic_id:
                return None, "Requested mechanic is not available for this time"
            reason = m_reasons[0] if m_reasons else "No available staff for this time"
            if "required skill" in reason.lower():
                reason = "No available staff for this time"
            return None, reason

        bay: Bay | None = None
        b_reasons: list[str] = []
        if request.bay_id:
            bay = next((b for b in bays if b.id == request.bay_id), None)
            if bay is None:
                return None, "Requested bay was not found"
            if not self._availability.bay_available(
                bay,
                start=start,
                end=end,
                vehicle_type=request.vehicle_type,
                existing=existing,
                required_bay=None,
            ):
                return None, "Requested bay is not available for this time"
            b_reasons = [f"Requested bay {bay.name}"]
        else:
            bay, b_reasons = self._optimization.recommend_bay(
                bays=bays,
                vehicle_type=request.vehicle_type,
                repair_type=request.repair_type,
                start=start,
                end=end,
                existing=existing,
                required_bay=request.required_bay,
            )
            # Soft fallback: catalog bay type may be over-constrained vs free capacity.
            if bay is None and request.required_bay:
                bay, b_reasons = self._optimization.recommend_bay(
                    bays=bays,
                    vehicle_type=request.vehicle_type,
                    repair_type=request.repair_type,
                    start=start,
                    end=end,
                    existing=existing,
                    required_bay=None,
                )
        if bay is None:
            return None, b_reasons[0] if b_reasons else "No available bay for this time"

        report = self._conflict.check_appointment(
            start=start,
            end=end,
            mechanic_id=mechanic.id,
            bay_id=bay.id,
            existing=existing,
            priority=request.priority,
        )
        if report.has_conflict and request.priority != "emergency":
            return None, report.conflicts[0] if report.conflicts else "Conflict at preferred start"

        wait = self._optimization.predict_wait_minutes(existing, start)
        return (
            SlotCandidate(
                start=start,
                end=end,
                mechanic_id=mechanic.id,
                bay_id=bay.id,
                score=100.0,
                reasons=list(m_reasons) + list(b_reasons) + ["Exact preferred start"],
                estimated_wait_min=wait,
                estimated_completion=end,
            ),
            None,
        )
