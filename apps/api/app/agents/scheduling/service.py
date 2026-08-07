"""Scheduling Agent — pure Decision Layer (recommends slots / booking actions).

Mutations are performed exclusively by Workflow DecisionExecutor.
AI identifies the requested service, matches Service Catalog, reads duration,
and proposes AppointmentDecision — never writes appointments to the database.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from app.agents.base.agent import Agent, AgentContext, AgentResult
from app.agents.counselor.persona import spoken_first_name
from app.agents.decisions.types import AppointmentDecision
from app.agents.intent.models import CustomerIntent
from app.agents.scheduling.catalog_match import CatalogServiceMatch, match_catalog_service
from app.agents.scheduling.catalog_port import InMemoryServiceCatalog, ServiceCatalogPort
from app.agents.scheduling.interfaces import SchedulingStorePort
from app.agents.scheduling.models import (
    AppointmentRecord,
    Reminder,
    SchedulingAction,
    SchedulingRequest,
    SchedulingResult,
    TimeSlot,
)


class InMemorySchedulingStore:
    def __init__(self, *, open_hour: int = 8, close_hour: int = 17, slot_minutes: int = 60) -> None:
        self._appointments: dict[UUID, AppointmentRecord] = {}
        self._open_hour = open_hour
        self._close_hour = close_hour
        self._slot_minutes = slot_minutes

    async def list_available_slots(
        self,
        shop_id: UUID,
        *,
        days_ahead: int = 7,
        duration_minutes: int | None = None,
        repair_type: str | None = None,
    ) -> list[TimeSlot]:
        del repair_type  # in-memory store has no skill matrix
        slot_min = duration_minutes if duration_minutes and duration_minutes > 0 else self._slot_minutes
        # Shop-local calendar day (matches AppointmentIntelligence / counselor TZ).
        from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

        now = datetime.now(DEFAULT_SHOP_TZ)
        booked = [
            a
            for a in self._appointments.values()
            if a.shop_id == shop_id and a.status == "booked"
        ]
        slots: list[TimeSlot] = []
        for day_offset in range(days_ahead):
            day = (now + timedelta(days=day_offset)).date()
            if day.weekday() >= 5:
                continue
            cursor = datetime(
                day.year, day.month, day.day, self._open_hour, 0, tzinfo=DEFAULT_SHOP_TZ
            )
            end_of_day = datetime(
                day.year, day.month, day.day, self._close_hour, 0, tzinfo=DEFAULT_SHOP_TZ
            )
            while cursor + timedelta(minutes=slot_min) <= end_of_day:
                slot_end = cursor + timedelta(minutes=slot_min)
                overlaps = any(a.start < slot_end and cursor < a.end for a in booked)
                available = not overlaps and cursor > now
                slots.append(TimeSlot(start=cursor, end=slot_end, available=available))
                cursor = slot_end
        return [s for s in slots if s.available]

    async def probe_slot_at(
        self,
        shop_id: UUID,
        *,
        preferred_start: datetime,
        duration_minutes: int | None = None,
        repair_type: str | None = None,
        required_bay: str | None = None,
    ) -> TimeSlot | None:
        """Exact-start probe for clock preferences (in-memory grid)."""
        del repair_type, required_bay
        openings = await self.list_available_slots(
            shop_id,
            days_ahead=14,
            duration_minutes=duration_minutes,
        )
        return SchedulingAgent._find_exact_slot(openings, preferred_start)

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
    ) -> AppointmentRecord:
        from uuid import uuid4

        from app.agents.base.errors import AgentValidationError

        del duration_minutes, repair_type, required_bay  # in-memory has no skill matrix

        for a in self._appointments.values():
            if (
                a.shop_id == shop_id
                and a.status == "booked"
                and a.start < end
                and start < a.end
            ):
                raise AgentValidationError("Time slot not available", agent="scheduling")
        record = AppointmentRecord(
            id=uuid4(),
            shop_id=shop_id,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            start=start,
            end=end,
            notes=notes,
            service_id=service_id,
            service_name=service_name,
        )
        self._appointments[record.id] = record
        return record

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
    ) -> AppointmentRecord:
        from app.agents.base.errors import AgentValidationError

        existing = await self.get(shop_id, appointment_id)
        if existing is None:
            raise AgentValidationError("Appointment not found", agent="scheduling")
        existing.status = "rescheduled"
        # Prefer newly requested catalog service on move (voice/SMS change).
        return await self.book(
            shop_id,
            start=start,
            end=end,
            customer_id=existing.customer_id,
            vehicle_id=existing.vehicle_id,
            notes=f"Rescheduled from {existing.id}",
            service_id=service_id if service_id is not None else existing.service_id,
            service_name=service_name if service_name is not None else existing.service_name,
            duration_minutes=duration_minutes,
            repair_type=repair_type,
            required_bay=required_bay,
        )

    async def cancel(
        self, shop_id: UUID, appointment_id: UUID, reason: str | None = None
    ) -> AppointmentRecord:
        from app.agents.base.errors import AgentValidationError

        existing = await self.get(shop_id, appointment_id)
        if existing is None:
            raise AgentValidationError("Appointment not found", agent="scheduling")
        existing.status = "cancelled"
        existing.notes = reason or existing.notes
        return existing

    async def get(self, shop_id: UUID, appointment_id: UUID) -> AppointmentRecord | None:
        a = self._appointments.get(appointment_id)
        return a if a and a.shop_id == shop_id else None

    async def list_by_customer(
        self, shop_id: UUID, customer_id: UUID
    ) -> list[AppointmentRecord]:
        active = {"booked", "confirmed", "in_progress"}
        items = [
            a
            for a in self._appointments.values()
            if a.shop_id == shop_id
            and a.customer_id == customer_id
            and str(a.status).lower() in active
        ]
        return sorted(items, key=lambda a: a.start)


class SchedulingAgent(Agent[SchedulingRequest, SchedulingResult]):
    """Decision-only scheduling AI — matches catalog, proposes AppointmentDecision."""

    name = "scheduling"

    def __init__(
        self,
        store: SchedulingStorePort | None = None,
        *,
        catalog: ServiceCatalogPort | None = None,
    ) -> None:
        super().__init__()
        self._store = store or InMemorySchedulingStore()
        self._catalog = catalog or InMemoryServiceCatalog()

    @property
    def store(self) -> SchedulingStorePort:
        return self._store

    @property
    def catalog(self) -> ServiceCatalogPort:
        return self._catalog

    async def handle(
        self, payload: SchedulingRequest, context: AgentContext
    ) -> AgentResult[SchedulingResult]:
        return await self.process(payload, context)

    async def process(
        self, request: SchedulingRequest, context: AgentContext
    ) -> AgentResult[SchedulingResult]:
        action = request.action
        inferred_from_intent = False
        if action == SchedulingAction.NOOP and request.intent:
            action = self._action_from_intent(request.intent)
            inferred_from_intent = True

        # Mid reschedule-ask, or same-conversation time change after a book:
        # convert BOOK → RESCHEDULE so the previous slot is marked rescheduled.
        # Do NOT use active_appointment_id / upcoming alone — that poisons a
        # fresh book into reschedule whenever the customer already has a visit.
        meta = context.metadata or {}
        mem_appt = meta.get("appointment_id")
        pending_action = str(meta.get("pending_action") or "")
        if (
            action == SchedulingAction.BOOK
            and request.appointment_id is not None
            and (
                pending_action == "reschedule"
                or (
                    mem_appt
                    and str(request.appointment_id) == str(mem_appt)
                    and pending_action != "book"
                )
            )
        ):
            action = SchedulingAction.RESCHEDULE

        # Chat path: never mutate until the customer confirms (YES / summary OK).
        # Preferred time alone selects a candidate slot; confirmation still required.
        if (
            action == SchedulingAction.BOOK
            and inferred_from_intent
            and not request.confirm_booking
        ):
            action = SchedulingAction.LIST_SLOTS
        # Reschedule needs a target visit up front — never demote to ask-time
        # (which would loop forever with no appointment_id).
        if action == SchedulingAction.RESCHEDULE and not request.appointment_id:
            return AgentResult.ok(
                SchedulingResult(
                    action=SchedulingAction.RESCHEDULE.value,
                    success=False,
                    available_slots=[],
                    message="no_appointment_to_reschedule",
                    metadata={"action": "reschedule", "no_appointment": True},
                    decision=AppointmentDecision(
                        action="noop",
                        rationale="No appointment found to reschedule",
                        confidence=0.0,
                    ),
                )
            )
        if (
            action == SchedulingAction.RESCHEDULE
            and inferred_from_intent
            and not request.confirm_booking
            and request.preferred_start is None
        ):
            action = SchedulingAction.LIST_SLOTS

        match = await self._resolve_catalog_match(request, context.shop_id)
        duration = match.duration_minutes if match else None
        repair_type = match.skill if match else None

        if action == SchedulingAction.LIST_SLOTS:
            asking_availability = (
                request.intent == CustomerIntent.CHECK_AVAILABILITY.value
                or request.action == SchedulingAction.LIST_SLOTS
            )
            # Booking path (not an availability ask): ask when they want to come —
            # do not volunteer openings. Soft day/part-of-day still needs a clock
            # unless they asked for the first/last available opening.
            # Closed / fully booked day → reject immediately (no time question).
            # time_only = clock already known — only need an explicit day.
            if (
                not asking_availability
                and request.time_precision != "clock"
                and not request.prefer_earliest
                and not request.prefer_latest
            ):
                pending_action = self._pending_action_label(request)
                if (
                    request.preferred_start is not None
                    and request.time_precision in {"day", "part_of_day"}
                ):
                    openings = await self._store.list_available_slots(
                        context.shop_id,
                        days_ahead=request.days_ahead,
                        duration_minutes=duration,
                        repair_type=repair_type,
                    )
                    closed = self._closed_day_result(
                        preferred_start=request.preferred_start,
                        slots=openings,
                        action=pending_action,
                        request=request,
                        context=context,
                        match=match,
                        duration=duration,
                    )
                    if closed is not None:
                        return closed
                clock_known = (
                    request.time_precision == "time_only"
                    and request.preferred_start is not None
                )
                decision = AppointmentDecision(
                    action="list_slots",
                    days_ahead=request.days_ahead,
                    customer_id=request.customer_id or context.customer_id,
                    vehicle_id=request.vehicle_id or context.vehicle_id,
                    appointment_id=request.appointment_id,
                    preferred_start=request.preferred_start,
                    preferred_end=request.preferred_end,
                    requested_service=request.requested_service,
                    service_id=match.service_id if match else None,
                    service_name=match.name if match else None,
                    duration_minutes=duration,
                    required_skill=match.skill if match else None,
                    required_bay=match.bay if match else None,
                    rationale=(
                        "Ask preferred day — clock already known"
                        if clock_known
                        else "Ask preferred time — do not volunteer openings"
                    )
                    + (f" for {match.name}" if match else ""),
                    confidence=match.confidence if match else 1.0,
                    offer_policy="ask_time",
                    hold_action=pending_action,  # type: ignore[arg-type]
                )
                return AgentResult.ok(
                    SchedulingResult(
                        action=action.value,
                        success=True,
                        available_slots=[],
                        message="ask_preferred_time",
                        metadata={
                            "ask_preferred_time": True,
                            "action": pending_action,
                            # Preserve spoken clock; reply asks day only.
                            **(
                                {
                                    "needs_date": True,
                                    "time_precision": "time_only",
                                    "preferred_start": request.preferred_start.isoformat(),
                                }
                                if clock_known
                                else {}
                            ),
                        },
                        decision=decision,
                    )
                )

            slots = await self._store.list_available_slots(
                context.shop_id,
                days_ahead=request.days_ahead,
                duration_minutes=duration,
                repair_type=repair_type,
            )
            # Day / part-of-day: narrow openings; do not invent a clock time.
            soft_pref = request.time_precision in {"day", "part_of_day"}
            slots = self._filter_slots_for_preference(
                slots,
                preferred_start=request.preferred_start,
                preferred_end=request.preferred_end,
                time_precision=request.time_precision,
            )
            pending_start = None
            pending_end = None
            meta: dict = {}
            # Only a concrete clock time, earliest/latest preference, or prior YES bind
            # may become the confirm candidate.
            if (request.prefer_earliest or request.prefer_latest) and slots:
                chosen = slots[-1] if request.prefer_latest else slots[0]
                pending_start = chosen.start
                pending_end = (
                    chosen.start + timedelta(minutes=duration)
                    if duration
                    else chosen.end
                )
                meta = {
                    "awaiting_confirmation": True,
                    "action": "book",
                    "pending_slot_start": pending_start.isoformat(),
                    "pending_slot_end": pending_end.isoformat(),
                    "prefer_earliest": bool(request.prefer_earliest),
                    "prefer_latest": bool(request.prefer_latest),
                }
                snap = (context.metadata or {}).get("customer_snapshot") or {}
                if snap and not spoken_first_name(snap.get("name")):
                    meta["awaiting_customer_name"] = True
            elif (
                request.preferred_start is not None
                and request.time_precision == "clock"
            ):
                chosen = await self._resolve_clock_slot(
                    slots,
                    preferred_start=request.preferred_start,
                    context=context,
                    duration=duration,
                    repair_type=repair_type,
                    required_bay=match.bay if match else None,
                    days_ahead=request.days_ahead,
                    exclude_appointment_id=request.appointment_id,
                )
                if chosen is None:
                    decision = AppointmentDecision(
                        action="list_slots",
                        days_ahead=request.days_ahead,
                        customer_id=request.customer_id or context.customer_id,
                        vehicle_id=request.vehicle_id or context.vehicle_id,
                        preferred_start=request.preferred_start,
                        preferred_end=request.preferred_end,
                        requested_service=request.requested_service,
                        service_id=match.service_id if match else None,
                        service_name=match.name if match else None,
                        duration_minutes=duration,
                        required_skill=match.skill if match else None,
                        required_bay=match.bay if match else None,
                        rationale="Preferred clock time unavailable"
                        + (f" for {match.name}" if match else ""),
                        confidence=match.confidence if match else 1.0,
                        offer_policy="unavailable",
                    )
                    return AgentResult.ok(
                        SchedulingResult(
                            action=action.value,
                            success=False,
                            available_slots=[],
                            message="preferred_time_unavailable",
                            metadata=self._unavailable_meta(
                                preferred_start=request.preferred_start,
                                slots=slots,
                                action="book",
                            ),
                            decision=decision,
                        )
                    )
                pending_start = chosen.start
                pending_end = (
                    chosen.start + timedelta(minutes=duration)
                    if duration
                    else chosen.end
                )
                meta = {
                    "awaiting_confirmation": True,
                    "action": "book",
                    "pending_slot_start": pending_start.isoformat(),
                    "pending_slot_end": pending_end.isoformat(),
                }
                snap = (context.metadata or {}).get("customer_snapshot") or {}
                if snap and not spoken_first_name(snap.get("name")):
                    meta["awaiting_customer_name"] = True
            decision = AppointmentDecision(
                action="list_slots",
                days_ahead=request.days_ahead,
                customer_id=request.customer_id or context.customer_id,
                vehicle_id=request.vehicle_id or context.vehicle_id,
                preferred_start=request.preferred_start,
                preferred_end=request.preferred_end,
                requested_service=request.requested_service,
                service_id=match.service_id if match else None,
                service_name=match.name if match else None,
                duration_minutes=duration,
                required_skill=match.skill if match else None,
                required_bay=match.bay if match else None,
                recommended_slot_start=pending_start,
                recommended_slot_end=pending_end,
                rationale="List available appointment slots"
                + (f" for {match.name}" if match else "")
                + ("; soft preference — offer times" if soft_pref else "")
                + (
                    "; prefer earliest opening"
                    if request.prefer_earliest and pending_start
                    else (
                        "; prefer latest opening"
                        if request.prefer_latest and pending_start
                        else ""
                    )
                )
                + (
                    "; awaiting customer name"
                    if meta.get("awaiting_customer_name")
                    else ("; awaiting booking confirmation" if pending_start else "")
                ),
                confidence=match.confidence if match else 1.0,
                hold_action="book",
            )
            return AgentResult.ok(
                SchedulingResult(
                    action=action.value,
                    success=True,
                    available_slots=slots,
                    message=(
                        "awaiting_customer_name"
                        if meta.get("awaiting_customer_name")
                        else (
                            "awaiting_booking_confirmation"
                            if pending_start
                            else f"{len(slots)} slots available"
                        )
                    ),
                    metadata=meta,
                    decision=decision,
                )
            )

        if action == SchedulingAction.BOOK:
            slots = await self._store.list_available_slots(
                context.shop_id,
                days_ahead=request.days_ahead,
                duration_minutes=duration,
                repair_type=repair_type,
            )
            if not slots:
                return AgentResult.ok(
                    SchedulingResult(
                        action=action.value,
                        success=False,
                        message="No available slots",
                        decision=self._catalog_decision(
                            action="book",
                            request=request,
                            context=context,
                            match=match,
                            rationale="No slots available to recommend",
                            confidence=0.0,
                        ),
                    )
                )
            # Never invent a clock time — require a concrete preferred start
            # (or an explicit earliest/latest available request).
            if (
                request.preferred_start is None
                and not request.prefer_earliest
                and not request.prefer_latest
            ):
                pending_action = self._pending_action_label(request)
                return AgentResult.ok(
                    SchedulingResult(
                        action=SchedulingAction.LIST_SLOTS.value,
                        success=True,
                        available_slots=[],
                        message="ask_preferred_time",
                        metadata={
                            "ask_preferred_time": True,
                            "action": pending_action,
                        },
                        decision=AppointmentDecision(
                            action="list_slots",
                            days_ahead=request.days_ahead,
                            customer_id=request.customer_id or context.customer_id,
                            vehicle_id=request.vehicle_id or context.vehicle_id,
                            appointment_id=request.appointment_id,
                            preferred_start=request.preferred_start,
                            preferred_end=request.preferred_end,
                            requested_service=request.requested_service,
                            service_id=match.service_id if match else None,
                            service_name=match.name if match else None,
                            duration_minutes=duration,
                            required_skill=match.skill if match else None,
                            required_bay=match.bay if match else None,
                            rationale="No preferred time — ask instead of volunteering openings",
                            confidence=match.confidence if match else 1.0,
                            offer_policy="ask_time",
                            hold_action=pending_action,  # type: ignore[arg-type]
                        ),
                    )
                )
            if request.time_precision in {"day", "part_of_day"} and not (
                request.prefer_earliest or request.prefer_latest
            ):
                pending_action = self._pending_action_label(request)
                closed = self._closed_day_result(
                    preferred_start=request.preferred_start,
                    slots=slots,
                    action=pending_action,
                    request=request,
                    context=context,
                    match=match,
                    duration=duration,
                )
                if closed is not None:
                    return closed
                return AgentResult.ok(
                    SchedulingResult(
                        action=SchedulingAction.LIST_SLOTS.value,
                        success=True,
                        available_slots=[],
                        message="ask_preferred_time",
                        metadata={
                            "ask_preferred_time": True,
                            "action": pending_action,
                        },
                        decision=AppointmentDecision(
                            action="list_slots",
                            days_ahead=request.days_ahead,
                            customer_id=request.customer_id or context.customer_id,
                            vehicle_id=request.vehicle_id or context.vehicle_id,
                            appointment_id=request.appointment_id,
                            preferred_start=request.preferred_start,
                            preferred_end=request.preferred_end,
                            requested_service=request.requested_service,
                            service_id=match.service_id if match else None,
                            service_name=match.name if match else None,
                            duration_minutes=duration,
                            required_skill=match.skill if match else None,
                            required_bay=match.bay if match else None,
                            rationale="Soft time preference — ask for a clock time",
                            confidence=match.confidence if match else 0.7,
                            offer_policy="ask_time",
                            hold_action=pending_action,  # type: ignore[arg-type]
                        ),
                    )
                )
            if request.prefer_earliest or request.prefer_latest:
                filtered = self._filter_slots_for_preference(
                    slots,
                    preferred_start=request.preferred_start,
                    preferred_end=request.preferred_end,
                    time_precision=request.time_precision or "day",
                )
                if filtered:
                    slot = filtered[-1] if request.prefer_latest else filtered[0]
                elif slots:
                    slot = slots[-1] if request.prefer_latest else slots[0]
                else:
                    slot = None
            else:
                slot = await self._resolve_clock_slot(
                    slots,
                    preferred_start=request.preferred_start,
                    context=context,
                    duration=duration,
                    repair_type=repair_type,
                    required_bay=match.bay if match else None,
                    days_ahead=request.days_ahead,
                    exclude_appointment_id=request.appointment_id,
                )
            if slot is None:
                return AgentResult.ok(
                    SchedulingResult(
                        action=SchedulingAction.LIST_SLOTS.value,
                        success=False,
                        available_slots=[],
                        message="preferred_time_unavailable",
                        metadata=self._unavailable_meta(
                            preferred_start=request.preferred_start,
                            slots=slots,
                            action="book",
                        ),
                        decision=AppointmentDecision(
                            action="list_slots",
                            days_ahead=request.days_ahead,
                            customer_id=request.customer_id or context.customer_id,
                            vehicle_id=request.vehicle_id or context.vehicle_id,
                            preferred_start=request.preferred_start,
                            preferred_end=request.preferred_end,
                            requested_service=request.requested_service,
                            service_id=match.service_id if match else None,
                            service_name=match.name if match else None,
                            duration_minutes=duration,
                            required_skill=match.skill if match else None,
                            required_bay=match.bay if match else None,
                            rationale="Preferred clock time unavailable",
                            confidence=match.confidence if match else 0.7,
                            offer_policy="unavailable",
                        ),
                    )
                )
            end = slot.end
            if duration:
                end = slot.start + timedelta(minutes=duration)
            snap = (context.metadata or {}).get("customer_snapshot") or {}
            if snap and not spoken_first_name(snap.get("name")):
                return AgentResult.ok(
                    SchedulingResult(
                        action=SchedulingAction.LIST_SLOTS.value,
                        success=True,
                        available_slots=slots,
                        message="awaiting_customer_name",
                        metadata={
                            "awaiting_customer_name": True,
                            "awaiting_confirmation": True,
                            "action": "book",
                            "pending_slot_start": slot.start.isoformat(),
                            "pending_slot_end": end.isoformat(),
                        },
                        decision=AppointmentDecision(
                            action="list_slots",
                            days_ahead=request.days_ahead,
                            customer_id=request.customer_id or context.customer_id,
                            vehicle_id=request.vehicle_id or context.vehicle_id,
                            preferred_start=request.preferred_start,
                            preferred_end=request.preferred_end,
                            requested_service=request.requested_service,
                            service_id=match.service_id if match else None,
                            service_name=match.name if match else None,
                            duration_minutes=duration,
                            required_skill=match.skill if match else None,
                            required_bay=match.bay if match else None,
                            recommended_slot_start=slot.start,
                            recommended_slot_end=end,
                            rationale="Need customer name before booking",
                            confidence=match.confidence if match else 0.7,
                            hold_action="book",
                        ),
                    )
                )
            rationale = "Recommend slot matching customer preferred time"
            if match:
                rationale = (
                    f"Matched catalog service '{match.name}' "
                    f"({match.duration_minutes} min); recommend slot"
                )
            decision = self._catalog_decision(
                action="book",
                request=request,
                context=context,
                match=match,
                recommended_slot_start=slot.start,
                recommended_slot_end=end,
                rationale=rationale,
                confidence=match.confidence if match else 0.7,
            )
            return AgentResult.ok(
                SchedulingResult(
                    action=action.value,
                    success=True,
                    available_slots=slots,
                    message="Appointment booking recommended",
                    decision=decision,
                    metadata={
                        "service_id": str(match.service_id) if match else None,
                        "service_name": match.name if match else None,
                        "duration_minutes": duration,
                    },
                )
            )

        if action == SchedulingAction.RESCHEDULE:
            slots = await self._store.list_available_slots(
                context.shop_id,
                duration_minutes=duration,
                repair_type=repair_type,
            )
            if not request.appointment_id:
                # Soft fail — do not emit a mutative decision without a visit.
                return AgentResult.ok(
                    SchedulingResult(
                        action=action.value,
                        success=False,
                        available_slots=[],
                        message="no_appointment_to_reschedule",
                        metadata={"action": "reschedule", "no_appointment": True},
                        decision=AppointmentDecision(
                            action="noop",
                            rationale="No appointment found to reschedule",
                            confidence=0.0,
                            service_id=match.service_id if match else None,
                            service_name=match.name if match else None,
                            duration_minutes=duration,
                        ),
                    )
                )
            if not slots:
                return AgentResult.fail("No slots available to reschedule")
            # Chat path with a preferred time but no YES → hold for confirmation.
            # Day / part-of-day: offer openings instead of inventing a clock time.
            if inferred_from_intent and not request.confirm_booking:
                if request.time_precision in {"day", "part_of_day"}:
                    same_day = self._same_day_openings(
                        slots, request.preferred_start
                    )
                    if request.preferred_start is not None and not same_day:
                        pending_action = self._pending_action_label(request)
                        closed = self._closed_day_result(
                            preferred_start=request.preferred_start,
                            slots=slots,
                            action=pending_action
                            if pending_action == "reschedule"
                            else "reschedule",
                            request=request,
                            context=context,
                            match=match,
                            duration=duration,
                        )
                        if closed is not None:
                            return closed
                    soft_slots = self._filter_slots_for_preference(
                        slots,
                        preferred_start=request.preferred_start,
                        preferred_end=request.preferred_end,
                        time_precision=request.time_precision,
                    )
                    return AgentResult.ok(
                        SchedulingResult(
                            action=SchedulingAction.LIST_SLOTS.value,
                            success=True,
                            available_slots=soft_slots or slots,
                            message=f"{len(soft_slots or slots)} slots available",
                            decision=AppointmentDecision(
                                action="list_slots",
                                appointment_id=request.appointment_id,
                                service_id=match.service_id if match else None,
                                service_name=match.name if match else None,
                                duration_minutes=duration,
                                rationale="Soft preference — offer reschedule times",
                                confidence=match.confidence if match else 0.7,
                            ),
                        )
                    )
                # Clock preference must match an opening exactly — never snap to
                # the next available (that is not the time the customer said).
                if request.preferred_start is not None:
                    slot = await self._resolve_clock_slot(
                        slots,
                        preferred_start=request.preferred_start,
                        context=context,
                        duration=duration,
                        repair_type=repair_type,
                        required_bay=match.bay if match else None,
                        days_ahead=request.days_ahead,
                        exclude_appointment_id=request.appointment_id,
                    )
                    if slot is None:
                        return AgentResult.ok(
                            SchedulingResult(
                                action=SchedulingAction.LIST_SLOTS.value,
                                success=False,
                                available_slots=[],
                                message="preferred_time_unavailable",
                                metadata=self._unavailable_meta(
                                    preferred_start=request.preferred_start,
                                    slots=slots,
                                    action="reschedule",
                                ),
                                decision=AppointmentDecision(
                                    action="list_slots",
                                    appointment_id=request.appointment_id,
                                    preferred_start=request.preferred_start,
                                    service_id=match.service_id if match else None,
                                    service_name=match.name if match else None,
                                    duration_minutes=duration,
                                    rationale="Preferred clock time unavailable to reschedule",
                                    confidence=match.confidence if match else 0.7,
                                    offer_policy="unavailable",
                                    hold_action="reschedule",
                                ),
                            )
                        )
                elif not inferred_from_intent:
                    # Explicit RESCHEDULE API/action with no preferred time —
                    # use next free opening (conversation path never reaches here
                    # without a time preference).
                    slot = slots[0]
                else:
                    # No preferred time yet — ask, do not invent slots[0].
                    return AgentResult.ok(
                        SchedulingResult(
                            action=SchedulingAction.LIST_SLOTS.value,
                            success=True,
                            available_slots=[],
                            message="ask_preferred_time",
                            metadata={
                                "ask_preferred_time": True,
                                "action": "reschedule",
                            },
                            decision=AppointmentDecision(
                                action="list_slots",
                                appointment_id=request.appointment_id,
                                service_id=match.service_id if match else None,
                                service_name=match.name if match else None,
                                duration_minutes=duration,
                                rationale="No preferred time for reschedule",
                                confidence=match.confidence if match else 0.7,
                                offer_policy="ask_time",
                                hold_action="reschedule",
                            ),
                        )
                    )
                end = slot.end
                if duration:
                    end = slot.start + timedelta(minutes=duration)
                return AgentResult.ok(
                    SchedulingResult(
                        action=SchedulingAction.LIST_SLOTS.value,
                        success=True,
                        available_slots=slots,
                        message="awaiting_reschedule_confirmation",
                        metadata={
                            "awaiting_confirmation": True,
                            "action": "reschedule",
                            "pending_slot_start": slot.start.isoformat(),
                            "pending_slot_end": end.isoformat(),
                        },
                        decision=AppointmentDecision(
                            action="list_slots",
                            appointment_id=request.appointment_id,
                            recommended_slot_start=slot.start,
                            recommended_slot_end=end,
                            service_id=match.service_id if match else None,
                            service_name=match.name if match else None,
                            duration_minutes=duration,
                            rationale="Awaiting confirmation before reschedule",
                            confidence=match.confidence if match else 0.7,
                            hold_action="reschedule",
                        ),
                    )
                )
            # Confirmed execute path — exact preferred only (never nearest opening).
            if request.prefer_earliest or request.prefer_latest:
                filtered = self._filter_slots_for_preference(
                    slots,
                    preferred_start=request.preferred_start,
                    preferred_end=request.preferred_end,
                    time_precision=request.time_precision or "day",
                )
                pool = filtered or slots
                slot = pool[-1] if request.prefer_latest else pool[0]
            elif request.preferred_start is not None:
                slot = await self._resolve_clock_slot(
                    slots,
                    preferred_start=request.preferred_start,
                    context=context,
                    duration=duration,
                    repair_type=repair_type,
                    required_bay=match.bay if match else None,
                    days_ahead=request.days_ahead,
                    exclude_appointment_id=request.appointment_id,
                )
                if slot is None:
                    return AgentResult.ok(
                        SchedulingResult(
                            action=SchedulingAction.LIST_SLOTS.value,
                            success=False,
                            available_slots=[],
                            message="preferred_time_unavailable",
                            metadata=self._unavailable_meta(
                                preferred_start=request.preferred_start,
                                slots=slots,
                                action="reschedule",
                            ),
                            decision=AppointmentDecision(
                                action="list_slots",
                                appointment_id=request.appointment_id,
                                preferred_start=request.preferred_start,
                                service_id=match.service_id if match else None,
                                service_name=match.name if match else None,
                                duration_minutes=duration,
                                rationale="Preferred clock time unavailable to reschedule",
                                confidence=match.confidence if match else 0.7,
                                offer_policy="unavailable",
                                hold_action="reschedule",
                            ),
                        )
                    )
            elif not inferred_from_intent:
                # Dashboard-style RESCHEDULE without a preferred clock.
                slot = slots[0]
            else:
                return AgentResult.ok(
                    SchedulingResult(
                        action=SchedulingAction.LIST_SLOTS.value,
                        success=True,
                        available_slots=[],
                        message="ask_preferred_time",
                        metadata={
                            "ask_preferred_time": True,
                            "action": "reschedule",
                        },
                        decision=AppointmentDecision(
                            action="list_slots",
                            appointment_id=request.appointment_id,
                            service_id=match.service_id if match else None,
                            service_name=match.name if match else None,
                            duration_minutes=duration,
                            rationale="Confirmed reschedule without preferred time",
                            confidence=match.confidence if match else 0.7,
                            offer_policy="ask_time",
                            hold_action="reschedule",
                        ),
                    )
                )
            end = slot.end
            if duration:
                end = slot.start + timedelta(minutes=duration)
            decision = AppointmentDecision(
                action="reschedule",
                appointment_id=request.appointment_id,
                recommended_slot_start=slot.start,
                recommended_slot_end=end,
                preferred_start=request.preferred_start,
                service_id=match.service_id if match else None,
                service_name=match.name if match else None,
                duration_minutes=duration,
                required_skill=match.skill if match else None,
                required_bay=match.bay if match else None,
                rationale="Recommend reschedule to exact preferred slot",
            )
            return AgentResult.ok(
                SchedulingResult(
                    action=action.value,
                    success=True,
                    available_slots=slots,
                    message="Appointment reschedule recommended",
                    decision=decision,
                )
            )

        if action == SchedulingAction.CANCEL:
            if not request.appointment_id:
                # Soft fail — never escalate the whole call for a missing visit.
                return AgentResult.ok(
                    SchedulingResult(
                        action=action.value,
                        success=False,
                        message="no_appointment_to_cancel",
                        metadata={"action": "cancel", "no_appointment": True},
                        decision=AppointmentDecision(
                            action="noop",
                            rationale="No appointment found to cancel",
                            confidence=0.0,
                        ),
                    )
                )
            # Chat path: ask for explicit cancel confirmation before mutating.
            if inferred_from_intent and not request.confirm_booking:
                return AgentResult.ok(
                    SchedulingResult(
                        action=action.value,
                        success=False,
                        message="awaiting_cancel_confirmation",
                        metadata={"awaiting_confirmation": True, "action": "cancel"},
                        decision=AppointmentDecision(
                            action="noop",
                            appointment_id=request.appointment_id,
                            rationale="Awaiting customer confirmation before cancel",
                            confidence=0.0,
                        ),
                    )
                )
            decision = AppointmentDecision(
                action="cancel",
                appointment_id=request.appointment_id,
                reason=request.reason,
                rationale="Recommend cancellation",
            )
            return AgentResult.ok(
                SchedulingResult(
                    action=action.value,
                    success=True,
                    message="Appointment cancellation recommended",
                    decision=decision,
                )
            )

        if action == SchedulingAction.REMINDERS:
            return AgentResult.ok(
                SchedulingResult(
                    action=action.value,
                    success=True,
                    message="No pending reminders",
                    decision=AppointmentDecision(action="noop", rationale="Reminders query"),
                )
            )

        return AgentResult.ok(
            SchedulingResult(
                action=SchedulingAction.NOOP.value,
                success=True,
                message="No scheduling action required",
                decision=AppointmentDecision(action="noop"),
            )
        )

    async def _resolve_catalog_match(
        self, request: SchedulingRequest, shop_id: UUID
    ) -> CatalogServiceMatch | None:
        services = await self._catalog.list_bookable_services(shop_id)
        return match_catalog_service(
            request.requested_service,
            services,
            service_id=request.service_id,
        )

    @staticmethod
    def _catalog_decision(
        *,
        action: str,
        request: SchedulingRequest,
        context: AgentContext,
        match: CatalogServiceMatch | None,
        rationale: str,
        confidence: float = 1.0,
        recommended_slot_start: datetime | None = None,
        recommended_slot_end: datetime | None = None,
    ) -> AppointmentDecision:
        return AppointmentDecision(
            action=action,  # type: ignore[arg-type]
            customer_id=request.customer_id or context.customer_id,
            vehicle_id=request.vehicle_id or context.vehicle_id,
            preferred_start=request.preferred_start,
            preferred_end=request.preferred_end,
            recommended_slot_start=recommended_slot_start,
            recommended_slot_end=recommended_slot_end,
            requested_service=request.requested_service,
            service_id=match.service_id if match else request.service_id,
            service_name=match.name if match else None,
            duration_minutes=match.duration_minutes if match else None,
            required_skill=match.skill if match else None,
            required_bay=match.bay if match else None,
            days_ahead=request.days_ahead,
            confidence=confidence,
            rationale=rationale,
        )

    def generate_reminders(self, appointment: AppointmentRecord) -> list[Reminder]:
        """Pure helper for reminder planning (used by DecisionExecutor / tests)."""
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

    @staticmethod
    def _shop_local_date(when: datetime) -> date:
        from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

        if when.tzinfo is None:
            return when.replace(tzinfo=DEFAULT_SHOP_TZ).date()
        return when.astimezone(DEFAULT_SHOP_TZ).date()

    @staticmethod
    def _same_day_openings(
        slots: list[TimeSlot],
        preferred_start: datetime | None,
    ) -> list[TimeSlot]:
        """Openings on the preferred calendar day only (no multi-day fallback)."""
        if preferred_start is None:
            return []
        day = SchedulingAgent._shop_local_date(preferred_start)
        return [
            s for s in slots if SchedulingAgent._shop_local_date(s.start) == day
        ]

    def _closed_day_result(
        self,
        *,
        preferred_start: datetime | None,
        slots: list[TimeSlot],
        action: str,
        request: SchedulingRequest,
        context: AgentContext,
        match: CatalogServiceMatch | None,
        duration: int | None,
    ) -> AgentResult | None:
        """If preferred day has zero openings, reject immediately (do not ask time)."""
        if preferred_start is None:
            return None
        if self._same_day_openings(slots, preferred_start):
            return None
        hold = action if action in {"book", "reschedule"} else "book"
        meta = self._unavailable_meta(
            preferred_start=preferred_start,
            slots=slots,
            action=hold,
        )
        # Soft day preference on a closed day — re-ask date only (no clock).
        meta["unavailable_aspect"] = "date"
        meta["closed_day"] = True
        return AgentResult.ok(
            SchedulingResult(
                action=SchedulingAction.LIST_SLOTS.value,
                success=False,
                available_slots=[],
                message="preferred_time_unavailable",
                metadata=meta,
                decision=AppointmentDecision(
                    action="list_slots",
                    days_ahead=request.days_ahead,
                    customer_id=request.customer_id or context.customer_id,
                    vehicle_id=request.vehicle_id or context.vehicle_id,
                    appointment_id=request.appointment_id,
                    preferred_start=preferred_start,
                    preferred_end=request.preferred_end,
                    requested_service=request.requested_service,
                    service_id=match.service_id if match else None,
                    service_name=match.name if match else None,
                    duration_minutes=duration,
                    required_skill=match.skill if match else None,
                    required_bay=match.bay if match else None,
                    rationale="Preferred day has no openings (closed or full)",
                    confidence=match.confidence if match else 0.7,
                    offer_policy="unavailable",
                    hold_action=hold,  # type: ignore[arg-type]
                ),
            )
        )

    @staticmethod
    def classify_unavailable_aspect(
        slots: list[TimeSlot],
        preferred_start: datetime | None,
    ) -> str:
        """Which half of preferred date/time failed: ``date``, ``time``, or ``both``.

        - Same-day openings exist → only the clock is wrong → re-ask time.
        - No openings that day (but slots elsewhere) → day is wrong → re-ask date.
        - No openings at all, or unknown preferred start → re-ask either.
        """
        if preferred_start is None or not slots:
            return "both"
        day = SchedulingAgent._shop_local_date(preferred_start)
        same_day = any(
            SchedulingAgent._shop_local_date(s.start) == day for s in slots
        )
        if same_day:
            return "time"
        return "date"

    @staticmethod
    def _unavailable_meta(
        *,
        preferred_start: datetime | None,
        slots: list[TimeSlot],
        action: str = "book",
    ) -> dict:
        meta: dict = {
            "preferred_time_unavailable": True,
            "unavailable_aspect": SchedulingAgent.classify_unavailable_aspect(
                slots, preferred_start
            ),
            "action": action,
        }
        if preferred_start is not None:
            meta["preferred_start"] = preferred_start.isoformat()
        return meta

    @staticmethod
    def _filter_slots_for_preference(
        slots: list[TimeSlot],
        *,
        preferred_start: datetime | None,
        preferred_end: datetime | None,
        time_precision: str | None,
    ) -> list[TimeSlot]:
        """Narrow openings for soft preferences without choosing a clock time."""
        if preferred_start is None or time_precision not in {"day", "part_of_day"}:
            return slots
        day = SchedulingAgent._shop_local_date(preferred_start)
        same_day = [
            s for s in slots if SchedulingAgent._shop_local_date(s.start) == day
        ]
        if time_precision == "day":
            return same_day or slots
        # part_of_day — keep openings inside the preferred window (shop-local hours).
        window_end = preferred_end or (preferred_start + timedelta(hours=3))
        # Allow a little slack so "morning" (9) still surfaces 8–11 openings.
        window_start = preferred_start - timedelta(hours=1)
        in_window = [
            s
            for s in same_day
            if window_start <= s.start < window_end + timedelta(hours=1)
        ]
        return in_window or same_day or slots

    @staticmethod
    def _find_exact_slot(
        slots: list[TimeSlot], preferred: datetime | None
    ) -> TimeSlot | None:
        """Return the opening that starts exactly at preferred (shop-local), else None."""
        if preferred is None:
            return None
        from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

        def _local(when: datetime) -> datetime:
            if when.tzinfo is None:
                when = when.replace(tzinfo=DEFAULT_SHOP_TZ)
            return when.astimezone(DEFAULT_SHOP_TZ).replace(second=0, microsecond=0)

        pref = _local(preferred)
        return next((s for s in slots if _local(s.start) == pref), None)

    async def _resolve_clock_slot(
        self,
        slots: list[TimeSlot],
        *,
        preferred_start: datetime | None,
        context: AgentContext,
        duration: int | None,
        repair_type: str | None,
        required_bay: str | None = None,
        days_ahead: int = 14,
        exclude_appointment_id: UUID | None = None,
    ) -> TimeSlot | None:
        """Match preferred clock in ranked openings, else capacity-probe exact start.

        Rank lists are a short subset of free windows; free staff at the requested
        minute must still win via store.probe_slot_at when available.
        When moving an existing visit, exclude it so same-time reschedule works.
        """
        del days_ahead  # reserved for store implementations that scan a day range
        exact = self._find_exact_slot(slots, preferred_start)
        if exact is not None:
            return exact
        if preferred_start is None:
            return None
        probe = getattr(self._store, "probe_slot_at", None)
        if not callable(probe):
            return None
        try:
            return await probe(
                context.shop_id,
                preferred_start=preferred_start,
                duration_minutes=duration,
                repair_type=repair_type,
                required_bay=required_bay,
                exclude_appointment_id=exclude_appointment_id,
            )
        except TypeError:
            # Older / partial doubles: omit exclude, then omit optional kwargs.
            try:
                return await probe(
                    context.shop_id,
                    preferred_start=preferred_start,
                    duration_minutes=duration,
                    repair_type=repair_type,
                    required_bay=required_bay,
                )
            except TypeError:
                try:
                    return await probe(
                        context.shop_id, preferred_start=preferred_start
                    )
                except Exception:  # noqa: BLE001
                    return None
        except Exception:  # noqa: BLE001 — treat probe failure as unavailable
            return None

    @staticmethod
    def _select_slot(slots: list[TimeSlot], preferred: datetime | None) -> TimeSlot:
        """Pick exact preferred start, else next on/after, else nearest same day."""
        if not preferred:
            return slots[0]
        exact = SchedulingAgent._find_exact_slot(slots, preferred)
        if exact is not None:
            return exact
        on_or_after = next((s for s in slots if s.start >= preferred), None)
        if on_or_after is not None:
            return on_or_after
        pref_day = SchedulingAgent._shop_local_date(preferred)
        same_day = [
            s for s in slots if SchedulingAgent._shop_local_date(s.start) == pref_day
        ]
        if same_day:
            return min(same_day, key=lambda s: abs((s.start - preferred).total_seconds()))
        return min(slots, key=lambda s: abs((s.start - preferred).total_seconds()))

    @staticmethod
    def _action_from_intent(intent: str) -> SchedulingAction:
        mapping = {
            CustomerIntent.BOOK_APPOINTMENT.value: SchedulingAction.BOOK,
            CustomerIntent.CHECK_AVAILABILITY.value: SchedulingAction.LIST_SLOTS,
            CustomerIntent.RESCHEDULE.value: SchedulingAction.RESCHEDULE,
            CustomerIntent.CANCEL_APPOINTMENT.value: SchedulingAction.CANCEL,
        }
        return mapping.get(intent, SchedulingAction.NOOP)

    @staticmethod
    def _pending_action_label(request: SchedulingRequest) -> str:
        """Memory/SMS pending_action for ask-time holds (book vs reschedule).

        Only explicit reschedule intent marks the hold as reschedule. Having an
        appointment_id (e.g. leftover memory / upcoming enrich) must not turn a
        new book into a reschedule hold.
        """
        if request.intent == CustomerIntent.RESCHEDULE.value:
            return "reschedule"
        return "book"
