from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.entities import CommunicationHistory, Customer, RepairHistory, Vehicle
from app.domain.enums import CommunicationChannel, CommunicationDirection
from app.domain.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.repositories import UnitOfWork

_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
_PHONE_RE = re.compile(r"^[0-9+\-().\s]{7,32}$")


def _normalize_vin(vin: str) -> str:
    normalized = vin.strip().upper()
    if not _VIN_RE.match(normalized):
        raise ValidationError(
            "VIN must be 17 characters and exclude I, O, and Q"
        )
    return normalized


def _normalize_plate(plate: str | None) -> str | None:
    if plate is None:
        return None
    cleaned = "".join(ch for ch in plate.strip().upper() if ch.isalnum())
    return cleaned or None


def _validate_phone(phone: str | None) -> str | None:
    if phone is None or phone.strip() == "":
        return None
    cleaned = phone.strip()
    if not _PHONE_RE.match(cleaned):
        raise ValidationError("Invalid phone number format")
    return cleaned


def _validate_year(year: int) -> int:
    current = datetime.now().year + 1
    if year < 1900 or year > current:
        raise ValidationError(f"Year must be between 1900 and {current}")
    return year


def _validate_mileage(mileage: int) -> int:
    if mileage < 0 or mileage > 3_000_000:
        raise ValidationError("Mileage must be between 0 and 3,000,000")
    return mileage


def _validate_cost(cost: Decimal) -> Decimal:
    if cost < 0:
        raise ValidationError("Cost cannot be negative")
    return cost.quantize(Decimal("0.01"))


class CrmService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def create_customer(
        self,
        *,
        shop_id: UUID,
        name: str,
        phone: str | None,
        email: str | None,
        address: str | None,
    ) -> Customer:
        await self._uow.bind_shop(shop_id)
        customer = Customer(
            id=uuid4(),
            shop_id=shop_id,
            name=name.strip(),
            phone=_validate_phone(phone),
            email=email.lower() if email else None,
            address=address.strip() if address else None,
        )
        created = await self._uow.customers.add(customer)
        await self._uow.commit()
        return created

    async def update_customer(
        self,
        *,
        shop_id: UUID,
        customer_id: UUID,
        name: str | None,
        phone: str | None,
        email: str | None,
        address: str | None,
        fields_set: set[str],
    ) -> Customer:
        await self._uow.bind_shop(shop_id)
        existing = await self._uow.customers.get_by_id(shop_id, customer_id)
        if existing is None:
            raise NotFoundError("Customer not found")

        updated = Customer(
            id=existing.id,
            shop_id=existing.shop_id,
            name=name.strip() if "name" in fields_set and name is not None else existing.name,
            phone=_validate_phone(phone) if "phone" in fields_set else existing.phone,
            email=(email.lower() if email else None) if "email" in fields_set else existing.email,
            address=(address.strip() if address else None)
            if "address" in fields_set
            else existing.address,
            created_at=existing.created_at,
        )
        result = await self._uow.customers.update(updated)
        await self._uow.commit()
        return result

    async def search_customers(self, *, shop_id: UUID, query: str | None) -> list[Customer]:
        await self._uow.bind_shop(shop_id)
        if query and query.strip():
            return await self._uow.customers.search(shop_id, query)
        return await self._uow.customers.list_by_shop(shop_id)

    async def get_customer(self, *, shop_id: UUID, customer_id: UUID) -> Customer:
        await self._uow.bind_shop(shop_id)
        customer = await self._uow.customers.get_by_id(shop_id, customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    async def create_vehicle(
        self,
        *,
        shop_id: UUID,
        customer_id: UUID,
        vin: str,
        license_plate: str | None,
        year: int,
        make: str,
        model: str,
        mileage: int,
    ) -> Vehicle:
        await self._uow.bind_shop(shop_id)
        customer = await self._uow.customers.get_by_id(shop_id, customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")

        normalized_vin = _normalize_vin(vin)
        if await self._uow.vehicles.get_by_vin(shop_id, normalized_vin):
            raise ConflictError("VIN already exists for this shop")

        vehicle = Vehicle(
            id=uuid4(),
            shop_id=shop_id,
            customer_id=customer_id,
            vin=normalized_vin,
            license_plate=license_plate.strip().upper() if license_plate else None,
            year=_validate_year(year),
            make=make.strip(),
            model=model.strip(),
            mileage=_validate_mileage(mileage),
        )
        created = await self._uow.vehicles.add(vehicle)
        await self._uow.commit()
        return created

    async def list_customer_vehicles(self, *, shop_id: UUID, customer_id: UUID) -> list[Vehicle]:
        await self._uow.bind_shop(shop_id)
        if await self._uow.customers.get_by_id(shop_id, customer_id) is None:
            raise NotFoundError("Customer not found")
        return await self._uow.vehicles.list_by_customer(shop_id, customer_id)

    async def get_vehicle(self, *, shop_id: UUID, vehicle_id: UUID) -> Vehicle:
        await self._uow.bind_shop(shop_id)
        vehicle = await self._uow.vehicles.get_by_id(shop_id, vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found")
        return vehicle

    async def vehicle_history(self, *, shop_id: UUID, vehicle_id: UUID) -> list[RepairHistory]:
        await self._uow.bind_shop(shop_id)
        if await self._uow.vehicles.get_by_id(shop_id, vehicle_id) is None:
            raise NotFoundError("Vehicle not found")
        return await self._uow.repair_histories.list_by_vehicle(shop_id, vehicle_id)

    async def add_repair_history(
        self,
        *,
        shop_id: UUID,
        vehicle_id: UUID,
        service_type: str,
        description: str,
        cost: Decimal,
        recommendation: str | None,
    ) -> RepairHistory:
        await self._uow.bind_shop(shop_id)
        vehicle = await self._uow.vehicles.get_by_id(shop_id, vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found")

        entry = RepairHistory(
            id=uuid4(),
            shop_id=shop_id,
            customer_id=vehicle.customer_id,
            vehicle_id=vehicle_id,
            service_type=service_type.strip(),
            description=description.strip(),
            cost=_validate_cost(cost),
            recommendation=recommendation.strip() if recommendation else None,
        )
        created = await self._uow.repair_histories.add(entry)
        await self._uow.commit()
        return created

    async def communication_timeline(
        self, *, shop_id: UUID, customer_id: UUID
    ) -> list[CommunicationHistory]:
        await self._uow.bind_shop(shop_id)
        if await self._uow.customers.get_by_id(shop_id, customer_id) is None:
            raise NotFoundError("Customer not found")
        return await self._uow.communications.list_by_customer(shop_id, customer_id)

    async def add_communication(
        self,
        *,
        shop_id: UUID,
        customer_id: UUID,
        channel: CommunicationChannel,
        message: str,
        direction: CommunicationDirection,
        created_at: datetime | None = None,
    ) -> CommunicationHistory:
        await self._uow.bind_shop(shop_id)
        if await self._uow.customers.get_by_id(shop_id, customer_id) is None:
            raise NotFoundError("Customer not found")
        if not message.strip():
            raise ValidationError("Message cannot be empty")

        occurred = created_at
        if occurred is not None and occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)

        entry = CommunicationHistory(
            id=uuid4(),
            shop_id=shop_id,
            customer_id=customer_id,
            channel=channel,
            message=message.strip(),
            direction=direction,
            created_at=occurred,
        )
        created = await self._uow.communications.add(entry)
        await self._uow.commit()
        return created
