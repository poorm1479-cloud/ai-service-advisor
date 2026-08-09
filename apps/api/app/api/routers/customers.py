from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, get_current_user, get_uow
from app.api.schemas import (
    CommunicationCreate,
    CommunicationOut,
    CustomerCreate,
    CustomerDetailOut,
    CustomerDirectoryItemOut,
    CustomerOut,
    CustomerUpdate,
    RepairHistoryOut,
    VehicleCreate,
    VehicleOut,
)
from app.application.crm_service import CrmService
from app.domain.exceptions import ConflictError, NotFoundError, ValidationError
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

router = APIRouter(prefix="/v1/customers", tags=["customers"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    raise exc


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CustomerCreate,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> CustomerOut:
    service = CrmService(uow)
    try:
        customer = await service.create_customer(
            shop_id=current.shop_id,
            name=body.name,
            phone=body.phone,
            email=str(body.email) if body.email else None,
            address=body.address,
        )
    except (ValidationError, ConflictError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return CustomerOut.model_validate(customer)


@router.get("", response_model=list[CustomerOut])
async def search_customers(
    q: str | None = Query(default=None, max_length=200),
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> list[CustomerOut]:
    service = CrmService(uow)
    customers = await service.search_customers(shop_id=current.shop_id, query=q)
    return [CustomerOut.model_validate(c) for c in customers]


@router.get("/directory", response_model=list[CustomerDirectoryItemOut])
async def list_customer_directory(
    q: str | None = Query(default=None, max_length=200),
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> list[CustomerDirectoryItemOut]:
    """Customers + vehicles + latest repair in a few queries (list-page friendly)."""
    service = CrmService(uow)
    items = await service.list_customer_directory(shop_id=current.shop_id, query=q)
    return [
        CustomerDirectoryItemOut(
            customer=CustomerOut.model_validate(item.customer),
            vehicles=[VehicleOut.model_validate(v) for v in item.vehicles],
            last_service=(
                RepairHistoryOut.model_validate(item.last_service)
                if item.last_service
                else None
            ),
        )
        for item in items
    ]


@router.get("/{customer_id}", response_model=CustomerDetailOut)
async def get_customer_detail(
    customer_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> CustomerDetailOut:
    service = CrmService(uow)
    try:
        customer = await service.get_customer(shop_id=current.shop_id, customer_id=customer_id)
        vehicles = await service.list_customer_vehicles(
            shop_id=current.shop_id, customer_id=customer_id
        )
        communications = await service.communication_timeline(
            shop_id=current.shop_id, customer_id=customer_id
        )
        repairs = await service.customer_repair_history(
            shop_id=current.shop_id,
            customer_id=customer_id,
            vehicle_ids=[v.id for v in vehicles],
        )
    except NotFoundError as exc:
        raise _http_error(exc) from exc
    return CustomerDetailOut(
        customer=CustomerOut.model_validate(customer),
        vehicles=[VehicleOut.model_validate(v) for v in vehicles],
        communications=[CommunicationOut.model_validate(c) for c in communications],
        repair_history=[RepairHistoryOut.model_validate(r) for r in repairs],
    )


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: UUID,
    body: CustomerUpdate,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> CustomerOut:
    service = CrmService(uow)
    try:
        customer = await service.update_customer(
            shop_id=current.shop_id,
            customer_id=customer_id,
            name=body.name,
            phone=body.phone,
            email=str(body.email) if body.email is not None else None,
            address=body.address,
            fields_set=set(body.model_fields_set),
        )
    except (ValidationError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return CustomerOut.model_validate(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> None:
    service = CrmService(uow)
    try:
        await service.delete_customer(shop_id=current.shop_id, customer_id=customer_id)
    except NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{customer_id}/vehicles",
    response_model=VehicleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_vehicle(
    customer_id: UUID,
    body: VehicleCreate,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> VehicleOut:
    service = CrmService(uow)
    try:
        vehicle = await service.create_vehicle(
            shop_id=current.shop_id,
            customer_id=customer_id,
            vin=body.vin,
            license_plate=body.license_plate,
            year=body.year,
            make=body.make,
            model=body.model,
            mileage=body.mileage,
        )
    except (ValidationError, ConflictError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return VehicleOut.model_validate(vehicle)


@router.get("/{customer_id}/communications", response_model=list[CommunicationOut])
async def communication_timeline(
    customer_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> list[CommunicationOut]:
    service = CrmService(uow)
    try:
        items = await service.communication_timeline(
            shop_id=current.shop_id, customer_id=customer_id
        )
    except NotFoundError as exc:
        raise _http_error(exc) from exc
    return [CommunicationOut.model_validate(i) for i in items]


@router.post(
    "/{customer_id}/communications",
    response_model=CommunicationOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_communication(
    customer_id: UUID,
    body: CommunicationCreate,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> CommunicationOut:
    service = CrmService(uow)
    try:
        item = await service.add_communication(
            shop_id=current.shop_id,
            customer_id=customer_id,
            channel=body.channel,
            message=body.message,
            direction=body.direction,
        )
    except (ValidationError, NotFoundError) as exc:
        raise _http_error(exc) from exc
    return CommunicationOut.model_validate(item)


@router.delete(
    "/{customer_id}/communications/{communication_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_communication(
    customer_id: UUID,
    communication_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> None:
    service = CrmService(uow)
    try:
        await service.delete_communication(
            shop_id=current.shop_id,
            customer_id=customer_id,
            communication_id=communication_id,
        )
    except NotFoundError as exc:
        raise _http_error(exc) from exc
