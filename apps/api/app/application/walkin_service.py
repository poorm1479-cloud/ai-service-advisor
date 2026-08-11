from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.application.crm_service import (
    _normalize_plate,
    _normalize_vin,
    _validate_cost,
    _validate_mileage,
    _validate_phone,
    _validate_year,
)
from app.domain.entities import Customer, RepairHistory, Vehicle, WalkInVisit
from app.domain.enums import WalkInStatus
from app.domain.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.repositories import UnitOfWork


@dataclass(slots=True)
class WalkInDetail:
    visit: WalkInVisit
    vehicle: Vehicle
    customer: Customer | None
    repair_history: list[RepairHistory]


class WalkInService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def create(
        self,
        *,
        shop_id: UUID,
        vin: str,
        year: int,
        make: str,
        model: str,
        mileage: int,
        complaint: str,
        license_plate: str | None = None,
        arrived_at: datetime | None = None,
    ) -> WalkInDetail:
        await self._uow.bind_shop(shop_id)
        if not complaint.strip():
            raise ValidationError("Complaint is required")

        normalized_vin = _normalize_vin(vin)
        normalized_plate = _normalize_plate(license_plate)
        vehicle = await self._uow.vehicles.get_by_vin(shop_id, normalized_vin)
        # No-VIN intake uses a temporary VIN — fall back to plate match for returning cars
        if vehicle is None and normalized_plate:
            vehicle = await self._uow.vehicles.get_by_license_plate(
                shop_id, normalized_plate
            )
        if vehicle is None:
            vehicle = await self._uow.vehicles.add(
                Vehicle(
                    id=uuid4(),
                    shop_id=shop_id,
                    customer_id=None,
                    vin=normalized_vin,
                    license_plate=normalized_plate,
                    year=_validate_year(year),
                    make=make.strip(),
                    model=model.strip(),
                    mileage=_validate_mileage(mileage),
                )
            )
        else:
            # Refresh mileage / plate for returning cars without forcing customer
            vehicle = await self._uow.vehicles.update(
                Vehicle(
                    id=vehicle.id,
                    shop_id=vehicle.shop_id,
                    customer_id=vehicle.customer_id,
                    vin=vehicle.vin,
                    license_plate=normalized_plate or vehicle.license_plate,
                    year=_validate_year(year),
                    make=make.strip() or vehicle.make,
                    model=model.strip() or vehicle.model,
                    mileage=_validate_mileage(mileage),
                    created_at=vehicle.created_at,
                )
            )

        arrival = arrived_at or datetime.now(timezone.utc)
        if arrival.tzinfo is None:
            arrival = arrival.replace(tzinfo=timezone.utc)

        visit = await self._uow.walk_ins.add(
            WalkInVisit(
                id=uuid4(),
                shop_id=shop_id,
                vehicle_id=vehicle.id,
                customer_id=vehicle.customer_id,
                complaint=complaint.strip(),
                status=WalkInStatus.OPEN,
                arrived_at=arrival,
            )
        )
        await self._uow.commit()
        return await self._detail(shop_id, visit.id)

    async def list(
        self,
        *,
        shop_id: UUID,
        status: WalkInStatus | None = None,
        arrived_after: datetime | None = None,
    ) -> list[WalkInVisit]:
        await self._uow.bind_shop(shop_id)
        return await self._uow.walk_ins.list_by_shop(
            shop_id,
            status=status.value if status else None,
            arrived_after=arrived_after,
        )

    async def get(self, *, shop_id: UUID, visit_id: UUID) -> WalkInDetail:
        await self._uow.bind_shop(shop_id)
        return await self._detail(shop_id, visit_id)

    async def convert_to_customer(
        self,
        *,
        shop_id: UUID,
        visit_id: UUID,
        name: str,
        phone: str | None = None,
        email: str | None = None,
        address: str | None = None,
    ) -> WalkInDetail:
        await self._uow.bind_shop(shop_id)
        visit = await self._require_open_visit(shop_id, visit_id)
        if visit.customer_id is not None:
            raise ConflictError("Walk-in already has a customer")
        if not name.strip():
            raise ValidationError("Name is required to convert walk-in into a customer")

        customer = await self._uow.customers.add(
            Customer(
                id=uuid4(),
                shop_id=shop_id,
                name=name.strip(),
                phone=_validate_phone(phone),
                email=email.lower() if email else None,
                address=address.strip() if address else None,
            )
        )

        vehicle = await self._uow.vehicles.get_by_id(shop_id, visit.vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found")
        vehicle = await self._uow.vehicles.update(
            Vehicle(
                id=vehicle.id,
                shop_id=vehicle.shop_id,
                customer_id=customer.id,
                vin=vehicle.vin,
                license_plate=vehicle.license_plate,
                year=vehicle.year,
                make=vehicle.make,
                model=vehicle.model,
                mileage=vehicle.mileage,
                created_at=vehicle.created_at,
            )
        )

        visit = await self._uow.walk_ins.update(
            WalkInVisit(
                id=visit.id,
                shop_id=visit.shop_id,
                vehicle_id=visit.vehicle_id,
                customer_id=customer.id,
                complaint=visit.complaint,
                status=WalkInStatus.CONVERTED,
                arrived_at=visit.arrived_at,
                created_at=visit.created_at,
            )
        )
        await self._uow.commit()
        return await self._detail(shop_id, visit.id)

    async def attach_vehicle(
        self,
        *,
        shop_id: UUID,
        visit_id: UUID,
        vehicle_id: UUID | None = None,
        vin: str | None = None,
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        mileage: int | None = None,
        license_plate: str | None = None,
    ) -> WalkInDetail:
        await self._uow.bind_shop(shop_id)
        visit = await self._require_open_visit(shop_id, visit_id)

        if vehicle_id is not None:
            vehicle = await self._uow.vehicles.get_by_id(shop_id, vehicle_id)
            if vehicle is None:
                raise NotFoundError("Vehicle not found")
        else:
            if not vin or year is None or not make or not model or mileage is None:
                raise ValidationError(
                    "Provide vehicle_id or full vehicle details (vin, year, make, model, mileage)"
                )
            normalized_vin = _normalize_vin(vin)
            existing = await self._uow.vehicles.get_by_vin(shop_id, normalized_vin)
            if existing:
                vehicle = await self._uow.vehicles.update(
                    Vehicle(
                        id=existing.id,
                        shop_id=existing.shop_id,
                        customer_id=visit.customer_id or existing.customer_id,
                        vin=existing.vin,
                        license_plate=(
                            license_plate.strip().upper()
                            if license_plate
                            else existing.license_plate
                        ),
                        year=_validate_year(year),
                        make=make.strip(),
                        model=model.strip(),
                        mileage=_validate_mileage(mileage),
                        created_at=existing.created_at,
                    )
                )
            else:
                vehicle = await self._uow.vehicles.add(
                    Vehicle(
                        id=uuid4(),
                        shop_id=shop_id,
                        customer_id=visit.customer_id,
                        vin=normalized_vin,
                        license_plate=license_plate.strip().upper() if license_plate else None,
                        year=_validate_year(year),
                        make=make.strip(),
                        model=model.strip(),
                        mileage=_validate_mileage(mileage),
                    )
                )

        if visit.customer_id and vehicle.customer_id is None:
            vehicle = await self._uow.vehicles.update(
                Vehicle(
                    id=vehicle.id,
                    shop_id=vehicle.shop_id,
                    customer_id=visit.customer_id,
                    vin=vehicle.vin,
                    license_plate=vehicle.license_plate,
                    year=vehicle.year,
                    make=vehicle.make,
                    model=vehicle.model,
                    mileage=vehicle.mileage,
                    created_at=vehicle.created_at,
                )
            )

        visit = await self._uow.walk_ins.update(
            WalkInVisit(
                id=visit.id,
                shop_id=visit.shop_id,
                vehicle_id=vehicle.id,
                customer_id=visit.customer_id or vehicle.customer_id,
                complaint=visit.complaint,
                status=visit.status,
                arrived_at=visit.arrived_at,
                created_at=visit.created_at,
            )
        )
        await self._uow.commit()
        return await self._detail(shop_id, visit.id)

    async def close(self, *, shop_id: UUID, visit_id: UUID) -> WalkInDetail:
        """Close a walk-in after reserved work is finished (idempotent)."""
        await self._uow.bind_shop(shop_id)
        visit = await self._uow.walk_ins.get_by_id(shop_id, visit_id)
        if visit is None:
            raise NotFoundError("Walk-in visit not found")
        if visit.status == WalkInStatus.CLOSED:
            return await self._detail(shop_id, visit.id)
        if visit.status == WalkInStatus.CANCELLED:
            raise ConflictError("Cannot close a cancelled walk-in")

        visit = await self._uow.walk_ins.update(
            WalkInVisit(
                id=visit.id,
                shop_id=visit.shop_id,
                vehicle_id=visit.vehicle_id,
                customer_id=visit.customer_id,
                complaint=visit.complaint,
                status=WalkInStatus.CLOSED,
                arrived_at=visit.arrived_at,
                created_at=visit.created_at,
            )
        )
        await self._uow.commit()
        return await self._detail(shop_id, visit.id)

    async def cancel(self, *, shop_id: UUID, visit_id: UUID) -> WalkInDetail:
        """Cancel a walk-in before/during service (idempotent)."""
        await self._uow.bind_shop(shop_id)
        visit = await self._uow.walk_ins.get_by_id(shop_id, visit_id)
        if visit is None:
            raise NotFoundError("Walk-in visit not found")
        if visit.status == WalkInStatus.CANCELLED:
            return await self._detail(shop_id, visit.id)
        if visit.status == WalkInStatus.CLOSED:
            raise ConflictError("Cannot cancel a closed walk-in")

        visit = await self._uow.walk_ins.update(
            WalkInVisit(
                id=visit.id,
                shop_id=visit.shop_id,
                vehicle_id=visit.vehicle_id,
                customer_id=visit.customer_id,
                complaint=visit.complaint,
                status=WalkInStatus.CANCELLED,
                arrived_at=visit.arrived_at,
                created_at=visit.created_at,
            )
        )
        await self._uow.commit()
        return await self._detail(shop_id, visit.id)

    async def attach_repair_history(
        self,
        *,
        shop_id: UUID,
        visit_id: UUID,
        service_type: str,
        description: str,
        cost: Decimal,
        recommendation: str | None = None,
    ) -> WalkInDetail:
        await self._uow.bind_shop(shop_id)
        visit = await self._uow.walk_ins.get_by_id(shop_id, visit_id)
        if visit is None:
            raise NotFoundError("Walk-in visit not found")
        if visit.status in (WalkInStatus.CLOSED, WalkInStatus.CANCELLED):
            raise ConflictError("Cannot attach repair history to a closed or cancelled walk-in")

        vehicle = await self._uow.vehicles.get_by_id(shop_id, visit.vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found")

        await self._uow.repair_histories.add(
            RepairHistory(
                id=uuid4(),
                shop_id=shop_id,
                customer_id=visit.customer_id or vehicle.customer_id,
                vehicle_id=vehicle.id,
                service_type=service_type.strip(),
                description=description.strip(),
                cost=_validate_cost(cost),
                recommendation=recommendation.strip() if recommendation else None,
            )
        )
        await self._uow.commit()
        return await self._detail(shop_id, visit.id)

    async def _require_open_visit(self, shop_id: UUID, visit_id: UUID) -> WalkInVisit:
        visit = await self._uow.walk_ins.get_by_id(shop_id, visit_id)
        if visit is None:
            raise NotFoundError("Walk-in visit not found")
        if visit.status == WalkInStatus.CLOSED:
            raise ConflictError("Walk-in visit is closed")
        if visit.status == WalkInStatus.CANCELLED:
            raise ConflictError("Walk-in visit is cancelled")
        return visit

    async def _detail(self, shop_id: UUID, visit_id: UUID) -> WalkInDetail:
        await self._uow.bind_shop(shop_id)
        visit = await self._uow.walk_ins.get_by_id(shop_id, visit_id)
        if visit is None:
            raise NotFoundError("Walk-in visit not found")
        vehicle = await self._uow.vehicles.get_by_id(shop_id, visit.vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found")
        customer = None
        if visit.customer_id:
            customer = await self._uow.customers.get_by_id(shop_id, visit.customer_id)
        history = await self._uow.repair_histories.list_by_vehicle(shop_id, visit.vehicle_id)
        return WalkInDetail(
            visit=visit,
            vehicle=vehicle,
            customer=customer,
            repair_history=history,
        )
