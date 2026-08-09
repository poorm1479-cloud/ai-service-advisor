"""Appointments & schedule intelligence HTTP API."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.domain.exceptions import ValidationError
from app.infrastructure.database import get_session
from app.scheduling.catalog import (
    build_booking_request,
    require_service_for_booking,
    resolve_extra_services_for_booking,
    sync_shop_resources,
)
from app.scheduling.engines.availability import DEFAULT_SHOP_TZ
from app.scheduling.factory import SchedulingRuntime, get_scheduling_runtime

router = APIRouter(prefix="/v1/appointments", tags=["appointments"])


def _runtime() -> SchedulingRuntime:
    return get_scheduling_runtime()


async def _bind_shop(session: AsyncSession, shop_id: UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.shop_id', :sid, true)"),
        {"sid": str(shop_id)},
    )


class BookRequest(BaseModel):
    """Book against Service Catalog. service_id required (AI voice + dashboard)."""

    service_id: UUID
    extra_service_ids: list[UUID] = Field(default_factory=list)
    preferred_start: datetime | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    vehicle_type: str = "sedan"
    priority: str = "normal"
    notes: str | None = None
    walk_in_id: UUID | None = None
    mechanic_id: UUID | None = None
    bay_id: UUID | None = None
    estimated_revenue: Decimal | None = None
    source: str = "dashboard"


class RescheduleRequest(BaseModel):
    preferred_start: datetime | None = None


class ChangeServiceRequest(BaseModel):
    service_id: UUID


class CancelRequest(BaseModel):
    reason: str | None = None


class AppointmentOut(BaseModel):
    id: UUID
    shop_id: UUID
    start: datetime
    end: datetime
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: str
    priority: str
    repair_type: str
    vehicle_type: str
    estimated_duration_min: int
    service_id: UUID | None = None
    customer_id: UUID | None
    vehicle_id: UUID | None
    mechanic_id: UUID | None
    bay_id: UUID | None
    walk_in_id: UUID | None
    source: str
    notes: str | None
    estimated_revenue: str
    estimated_completion: datetime | None
    wait_time_min: int | None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SlotOut(BaseModel):
    start: datetime
    end: datetime
    mechanic_id: UUID | None
    bay_id: UUID | None
    score: float
    reasons: list[str]
    estimated_wait_min: int
    estimated_completion: datetime | None


class MechanicOut(BaseModel):
    id: UUID
    name: str
    skills: list[dict[str, Any]]
    work_start: str
    work_end: str
    workdays: list[int]
    hourly_rate: str
    role: str = "staff"


class BayOut(BaseModel):
    id: UUID
    name: str
    bay_type: str
    supports_vehicle_types: list[str]


def _shop_wall(when: datetime | None) -> datetime | None:
    """Serialize starts/ends in shop wall-clock so the calendar grid aligns.

    Dashboard wallClockParts reads ISO hour/minute digits — UTC offsets would
    place voice/SMS bookings on the wrong hour (e.g. 3 PM LA → 10 PM).
    """
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(DEFAULT_SHOP_TZ)


def _appt_out(a) -> AppointmentOut:
    start = _shop_wall(a.start) or a.start
    end = _shop_wall(a.end) or a.end
    return AppointmentOut(
        id=a.id,
        shop_id=a.shop_id,
        start=start,
        end=end,
        start_time=start,
        end_time=end,
        status=a.status,
        priority=a.priority,
        repair_type=a.repair_type,
        vehicle_type=a.vehicle_type,
        estimated_duration_min=a.estimated_duration_min,
        service_id=a.service_id,
        customer_id=a.customer_id,
        vehicle_id=a.vehicle_id,
        mechanic_id=a.mechanic_id,
        bay_id=a.bay_id,
        walk_in_id=a.walk_in_id,
        source=a.source,
        notes=a.notes,
        estimated_revenue=str(a.estimated_revenue),
        estimated_completion=_shop_wall(a.estimated_completion),
        wait_time_min=a.wait_time_min,
        metadata=a.metadata or {},
    )


def _http_validation(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


@router.get("", response_model=list[AppointmentOut])
async def list_appointments(
    start: datetime | None = None,
    end: datetime | None = None,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
) -> list[AppointmentOut]:
    items = await runtime.service.list_appointments(user.shop_id, start=start, end=end)
    return [_appt_out(a) for a in items]


@router.get("/calendar")
async def calendar_view(
    view: str = Query("week", pattern="^(day|week)$"),
    anchor: date | None = None,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _bind_shop(session, user.shop_id)
    await sync_shop_resources(session, shop_id=user.shop_id, store=runtime.store)

    availability = runtime.service._availability
    day = anchor or availability.today()
    if view == "day":
        start, end = availability.day_bounds_utc(day)
    else:
        start_date = day - timedelta(days=day.weekday())
        start, _ = availability.day_bounds_utc(start_date)
        _, end = availability.day_bounds_utc(start_date + timedelta(days=6))

    appts = await runtime.service.list_appointments(user.shop_id, start=start, end=end)
    mechanics = await runtime.service.list_mechanics(user.shop_id)
    bays = await runtime.service.list_bays(user.shop_id)
    hours = await runtime.service.list_business_hours(user.shop_id)

    return {
        "view": view,
        "anchor": day.isoformat(),
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
        "appointments": [_appt_out(a).model_dump(mode="json") for a in appts],
        "mechanics": [
            MechanicOut(
                id=m.id,
                name=m.name,
                skills=[{"repair_type": s.repair_type, "proficiency": s.proficiency} for s in m.skills],
                work_start=m.work_start.isoformat(),
                work_end=m.work_end.isoformat(),
                workdays=m.workdays,
                hourly_rate=str(m.hourly_rate),
                role=getattr(m, "role", None) or "staff",
            ).model_dump(mode="json")
            for m in mechanics
        ],
        "bays": [
            BayOut(
                id=b.id,
                name=b.name,
                bay_type=b.bay_type,
                supports_vehicle_types=b.supports_vehicle_types,
            ).model_dump(mode="json")
            for b in bays
        ],
        "business_hours": [
            {
                "weekday": h.weekday,
                "open_time": h.open_time.isoformat(),
                "close_time": h.close_time.isoformat(),
                "closed": h.closed,
            }
            for h in hours
        ],
    }


@router.get("/mechanics", response_model=list[MechanicOut])
async def list_mechanics(
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
    session: AsyncSession = Depends(get_session),
) -> list[MechanicOut]:
    await _bind_shop(session, user.shop_id)
    await sync_shop_resources(session, shop_id=user.shop_id, store=runtime.store)
    mechanics = await runtime.service.list_mechanics(user.shop_id)
    return [
        MechanicOut(
            id=m.id,
            name=m.name,
            skills=[{"repair_type": s.repair_type, "proficiency": s.proficiency} for s in m.skills],
            work_start=m.work_start.isoformat(),
            work_end=m.work_end.isoformat(),
            workdays=m.workdays,
            hourly_rate=str(m.hourly_rate),
            role=getattr(m, "role", None) or "staff",
        )
        for m in mechanics
    ]


@router.get("/bays", response_model=list[BayOut])
async def list_bays(
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
    session: AsyncSession = Depends(get_session),
) -> list[BayOut]:
    await _bind_shop(session, user.shop_id)
    await sync_shop_resources(session, shop_id=user.shop_id, store=runtime.store)
    bays = await runtime.service.list_bays(user.shop_id)
    return [
        BayOut(
            id=b.id,
            name=b.name,
            bay_type=b.bay_type,
            supports_vehicle_types=b.supports_vehicle_types,
        )
        for b in bays
    ]


@router.post("/recommend", response_model=list[SlotOut])
async def recommend_slots(
    body: BookRequest,
    days_ahead: int = 7,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
    session: AsyncSession = Depends(get_session),
) -> list[SlotOut]:
    await _bind_shop(session, user.shop_id)
    try:
        service = await require_service_for_booking(
            session,
            shop_id=user.shop_id,
            service_id=body.service_id,
            store=runtime.store,
        )
        extras = await resolve_extra_services_for_booking(
            session,
            shop_id=user.shop_id,
            primary_id=service.id,
            extra_service_ids=body.extra_service_ids,
        )
    except ValidationError as exc:
        raise _http_validation(exc) from exc

    request = build_booking_request(
        shop_id=user.shop_id,
        service=service,
        preferred_start=body.preferred_start,
        customer_id=body.customer_id,
        vehicle_id=body.vehicle_id,
        vehicle_type=body.vehicle_type,
        priority=body.priority,
        mechanic_id=body.mechanic_id,
        bay_id=body.bay_id,
        additional_services=extras,
    )
    slots = await runtime.service.recommend_slots(request, days_ahead=days_ahead)
    return [
        SlotOut(
            start=s.start,
            end=s.end,
            mechanic_id=s.mechanic_id,
            bay_id=s.bay_id,
            score=s.score,
            reasons=s.reasons,
            estimated_wait_min=s.estimated_wait_min,
            estimated_completion=s.estimated_completion,
        )
        for s in slots
    ]


@router.post("/book")
async def book_appointment(
    body: BookRequest,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _bind_shop(session, user.shop_id)
    try:
        service = await require_service_for_booking(
            session,
            shop_id=user.shop_id,
            service_id=body.service_id,
            store=runtime.store,
        )
        extras = await resolve_extra_services_for_booking(
            session,
            shop_id=user.shop_id,
            primary_id=service.id,
            extra_service_ids=body.extra_service_ids,
        )
    except ValidationError as exc:
        raise _http_validation(exc) from exc

    result = await runtime.service.book(
        build_booking_request(
            shop_id=user.shop_id,
            service=service,
            preferred_start=body.preferred_start,
            customer_id=body.customer_id,
            vehicle_id=body.vehicle_id,
            vehicle_type=body.vehicle_type,
            priority=body.priority,
            notes=body.notes,
            walk_in_id=body.walk_in_id,
            mechanic_id=body.mechanic_id,
            bay_id=body.bay_id,
            estimated_revenue=body.estimated_revenue,
            source=body.source,
            additional_services=extras,
        )
    )
    if result.success:
        runtime.monitor.record_booking()
    elif result.conflicts and result.conflicts.has_conflict:
        runtime.monitor.record_conflict()
    return {
        "success": result.success,
        "message": result.message,
        "appointment": _appt_out(result.appointment).model_dump(mode="json") if result.appointment else None,
        "ai_decisions": result.ai_decisions,
        "alternatives": [
            SlotOut(
                start=s.start,
                end=s.end,
                mechanic_id=s.mechanic_id,
                bay_id=s.bay_id,
                score=s.score,
                reasons=s.reasons,
                estimated_wait_min=s.estimated_wait_min,
                estimated_completion=s.estimated_completion,
            ).model_dump(mode="json")
            for s in result.alternatives
        ],
        "conflicts": {
            "has_conflict": result.conflicts.has_conflict,
            "conflicts": result.conflicts.conflicts,
            "overbooked": result.conflicts.overbooked,
            "severity": result.conflicts.severity,
        }
        if result.conflicts
        else None,
    }


@router.get("/insights/forecast")
async def capacity_forecast(
    day: date | None = None,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _bind_shop(session, user.shop_id)
    await sync_shop_resources(session, shop_id=user.shop_id, store=runtime.store)
    target = day or runtime.service._availability.today()
    forecast = await runtime.service.capacity_forecast(user.shop_id, target)
    return {
        "day": forecast.day.isoformat(),
        "total_minutes": forecast.total_minutes,
        "booked_minutes": forecast.booked_minutes,
        "utilization": forecast.utilization,
        "remaining_slots": forecast.remaining_slots,
        "overbook_risk": forecast.overbook_risk,
        "expected_wait_min": forecast.expected_wait_min,
        "expected_revenue": str(forecast.expected_revenue),
    }


@router.get("/insights/optimize")
async def optimize_schedule(
    day: date | None = None,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _bind_shop(session, user.shop_id)
    await sync_shop_resources(session, shop_id=user.shop_id, store=runtime.store)
    target = day or runtime.service._availability.today()
    optimized = await runtime.service.optimize_schedule(user.shop_id, target)
    runtime.monitor.record_optimize()
    return {
        "day": optimized.day.isoformat(),
        "appointments": [_appt_out(a).model_dump(mode="json") for a in optimized.appointments],
        "improvements": optimized.improvements,
        "mechanic_utilization": optimized.mechanic_utilization,
        "bay_utilization": optimized.bay_utilization,
        "expected_daily_revenue": str(optimized.expected_daily_revenue),
        "avg_customer_wait_min": optimized.avg_customer_wait_min,
        "conflicts": optimized.conflicts,
    }


@router.get("/insights/conflicts")
async def list_conflicts(
    day: date | None = None,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
) -> dict[str, Any]:
    target = day or runtime.service._availability.today()
    conflicts = await runtime.service.detect_conflicts(user.shop_id, target)
    if conflicts:
        runtime.monitor.record_conflict()
    return {"day": target.isoformat(), "conflicts": conflicts}


@router.get("/insights/metrics")
async def scheduling_metrics(
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
) -> dict[str, Any]:
    _ = user
    return {"metrics": runtime.monitor.snapshot()}


@router.get("/{appointment_id}", response_model=AppointmentOut)
async def get_appointment(
    appointment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
) -> AppointmentOut:
    appt = await runtime.service.get_appointment(user.shop_id, appointment_id)
    if appt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return _appt_out(appt)


@router.post("/{appointment_id}/reschedule")
async def reschedule_appointment(
    appointment_id: UUID,
    body: RescheduleRequest,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _bind_shop(session, user.shop_id)
    await sync_shop_resources(session, shop_id=user.shop_id, store=runtime.store)
    result = await runtime.service.reschedule(
        shop_id=user.shop_id,
        appointment_id=appointment_id,
        preferred_start=body.preferred_start,
    )
    if result.success:
        runtime.monitor.record_reschedule()
    if not result.success and result.message == "Appointment not found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=result.message)
    return {
        "success": result.success,
        "message": result.message,
        "appointment": _appt_out(result.appointment).model_dump(mode="json") if result.appointment else None,
        "ai_decisions": result.ai_decisions,
    }


@router.post("/{appointment_id}/change-service")
async def change_appointment_service(
    appointment_id: UUID,
    body: ChangeServiceRequest,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Change the Service Catalog item on an existing appointment."""
    await _bind_shop(session, user.shop_id)
    try:
        service = await require_service_for_booking(
            session,
            shop_id=user.shop_id,
            service_id=body.service_id,
            store=runtime.store,
        )
    except ValidationError as exc:
        raise _http_validation(exc) from exc

    booking = build_booking_request(shop_id=user.shop_id, service=service)
    result = await runtime.service.change_service(
        shop_id=user.shop_id,
        appointment_id=appointment_id,
        service_id=service.id,
        service_name=service.name,
        repair_type=booking.repair_type,
        required_bay=booking.required_bay,
        estimated_duration_min=booking.estimated_duration_min or service.duration_minutes,
        estimated_revenue=booking.estimated_revenue or Decimal(str(service.price)),
    )
    if not result.success and result.message == "Appointment not found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=result.message)
    return {
        "success": result.success,
        "message": result.message,
        "appointment": _appt_out(result.appointment).model_dump(mode="json") if result.appointment else None,
        "ai_decisions": result.ai_decisions,
    }


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
async def cancel_appointment(
    appointment_id: UUID,
    body: CancelRequest,
    user: CurrentUser = Depends(get_current_user),
    runtime: SchedulingRuntime = Depends(_runtime),
) -> AppointmentOut:
    appt = await runtime.service.cancel(
        shop_id=user.shop_id, appointment_id=appointment_id, reason=body.reason
    )
    if appt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    runtime.monitor.record_cancel()
    return _appt_out(appt)
