from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, get_current_user, get_uow
from app.api.schemas import (
    RepairHistoryCreate,
    RepairHistoryOut,
    VehicleDetailOut,
    VehicleMatchAssistOut,
    VehicleOut,
    VinAssistOut,
    VinDecodedOut,
)
from app.application.crm_service import CrmService, _normalize_plate, _normalize_vin
from app.application.vin_assist import decode_vin_nhtsa
from app.domain.exceptions import ConflictError, NotFoundError, ValidationError
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

router = APIRouter(prefix="/v1/vehicles", tags=["vehicles"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    raise exc


@router.get("/vin-assist/{vin}", response_model=VinAssistOut)
async def vin_assist(
    vin: str,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> VinAssistOut:
    """Auto-fill helper: shop vehicle match + NHTSA year/make/model decode."""
    try:
        normalized = _normalize_vin(vin)
    except ValidationError as exc:
        raise _http_error(exc) from exc

    existing_out: VehicleOut | None = None
    existing = await uow.vehicles.get_by_vin(current.shop_id, normalized)
    if existing is not None:
        existing_out = VehicleOut.model_validate(existing)

    decoded_out: VinDecodedOut | None = None
    if existing_out is None:
        decoded = await decode_vin_nhtsa(normalized)
        if decoded:
            decoded_out = VinDecodedOut.model_validate(decoded)

    message = None
    if existing_out:
        message = "Matched an existing shop vehicle — fields filled from CRM."
    elif decoded_out:
        message = "Vehicle details decoded from VIN — confirm mileage and complaint."
    else:
        message = "VIN accepted. Enter year, make, model manually (decoder unavailable)."

    return VinAssistOut(
        vin=normalized,
        existing=existing_out,
        decoded=decoded_out,
        message=message,
    )


@router.get("/match-assist", response_model=VehicleMatchAssistOut)
async def match_assist(
    license_plate: str | None = Query(default=None),
    year: int | None = Query(default=None, ge=1900, le=2100),
    make: str | None = Query(default=None, min_length=1, max_length=100),
    model: str | None = Query(default=None, min_length=1, max_length=100),
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> VehicleMatchAssistOut:
    """No-VIN helper: match shop vehicle by plate, then unique year/make/model."""
    plate = _normalize_plate(license_plate)
    if plate:
        existing = await uow.vehicles.get_by_license_plate(current.shop_id, plate)
        if existing is not None:
            return VehicleMatchAssistOut(
                existing=VehicleOut.model_validate(existing),
                match_type="license_plate",
                message="Matched an existing shop vehicle by license plate.",
            )

    if year is not None and make and model:
        candidates = await uow.vehicles.find_by_year_make_model(
            current.shop_id, year, make, model
        )
        if len(candidates) == 1:
            return VehicleMatchAssistOut(
                existing=VehicleOut.model_validate(candidates[0]),
                match_type="year_make_model",
                message="Matched a unique shop vehicle by year / make / model.",
            )
        with_customer = [c for c in candidates if c.customer_id is not None]
        if len(with_customer) == 1:
            return VehicleMatchAssistOut(
                existing=VehicleOut.model_validate(with_customer[0]),
                match_type="year_make_model",
                message="Matched a shop vehicle by year / make / model.",
            )
        if len(candidates) > 1:
            return VehicleMatchAssistOut(
                existing=None,
                match_type=None,
                message="Multiple vehicles match year / make / model — enter plate to narrow.",
            )

    if plate:
        return VehicleMatchAssistOut(
            existing=None,
            match_type=None,
            message="No shop vehicle matches this plate yet.",
        )
    return VehicleMatchAssistOut(
        existing=None,
        match_type=None,
        message=None,
    )


@router.get("/{vehicle_id}", response_model=VehicleDetailOut)
async def get_vehicle_detail(
    vehicle_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> VehicleDetailOut:
    service = CrmService(uow)
    try:
        vehicle = await service.get_vehicle(shop_id=current.shop_id, vehicle_id=vehicle_id)
        history = await service.vehicle_history(shop_id=current.shop_id, vehicle_id=vehicle_id)
    except NotFoundError as exc:
        raise _http_error(exc) from exc
    return VehicleDetailOut(
        vehicle=VehicleOut.model_validate(vehicle),
        repair_history=[RepairHistoryOut.model_validate(h) for h in history],
    )


@router.get("/{vehicle_id}/history", response_model=list[RepairHistoryOut])
async def vehicle_history(
    vehicle_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> list[RepairHistoryOut]:
    service = CrmService(uow)
    try:
        history = await service.vehicle_history(shop_id=current.shop_id, vehicle_id=vehicle_id)
    except NotFoundError as exc:
        raise _http_error(exc) from exc
    return [RepairHistoryOut.model_validate(h) for h in history]


@router.post(
    "/{vehicle_id}/history",
    response_model=RepairHistoryOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_repair_history(
    vehicle_id: UUID,
    body: RepairHistoryCreate,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> RepairHistoryOut:
    service = CrmService(uow)
    try:
        entry = await service.add_repair_history(
            shop_id=current.shop_id,
            vehicle_id=vehicle_id,
            service_type=body.service_type,
            description=body.description,
            cost=body.cost,
            recommendation=body.recommendation,
        )
    except (ValidationError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return RepairHistoryOut.model_validate(entry)
