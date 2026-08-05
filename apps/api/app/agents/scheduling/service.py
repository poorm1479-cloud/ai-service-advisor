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
        from uuid import uuid4

        from app.agents.base.errors import AgentValidationError

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
        self, shop_id: UUID, appointment_id: UUID, start: datetime, end: datetime
    ) -> AppointmentRecord:
        from app.agents.base.errors import AgentValidationError

        existing = await self.get(shop_id, appointment_id)
        if existing is None:
            raise AgentValidationError("Appointment not found", agent="scheduling")
        existing.status = "rescheduled"
        return await self.book(
            shop_id,
            start=start,
            end=end,
            customer_id=existing.customer_id,
            vehicle_id=existing.vehicle_id,
            notes=f"Rescheduled from {existing.id}",
            service_id=existing.service_id,
            service_name=existing.service_name,
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

        # Chat path: never mutate until the customer confirms (YES / summary OK).
        # Preferred time alone selects a candidate slot; confirmation still required.
        if (
            action == SchedulingAction.BOOK
            and inferred_from_intent
            and not request.confirm_booking
        ):
            action = SchedulingAction.LIST_SLOTS
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
            if (
                not asking_availability
                and request.time_precision != "clock"
                and not request.prefer_earliest
                and not request.prefer_latest
            ):
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
                    rationale="Ask preferred time — do not volunteer openings"
                    + (f" for {match.name}" if match else ""),
                    confidence=match.confidence if match else 1.0,
                    offer_policy="ask_time",
                )
                return AgentResult.ok(
                    SchedulingResult(
                        action=action.value,
                        success=True,
                        available_slots=[],
                        message="ask_preferred_time",
                        metadata={"ask_preferred_time": True, "action": "book"},
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
                chosen = self._find_exact_slot(slots, request.preferred_start)
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
                            metadata={
                                "preferred_time_unavailable": True,
                                "action": "book",
                                "preferred_start": request.preferred_start.isoformat(),
                            },
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
                return AgentResult.ok(
                    SchedulingResult(
                        action=SchedulingAction.LIST_SLOTS.value,
                        success=True,
                        available_slots=[],
                        message="ask_preferred_time",
                        metadata={"ask_preferred_time": True, "action": "book"},
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
                            rationale="No preferred time — ask instead of volunteering openings",
                            confidence=match.confidence if match else 1.0,
                            offer_policy="ask_time",
                        ),
                    )
                )
            if request.time_precision in {"day", "part_of_day"} and not (
                request.prefer_earliest or request.prefer_latest
            ):
                return AgentResult.ok(
                    SchedulingResult(
                        action=SchedulingAction.LIST_SLOTS.value,
                        success=True,
                        available_slots=[],
                        message="ask_preferred_time",
                        metadata={"ask_preferred_time": True, "action": "book"},
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
                            rationale="Soft time preference — ask for a clock time",
                            confidence=match.confidence if match else 0.7,
                            offer_policy="ask_time",
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
                slot = self._find_exact_slot(slots, request.preferred_start)
            if slot is None:
                return AgentResult.ok(
                    SchedulingResult(
                        action=SchedulingAction.LIST_SLOTS.value,
                        success=False,
                        available_slots=[],
                        message="preferred_time_unavailable",
                        metadata={
                            "preferred_time_unavailable": True,
                            "action": "book",
                            "preferred_start": request.preferred_start.isoformat(),
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
                return AgentResult.ok(
                    SchedulingResult(
                        action=action.value,
                        success=False,
                        available_slots=slots,
                        message="appointment_id required to reschedule; slots provided",
                        decision=AppointmentDecision(
                            action="reschedule",
                            rationale="Missing appointment_id",
                            confidence=0.0,
                            service_id=match.service_id if match else None,
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
                slot = self._select_slot(slots, request.preferred_start)
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
                        ),
                    )
                )
            slot = self._select_slot(slots, request.preferred_start)
            end = slot.end
            if duration:
                end = slot.start + timedelta(minutes=duration)
            decision = AppointmentDecision(
                action="reschedule",
                appointment_id=request.appointment_id,
                recommended_slot_start=slot.start,
                recommended_slot_end=end,
                service_id=match.service_id if match else None,
                service_name=match.name if match else None,
                duration_minutes=duration,
                required_skill=match.skill if match else None,
                required_bay=match.bay if match else None,
                rationale="Recommend reschedule to next available slot",
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
                return AgentResult.fail("appointment_id required to cancel")
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
