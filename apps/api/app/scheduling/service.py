"""Appointment Intelligence Service — book/reschedule/cancel/complete + AI optimization."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.exceptions import ValidationError
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

    async def _catalog_list_price(
        self,
        shop_id: UUID,
        service_id: UUID | None = None,
        *,
        skill: str | None = None,
        service_name: str | None = None,
    ) -> Decimal | None:
        """Load shop catalog list price (id → name → skill). Prefer shop settings over DEFAULT_REVENUE."""
        try:
            from sqlalchemy import text

            from app.infrastructure.database import SessionLocal
            from app.scheduling.catalog import resolve_bookable_service
            from app.shop_setup.service import ShopSetupService

            async with SessionLocal() as session:
                await session.execute(
                    text("SELECT set_config('app.shop_id', :sid, true)"),
                    {"sid": str(shop_id)},
                )
                if service_id is not None:
                    try:
                        service = await resolve_bookable_service(
                            session, shop_id=shop_id, service_id=service_id
                        )
                        return Decimal(str(service.price))
                    except Exception:  # noqa: BLE001 — fall through to name/skill
                        logger.debug(
                            "scheduling.catalog_price_by_id_failed shop=%s service=%s",
                            shop_id,
                            service_id,
                            exc_info=True,
                        )

                services = await ShopSetupService(session).list_services(
                    shop_id, active_only=True
                )
                if not services:
                    return None

                name_key = (service_name or "").strip().casefold()
                if name_key:
                    for row in services:
                        if str(row.name or "").strip().casefold() == name_key:
                            return Decimal(str(row.price))
                    for row in services:
                        row_name = str(row.name or "").strip().casefold()
                        if name_key in row_name or row_name in name_key:
                            return Decimal(str(row.price))

                skill_key = (skill or "").strip().casefold()
                if skill_key and skill_key not in {"", "general", "walk_in"}:
                    skill_hits = [
                        row
                        for row in services
                        if str(row.skill or "").strip().casefold() == skill_key
                    ]
                    if len(skill_hits) == 1:
                        return Decimal(str(skill_hits[0].price))
                    if skill_hits:
                        # Prefer the cheapest active skill match (list price, not upsell).
                        return min(
                            (Decimal(str(row.price)) for row in skill_hits),
                            default=None,
                        )
        except Exception:  # noqa: BLE001 — offline / tests → DEFAULT_REVENUE
            logger.debug(
                "scheduling.catalog_price_lookup_failed shop=%s service=%s skill=%s name=%s",
                shop_id,
                service_id,
                skill,
                service_name,
                exc_info=True,
            )
        return None

    async def _resolve_booking_revenue(
        self,
        *,
        shop_id: UUID,
        repair_type: str,
        estimated_revenue: Decimal | None,
        service_id: UUID | None = None,
        service_name: str | None = None,
    ) -> Decimal:
        """Prefer explicit/catalog list price; DEFAULT_REVENUE only as last resort."""
        override = estimated_revenue
        if override is None:
            override = await self._catalog_list_price(
                shop_id,
                service_id,
                skill=repair_type,
                service_name=service_name,
            )
        return self._optimization.estimate_revenue(repair_type, override)

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
        # Walk-in "start service" books at the counter moment onto the schedule.
        # Only source=walk_in (not reschedule of a prior walk-in appointment).
        if request.source == "walk_in":
            return await self._book_walk_in_start(request)

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

        revenue = await self._resolve_booking_revenue(
            shop_id=request.shop_id,
            repair_type=request.repair_type,
            estimated_revenue=request.estimated_revenue,
            service_id=request.service_id,
            service_name=request.service_name,
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

    async def _book_walk_in_start(self, request: BookingRequest) -> BookingResult:
        """Book a walk-in at the counter moment — only during business hours."""
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        preferred = request.preferred_start
        if preferred is not None:
            if preferred.tzinfo is None:
                preferred = preferred.replace(tzinfo=self._availability._shop_tz)
            preferred = preferred.replace(second=0, microsecond=0)
            # Counter clock skew: clamp slightly-past times up to now.
            if preferred.astimezone(timezone.utc) < now - timedelta(minutes=2):
                preferred = now.astimezone(preferred.tzinfo)
            elif preferred.astimezone(timezone.utc) < now:
                preferred = now.astimezone(preferred.tzinfo)
        else:
            preferred = now.astimezone(self._availability._shop_tz)

        request.preferred_start = preferred
        duration = self._availability.estimate_duration(
            repair_type=request.repair_type,
            override_min=request.estimated_duration_min,
        )
        end = preferred + timedelta(minutes=duration)

        hours = await self._store.list_business_hours(request.shop_id)
        window = self._availability.day_window(
            hours, self._availability.local_date(preferred)
        )
        if window is None:
            return BookingResult(
                success=False,
                message="Shop is closed today — walk-in service cannot start outside business hours.",
                conflicts=ConflictReport(
                    has_conflict=True,
                    conflicts=["Shop is closed"],
                    overbooked=False,
                    severity="high",
                ),
            )
        if preferred < window[0] or end > window[1]:
            return BookingResult(
                success=False,
                message="Walk-in service can only start during business hours.",
                conflicts=ConflictReport(
                    has_conflict=True,
                    conflicts=["Outside business hours"],
                    overbooked=False,
                    severity="high",
                ),
            )

        mechanics = await self._store.list_mechanics(request.shop_id)
        bays = await self._store.list_bays(request.shop_id)
        existing = await self._store.list_appointments(request.shop_id)

        pool = mechanics
        if request.mechanic_id:
            pool = [m for m in mechanics if m.id == request.mechanic_id] or mechanics

        mechanic, m_reasons = self._optimization.recommend_mechanic(
            mechanics=pool,
            repair_type=request.repair_type,
            start=preferred,
            end=end,
            existing=existing,
            priority="emergency",
            require_skill=False,
        )
        if mechanic is None and pool:
            mechanic = pool[0]
            m_reasons = ["Walk-in assigned first available teammate"]

        bay: Bay | None = None
        b_reasons: list[str] = []
        if request.bay_id:
            bay = next((b for b in bays if b.id == request.bay_id), None)
        if bay is None:
            bay, b_reasons = self._optimization.recommend_bay(
                bays=bays,
                vehicle_type=request.vehicle_type,
                repair_type=request.repair_type,
                start=preferred,
                end=end,
                existing=existing,
                required_bay=None,
            )
        if bay is None and bays:
            bay = bays[0]
            b_reasons = ["Walk-in assigned first available bay"]

        revenue = await self._resolve_booking_revenue(
            shop_id=request.shop_id,
            repair_type=request.repair_type,
            estimated_revenue=request.estimated_revenue,
            service_id=request.service_id,
            service_name=request.service_name,
        )
        reasons = list(m_reasons) + list(b_reasons) + ["Walk-in service started now"]
        meta: dict = {
            "ai_reasons": reasons,
            "score": 100.0,
            "required_skill": request.repair_type,
            "walk_in_start": True,
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
            start=preferred,
            end=end,
            status=AppointmentStatus.IN_PROGRESS.value,
            priority=request.priority or "normal",
            repair_type=request.repair_type,
            vehicle_type=request.vehicle_type,
            estimated_duration_min=duration,
            service_id=request.service_id,
            customer_id=request.customer_id,
            vehicle_id=request.vehicle_id,
            mechanic_id=mechanic.id if mechanic else None,
            bay_id=bay.id if bay else None,
            walk_in_id=request.walk_in_id,
            source="walk_in",
            notes=request.notes,
            estimated_revenue=revenue,
            estimated_completion=end,
            wait_time_min=0,
            created_at=datetime.now(timezone.utc),
            metadata=meta,
        )
        saved = await self._store.save_appointment(appt)
        mech_name = next((m.name for m in mechanics if m.id == saved.mechanic_id), None)
        bay_name = next((b.name for b in bays if b.id == saved.bay_id), None)

        logger.info(
            "scheduling.walk_in_started id=%s mechanic=%s bay=%s",
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
                    "walk_in_id": str(saved.walk_in_id) if saved.walk_in_id else None,
                    "repair_type": saved.repair_type,
                    "priority": saved.priority,
                    "estimated_duration_min": saved.estimated_duration_min,
                    "estimated_revenue": str(saved.estimated_revenue),
                    "start_time": saved.start.isoformat(),
                    "end_time": saved.end.isoformat(),
                    "start": saved.start.isoformat(),
                    "end": saved.end.isoformat(),
                    "source": "walk_in",
                },
                source="scheduling",
                correlation_id=str(saved.id),
            )
        except Exception:  # noqa: BLE001 — workflows must not break booking
            logger.exception("workflow.emit walk-in appointment.booked failed")

        slot = SlotCandidate(
            start=preferred,
            end=end,
            mechanic_id=saved.mechanic_id,
            bay_id=saved.bay_id,
            score=100.0,
            reasons=reasons,
            estimated_wait_min=0,
            estimated_completion=end,
        )
        return BookingResult(
            success=True,
            appointment=saved,
            recommended_slot=slot,
            message="Walk-in service started",
            ai_decisions={
                "preferred_start": preferred.isoformat(),
                "walk_in_start": True,
                "mechanic_id": str(saved.mechanic_id) if saved.mechanic_id else None,
                "mechanic_name": mech_name,
                "bay_id": str(saved.bay_id) if saved.bay_id else None,
                "bay_name": bay_name,
                "estimated_duration_min": duration,
                "estimated_completion": end.isoformat(),
                "estimated_wait_min": 0,
                "estimated_revenue": str(saved.estimated_revenue),
                "reasons": reasons,
            },
        )

    async def reschedule(
        self,
        *,
        shop_id: UUID,
        appointment_id: UUID,
        preferred_start: datetime | None = None,
        service_id: UUID | None = None,
        service_name: str | None = None,
        estimated_duration_min: int | None = None,
        repair_type: str | None = None,
        required_bay: str | None = None,
        estimated_revenue: Decimal | None = None,
        mechanic_id: UUID | None = None,
    ) -> BookingResult:
        existing = await self._store.get_appointment(shop_id, appointment_id)
        if existing is None:
            return BookingResult(success=False, message="Appointment not found")
        if existing.status not in self._ACTIVE_STATUSES:
            return BookingResult(
                success=False,
                message=f"Cannot reschedule {existing.status} appointment",
            )

        # Free the current slot only while we attempt rebook; restore on failure.
        original_status = existing.status
        existing.status = AppointmentStatus.RESCHEDULED.value
        await self._store.update_appointment(existing)

        meta = existing.metadata or {}
        # Default to next day so one-click reschedule does not silently rebook
        # the exact same freed slot (looks like the button did nothing).
        target_start = preferred_start or (existing.start + timedelta(days=1))
        next_service_id = service_id if service_id is not None else existing.service_id
        next_service_name = (
            service_name if service_name is not None else meta.get("service_name")
        )
        next_repair = repair_type if repair_type is not None else existing.repair_type
        next_bay = (
            required_bay
            if required_bay is not None
            else meta.get("required_bay")
        )
        next_duration = (
            estimated_duration_min
            if estimated_duration_min is not None
            else existing.estimated_duration_min
        )
        next_revenue = (
            estimated_revenue
            if estimated_revenue is not None
            else existing.estimated_revenue
        )
        if estimated_revenue is None and service_id is not None and service_id != existing.service_id:
            looked_up = await self._catalog_list_price(shop_id, service_id)
            if looked_up is not None:
                next_revenue = looked_up
        # Drag-drop / explicit assignee wins; otherwise keep the current mechanic.
        next_mechanic = (
            mechanic_id if mechanic_id is not None else existing.mechanic_id
        )
        booking = BookingRequest(
            shop_id=shop_id,
            preferred_start=target_start,
            customer_id=existing.customer_id,
            vehicle_id=existing.vehicle_id,
            service_id=next_service_id,
            service_name=next_service_name,
            repair_type=next_repair,
            required_bay=next_bay,
            vehicle_type=existing.vehicle_type,
            priority=existing.priority,
            estimated_duration_min=next_duration,
            # Never re-enter walk-in start path (forces "now" + in_progress).
            source="dashboard" if existing.source == "walk_in" else existing.source,
            notes=f"Rescheduled from {existing.id}",
            walk_in_id=existing.walk_in_id,
            estimated_revenue=next_revenue,
            mechanic_id=next_mechanic,
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
            if existing.source == "walk_in":
                result.appointment.source = "walk_in"
            await self._store.update_appointment(result.appointment)
        return result

    async def change_service(
        self,
        *,
        shop_id: UUID,
        appointment_id: UUID,
        service_id: UUID,
        service_name: str,
        repair_type: str,
        required_bay: str | None,
        estimated_duration_min: int,
        estimated_revenue: Decimal,
    ) -> BookingResult:
        """Update catalog service on an active appointment (same start time)."""
        existing = await self._store.get_appointment(shop_id, appointment_id)
        if existing is None:
            return BookingResult(success=False, message="Appointment not found")

        if existing.status not in self._ACTIVE_STATUSES:
            return BookingResult(
                success=False,
                message=f"Cannot change service on {existing.status} appointment",
            )

        duration = max(1, int(estimated_duration_min))
        new_end = existing.start + timedelta(minutes=duration)

        hours = await self._store.list_business_hours(shop_id)
        window = self._availability.day_window(
            hours, self._availability.local_date(existing.start)
        )
        if window is None or existing.start < window[0] or new_end > window[1]:
            return BookingResult(
                success=False,
                message="New service duration falls outside business hours. Reschedule instead.",
                conflicts=ConflictReport(
                    has_conflict=True,
                    conflicts=["Outside business hours"],
                    overbooked=False,
                    severity="high",
                ),
            )

        existing_list = await self._store.list_appointments(shop_id)
        report = self._conflict.check_appointment(
            start=existing.start,
            end=new_end,
            mechanic_id=existing.mechanic_id,
            bay_id=existing.bay_id,
            existing=existing_list,
            ignore_id=existing.id,
            priority=existing.priority,
        )
        if report.has_conflict and existing.priority != "emergency":
            return BookingResult(
                success=False,
                message="New service duration conflicts with another appointment. Reschedule instead.",
                conflicts=report,
            )

        meta = dict(existing.metadata or {})
        meta["service_id"] = str(service_id)
        meta["service_name"] = service_name
        meta["required_skill"] = repair_type
        if required_bay:
            meta["required_bay"] = required_bay
        elif "required_bay" in meta:
            del meta["required_bay"]

        existing.service_id = service_id
        existing.repair_type = repair_type
        existing.estimated_duration_min = duration
        existing.end = new_end
        existing.estimated_completion = new_end
        existing.estimated_revenue = estimated_revenue
        existing.metadata = meta

        saved = await self._store.update_appointment(existing)
        logger.info(
            "scheduling.service_changed id=%s service=%s duration=%s",
            saved.id,
            service_name,
            duration,
        )
        return BookingResult(
            success=True,
            appointment=saved,
            message="Service updated",
            ai_decisions={
                "service_id": str(service_id),
                "service_name": service_name,
                "estimated_duration_min": duration,
                "estimated_revenue": str(estimated_revenue),
                "end": new_end.isoformat(),
            },
        )

    async def cancel(
        self, *, shop_id: UUID, appointment_id: UUID, reason: str | None = None
    ) -> Appointment | None:
        appt = await self._store.get_appointment(shop_id, appointment_id)
        if appt is None:
            return None
        if appt.status not in self._ACTIVE_STATUSES:
            raise ValidationError(
                f"Cannot cancel appointment with status '{appt.status}'"
            )
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

    async def complete(
        self, *, shop_id: UUID, appointment_id: UUID, notes: str | None = None
    ) -> Appointment | None:
        """Mark reserved work finished. Idempotent when already completed."""
        appt = await self._store.get_appointment(shop_id, appointment_id)
        if appt is None:
            return None
        if appt.status == AppointmentStatus.COMPLETED.value:
            return appt
        if appt.status in {
            AppointmentStatus.CANCELLED.value,
            AppointmentStatus.RESCHEDULED.value,
            AppointmentStatus.NO_SHOW.value,
        }:
            raise ValidationError(
                f"Cannot complete appointment with status '{appt.status}'"
            )
        appt.status = AppointmentStatus.COMPLETED.value
        if notes:
            appt.notes = f"{appt.notes or ''} | Completed: {notes}".strip(" |")
        updated = await self._store.update_appointment(appt)
        try:
            from app.workflows.emitter import emit_domain_event
            from app.workflows.enums import DomainEventType

            await emit_domain_event(
                shop_id=shop_id,
                event_type=DomainEventType.APPOINTMENT_COMPLETED,
                payload={
                    "appointment_id": str(appt.id),
                    "customer_id": str(appt.customer_id) if appt.customer_id else None,
                    "vehicle_id": str(appt.vehicle_id) if appt.vehicle_id else None,
                    "walk_in_id": str(appt.walk_in_id) if appt.walk_in_id else None,
                    "estimated_revenue": str(appt.estimated_revenue),
                },
                source="scheduling",
                correlation_id=str(appt.id),
            )
        except Exception:  # noqa: BLE001
            logger.exception("workflow.emit appointment.completed failed")
        return updated

    _ACTIVE_STATUSES = frozenset(
        {
            AppointmentStatus.BOOKED.value,
            AppointmentStatus.CONFIRMED.value,
            AppointmentStatus.IN_PROGRESS.value,
        }
    )

    async def complete_elapsed(
        self,
        *,
        shop_id: UUID,
        now: datetime | None = None,
    ) -> list[Appointment]:
        """Auto-complete active appointments whose scheduled end time has passed."""
        cursor = now or datetime.now(timezone.utc)
        if cursor.tzinfo is None:
            cursor = cursor.replace(tzinfo=timezone.utc)
        else:
            cursor = cursor.astimezone(timezone.utc)

        appts = await self._store.list_appointments(shop_id)
        done: list[Appointment] = []
        for appt in appts:
            if appt.status not in self._ACTIVE_STATUSES:
                continue
            end = appt.end
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            else:
                end = end.astimezone(timezone.utc)
            if end > cursor:
                continue
            updated = await self.complete(
                shop_id=shop_id,
                appointment_id=appt.id,
                notes="Auto-completed after scheduled end",
            )
            if updated is not None:
                done.append(updated)
        return done

    async def walk_in_has_active_work(
        self, *, shop_id: UUID, walk_in_id: UUID
    ) -> bool:
        """True when the walk-in still has booked/confirmed/in-progress appointments."""
        appts = await self._store.list_appointments(shop_id)
        return any(
            a.walk_in_id == walk_in_id and a.status in self._ACTIVE_STATUSES for a in appts
        )

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
        *,
        ignore_appointment_id: UUID | None = None,
    ) -> tuple[SlotCandidate | None, str | None]:
        """Assign the best free mechanic/bay at an exact start time."""
        hours = await self._store.list_business_hours(request.shop_id)
        mechanics = await self._store.list_mechanics(request.shop_id)
        bays = await self._store.list_bays(request.shop_id)
        existing = await self._store.list_appointments(request.shop_id)
        if ignore_appointment_id is not None:
            existing = [a for a in existing if a.id != ignore_appointment_id]
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
            ignore_id=ignore_appointment_id,
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
