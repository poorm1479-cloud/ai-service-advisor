from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.entities import CommunicationHistory, Customer, RepairHistory, Vehicle
from app.domain.enums import CommunicationChannel, CommunicationDirection
from app.domain.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.repositories import UnitOfWork

_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
_PHONE_RE = re.compile(r"^[0-9+\-().\s]{7,32}$")
_PHONE_DIGITS_RE = re.compile(r"\D+")


@dataclass(frozen=True)
class CustomerDirectoryItem:
    customer: Customer
    vehicles: list[Vehicle]
    last_service: RepairHistory | None


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


def _phone_match_key(phone: str | None) -> str | None:
    """Canonical key for duplicate checks (US 10-digit == +1XXXXXXXXXX)."""
    if not phone:
        return None
    digits = _PHONE_DIGITS_RE.sub("", phone)
    if not digits:
        return None
    # Compare by national 10-digit number when present (strips leading country 1).
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def _validate_phone(phone: str | None) -> str | None:
    """Validate phone; normalize US 10/11-digit numbers to +1XXXXXXXXXX."""
    if phone is None or phone.strip() == "":
        return None
    cleaned = phone.strip()
    if not _PHONE_RE.match(cleaned):
        raise ValidationError("Invalid phone number format")
    digits = _PHONE_DIGITS_RE.sub("", cleaned)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
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
        phone_norm = _validate_phone(phone)
        email_norm = email.lower().strip() if email and email.strip() else None
        phone_key = _phone_match_key(phone_norm)

        if phone_key or email_norm:
            existing = await self._uow.customers.list_by_shop(shop_id)
            if phone_key and any(
                _phone_match_key(c.phone) == phone_key for c in existing
            ):
                raise ConflictError("A customer with this phone number already exists")
            if email_norm and any(
                (c.email or "").lower() == email_norm for c in existing
            ):
                raise ConflictError("A customer with this email already exists")

        customer = Customer(
            id=uuid4(),
            shop_id=shop_id,
            name=name.strip(),
            phone=phone_norm,
            email=email_norm,
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

    async def delete_customer(self, *, shop_id: UUID, customer_id: UUID) -> None:
        await self._uow.bind_shop(shop_id)
        existing = await self._uow.customers.get_by_id(shop_id, customer_id)
        if existing is None:
            raise NotFoundError("Customer not found")
        deleted = await self._uow.customers.delete(shop_id, customer_id)
        if not deleted:
            raise NotFoundError("Customer not found")
        await self._uow.commit()

    async def search_customers(self, *, shop_id: UUID, query: str | None) -> list[Customer]:
        await self._uow.bind_shop(shop_id)
        if query and query.strip():
            return await self._uow.customers.search(shop_id, query)
        return await self._uow.customers.list_by_shop(shop_id)

    async def list_customer_directory(
        self, *, shop_id: UUID, query: str | None = None
    ) -> list[CustomerDirectoryItem]:
        """Batch-load customers with vehicles + latest repair (avoids N+1 on list pages)."""
        await self._uow.bind_shop(shop_id)
        if query and query.strip():
            customers = await self._uow.customers.search(shop_id, query)
        else:
            customers = await self._uow.customers.list_by_shop(shop_id)

        vehicles = await self._uow.vehicles.list_by_shop(shop_id)
        latest = await self._uow.repair_histories.latest_by_customer_for_shop(shop_id)

        vehicles_by_customer: dict[UUID, list[Vehicle]] = {}
        for v in vehicles:
            if v.customer_id is None:
                continue
            vehicles_by_customer.setdefault(v.customer_id, []).append(v)

        # When searching by name/phone, also include customers matched via VIN/plate.
        if query and query.strip():
            needle = query.strip().lower()
            matched_ids = {c.id for c in customers}
            for v in vehicles:
                if v.customer_id is None or v.customer_id in matched_ids:
                    continue
                label = f"{v.year} {v.make} {v.model}".lower()
                plate = (v.license_plate or "").lower()
                if needle in v.vin.lower() or needle in label or needle in plate:
                    matched_ids.add(v.customer_id)
            if len(matched_ids) > len(customers):
                all_customers = await self._uow.customers.list_by_shop(shop_id)
                customers = [c for c in all_customers if c.id in matched_ids]

        return [
            CustomerDirectoryItem(
                customer=c,
                vehicles=vehicles_by_customer.get(c.id, []),
                last_service=latest.get(c.id),
            )
            for c in customers
        ]

    async def get_customer(self, *, shop_id: UUID, customer_id: UUID) -> Customer:
        await self._uow.bind_shop(shop_id)
        customer = await self._uow.customers.get_by_id(shop_id, customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    async def get_customer_detail(
        self, *, shop_id: UUID, customer_id: UUID
    ) -> tuple[Customer, list[Vehicle], list[CommunicationHistory], list[RepairHistory]]:
        """Single-pass detail load — avoids repeated customer existence checks."""
        await self._uow.bind_shop(shop_id)
        customer = await self._uow.customers.get_by_id(shop_id, customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        vehicles = await self._uow.vehicles.list_by_customer(shop_id, customer_id)
        communications = await self._uow.communications.list_by_customer(
            shop_id, customer_id
        )
        repairs = await self._uow.repair_histories.list_by_vehicle_ids(
            shop_id, [v.id for v in vehicles]
        )
        return customer, vehicles, communications, repairs

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

    async def update_vehicle(
        self,
        *,
        shop_id: UUID,
        vehicle_id: UUID,
        vin: str | None,
        license_plate: str | None,
        year: int | None,
        make: str | None,
        model: str | None,
        mileage: int | None,
        fields_set: set[str],
    ) -> Vehicle:
        await self._uow.bind_shop(shop_id)
        existing = await self._uow.vehicles.get_by_id(shop_id, vehicle_id)
        if existing is None:
            raise NotFoundError("Vehicle not found")

        next_vin = existing.vin
        if "vin" in fields_set:
            if vin is None:
                raise ValidationError("VIN cannot be empty")
            next_vin = _normalize_vin(vin)
            if next_vin != existing.vin:
                conflict = await self._uow.vehicles.get_by_vin(shop_id, next_vin)
                if conflict is not None and conflict.id != existing.id:
                    raise ConflictError("VIN already exists for this shop")

        next_plate = existing.license_plate
        if "license_plate" in fields_set:
            next_plate = license_plate.strip().upper() if license_plate else None

        next_year = existing.year
        if "year" in fields_set:
            if year is None:
                raise ValidationError("Year cannot be empty")
            next_year = _validate_year(year)

        next_make = existing.make
        if "make" in fields_set:
            if make is None or not make.strip():
                raise ValidationError("Make cannot be empty")
            next_make = make.strip()

        next_model = existing.model
        if "model" in fields_set:
            if model is None or not model.strip():
                raise ValidationError("Model cannot be empty")
            next_model = model.strip()

        next_mileage = existing.mileage
        if "mileage" in fields_set:
            if mileage is None:
                raise ValidationError("Mileage cannot be empty")
            next_mileage = _validate_mileage(mileage)

        updated = Vehicle(
            id=existing.id,
            shop_id=existing.shop_id,
            customer_id=existing.customer_id,
            vin=next_vin,
            license_plate=next_plate,
            year=next_year,
            make=next_make,
            model=next_model,
            mileage=next_mileage,
            created_at=existing.created_at,
        )
        result = await self._uow.vehicles.update(updated)
        await self._uow.commit()
        return result

    async def delete_vehicle(self, *, shop_id: UUID, vehicle_id: UUID) -> None:
        await self._uow.bind_shop(shop_id)
        existing = await self._uow.vehicles.get_by_id(shop_id, vehicle_id)
        if existing is None:
            raise NotFoundError("Vehicle not found")
        if await self._uow.vehicles.has_walk_in_visits(shop_id, vehicle_id):
            raise ConflictError(
                "Cannot delete vehicle with walk-in visits — close or reassign those visits first"
            )
        deleted = await self._uow.vehicles.delete(shop_id, vehicle_id)
        if not deleted:
            raise NotFoundError("Vehicle not found")
        await self._uow.commit()

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

    async def customer_repair_history(
        self, *, shop_id: UUID, customer_id: UUID, vehicle_ids: list[UUID] | None = None
    ) -> list[RepairHistory]:
        await self._uow.bind_shop(shop_id)
        ids = vehicle_ids
        if ids is None:
            vehicles = await self._uow.vehicles.list_by_customer(shop_id, customer_id)
            ids = [v.id for v in vehicles]
        return await self._uow.repair_histories.list_by_vehicle_ids(shop_id, ids)

    async def add_repair_history(
        self,
        *,
        shop_id: UUID,
        vehicle_id: UUID,
        service_type: str,
        description: str,
        cost: Decimal,
        recommendation: str | None,
        created_at: datetime | None = None,
    ) -> RepairHistory:
        await self._uow.bind_shop(shop_id)
        vehicle = await self._uow.vehicles.get_by_id(shop_id, vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found")

        occurred = created_at
        if occurred is not None and occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)

        entry = RepairHistory(
            id=uuid4(),
            shop_id=shop_id,
            customer_id=vehicle.customer_id,
            vehicle_id=vehicle_id,
            service_type=service_type.strip(),
            description=description.strip(),
            cost=_validate_cost(cost),
            recommendation=recommendation.strip() if recommendation else None,
            created_at=occurred,
        )
        created = await self._uow.repair_histories.add(entry)
        await self._uow.commit()
        return created

    async def delete_repair_history(
        self, *, shop_id: UUID, vehicle_id: UUID, repair_id: UUID
    ) -> None:
        await self._uow.bind_shop(shop_id)
        if await self._uow.vehicles.get_by_id(shop_id, vehicle_id) is None:
            raise NotFoundError("Vehicle not found")
        deleted = await self._uow.repair_histories.delete(shop_id, vehicle_id, repair_id)
        if not deleted:
            raise NotFoundError("Repair history not found")
        await self._uow.commit()

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

    async def delete_communication(
        self, *, shop_id: UUID, customer_id: UUID, communication_id: UUID
    ) -> None:
        await self._uow.bind_shop(shop_id)
        if await self._uow.customers.get_by_id(shop_id, customer_id) is None:
            raise NotFoundError("Customer not found")
        deleted = await self._uow.communications.delete(
            shop_id, customer_id, communication_id
        )
        if not deleted:
            raise NotFoundError("Communication not found")
        await self._uow.commit()
