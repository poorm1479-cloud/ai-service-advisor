from uuid import UUID

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, get_current_user, get_uow
from app.api.schemas import (
    CustomerOut,
    RepairHistoryCreate,
    RepairHistoryOut,
    VehicleOut,
    WalkInAttachVehicle,
    WalkInConvertCustomer,
    WalkInCreate,
    WalkInDetailOut,
    WalkInVisitOut,
)
from app.application.walkin_service import WalkInService
from app.domain.enums import WalkInStatus
from app.domain.exceptions import ConflictError, NotFoundError, ValidationError
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

router = APIRouter(prefix="/v1/walk-ins", tags=["walk-ins"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    raise exc


def _detail_out(detail) -> WalkInDetailOut:
    return WalkInDetailOut(
        visit=WalkInVisitOut.model_validate(detail.visit),
        vehicle=VehicleOut.model_validate(detail.vehicle),
        customer=CustomerOut.model_validate(detail.customer) if detail.customer else None,
        repair_history=[RepairHistoryOut.model_validate(h) for h in detail.repair_history],
    )


@router.post("", response_model=WalkInDetailOut, status_code=status.HTTP_201_CREATED)
async def create_walk_in(
    body: WalkInCreate,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> WalkInDetailOut:
    service = WalkInService(uow)
    try:
        detail = await service.create(
            shop_id=current.shop_id,
            vin=body.vin,
            license_plate=body.license_plate,
            year=body.year,
            make=body.make,
            model=body.model,
            mileage=body.mileage,
            complaint=body.complaint,
            arrived_at=body.arrived_at,
        )
    except (ValidationError, ConflictError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return _detail_out(detail)


@router.get("", response_model=list[WalkInVisitOut])
async def list_walk_ins(
    status_filter: WalkInStatus | None = Query(default=None, alias="status"),
    arrived_after: datetime | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> list[WalkInVisitOut]:
    service = WalkInService(uow)
    visits = await service.list(
        shop_id=current.shop_id,
        status=status_filter,
        arrived_after=arrived_after,
    )
    return [WalkInVisitOut.model_validate(v) for v in visits]


@router.get("/{visit_id}", response_model=WalkInDetailOut)
async def get_walk_in(
    visit_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> WalkInDetailOut:
    service = WalkInService(uow)
    try:
        detail = await service.get(shop_id=current.shop_id, visit_id=visit_id)
    except NotFoundError as exc:
        raise _http_error(exc) from exc
    return _detail_out(detail)


@router.post("/{visit_id}/convert-customer", response_model=WalkInDetailOut)
async def convert_walk_in_to_customer(
    visit_id: UUID,
    body: WalkInConvertCustomer,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> WalkInDetailOut:
    service = WalkInService(uow)
    try:
        detail = await service.convert_to_customer(
            shop_id=current.shop_id,
            visit_id=visit_id,
            name=body.name,
            phone=body.phone,
            email=str(body.email) if body.email else None,
            address=body.address,
        )
    except (ValidationError, ConflictError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return _detail_out(detail)


@router.post("/{visit_id}/attach-vehicle", response_model=WalkInDetailOut)
async def attach_vehicle_to_walk_in(
    visit_id: UUID,
    body: WalkInAttachVehicle,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> WalkInDetailOut:
    service = WalkInService(uow)
    try:
        detail = await service.attach_vehicle(
            shop_id=current.shop_id,
            visit_id=visit_id,
            vehicle_id=body.vehicle_id,
            vin=body.vin,
            year=body.year,
            make=body.make,
            model=body.model,
            mileage=body.mileage,
            license_plate=body.license_plate,
        )
    except (ValidationError, ConflictError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return _detail_out(detail)


@router.post("/{visit_id}/repair-history", response_model=WalkInDetailOut)
async def attach_repair_history_to_walk_in(
    visit_id: UUID,
    body: RepairHistoryCreate,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> WalkInDetailOut:
    service = WalkInService(uow)
    try:
        detail = await service.attach_repair_history(
            shop_id=current.shop_id,
            visit_id=visit_id,
            service_type=body.service_type,
            description=body.description,
            cost=body.cost,
            recommendation=body.recommendation,
        )
    except (ValidationError, ConflictError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return _detail_out(detail)


@router.post("/{visit_id}/close", response_model=WalkInDetailOut)
async def close_walk_in(
    visit_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> WalkInDetailOut:
    service = WalkInService(uow)
    try:
        detail = await service.close(shop_id=current.shop_id, visit_id=visit_id)
    except (ValidationError, ConflictError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return _detail_out(detail)


@router.post("/{visit_id}/cancel", response_model=WalkInDetailOut)
async def cancel_walk_in(
    visit_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> WalkInDetailOut:
    """Cancel a walk-in visit and any linked active appointments."""
    from app.scheduling.factory import get_scheduling_runtime

    runtime = get_scheduling_runtime()
    try:
        linked = await runtime.service.list_appointments(shop_id=current.shop_id)
        for appt in linked:
            if appt.walk_in_id != visit_id:
                continue
            if appt.status not in ("booked", "confirmed", "in_progress"):
                continue
            await runtime.service.cancel(
                shop_id=current.shop_id,
                appointment_id=appt.id,
                reason="Walk-in visit cancelled",
            )
            runtime.monitor.record_cancel()
    except ValidationError as exc:
        raise _http_error(exc) from exc

    service = WalkInService(uow)
    try:
        detail = await service.cancel(shop_id=current.shop_id, visit_id=visit_id)
    except (ValidationError, ConflictError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return _detail_out(detail)
