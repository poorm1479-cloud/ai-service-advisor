"""SQL adapters for agent CustomerDirectoryPort / VehicleDirectoryPort.

Bridges Phase 5 agents to the same CRM tables that /v1/customers reads,
so import apply and agent create decisions land in the dashboard CRM.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete

from app.agents.customer.models import CustomerProfile
from app.agents.vehicle.models import RepairRecord, VehicleRecord
from app.domain.entities import Customer, RepairHistory, Vehicle
from app.infrastructure.database import SessionLocal
from app.infrastructure.models import CustomerModel
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

_PHONE_DIGITS = re.compile(r"\D+")


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = _PHONE_DIGITS.sub("", phone)
    return digits or None


def _phone_match_key(phone: str | None) -> str | None:
    """US-tolerant key: +1XXXXXXXXXX and XXXXXXXXXX compare equal."""
    digits = _normalize_phone(phone)
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    if len(digits) > 10:
        return digits[-10:]
    return digits


def _to_profile(c: Customer) -> CustomerProfile:
    return CustomerProfile(
        id=c.id,
        shop_id=c.shop_id,
        name=c.name,
        phone=c.phone,
        email=c.email,
        address=c.address,
    )


def _to_vehicle_record(v: Vehicle) -> VehicleRecord:
    return VehicleRecord(
        id=v.id,
        shop_id=v.shop_id,
        vin=v.vin,
        year=v.year,
        make=v.make,
        model=v.model,
        mileage=v.mileage,
        customer_id=v.customer_id,
        license_plate=v.license_plate,
    )


class SqlCustomerDirectory:
    """CustomerDirectoryPort backed by SQL CRM tables."""

    async def find_by_id(self, shop_id: UUID, customer_id: UUID) -> CustomerProfile | None:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(shop_id)
            row = await uow.customers.get_by_id(shop_id, customer_id)
            return _to_profile(row) if row else None

    async def find_by_phone(self, shop_id: UUID, phone: str) -> list[CustomerProfile]:
        target = _phone_match_key(phone)
        if not target:
            return []
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(shop_id)
            rows = await uow.customers.list_by_shop(shop_id)
            return [
                _to_profile(r)
                for r in rows
                if _phone_match_key(r.phone) == target
            ]

    async def find_by_email(self, shop_id: UUID, email: str) -> list[CustomerProfile]:
        target = email.lower().strip()
        if not target:
            return []
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(shop_id)
            rows = await uow.customers.list_by_shop(shop_id)
            return [
                _to_profile(r)
                for r in rows
                if (r.email or "").lower() == target
            ]

    async def search(self, shop_id: UUID, query: str) -> list[CustomerProfile]:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(shop_id)
            rows = await uow.customers.search(shop_id, query)
            return [_to_profile(r) for r in rows]

    async def create(self, profile: CustomerProfile) -> CustomerProfile:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(profile.shop_id)
            created = await uow.customers.add(
                Customer(
                    id=profile.id or uuid4(),
                    shop_id=profile.shop_id,
                    name=profile.name.strip() or "Unknown Customer",
                    phone=profile.phone,
                    email=profile.email.lower().strip() if profile.email else None,
                    address=profile.address,
                )
            )
            await uow.commit()
            return _to_profile(created)

    async def update(self, profile: CustomerProfile) -> CustomerProfile:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(profile.shop_id)
            updated = await uow.customers.update(
                Customer(
                    id=profile.id,
                    shop_id=profile.shop_id,
                    name=profile.name,
                    phone=profile.phone,
                    email=profile.email,
                    address=profile.address,
                )
            )
            await uow.commit()
            return _to_profile(updated)

    async def merge(
        self, shop_id: UUID, primary_id: UUID, duplicate_ids: list[UUID]
    ) -> CustomerProfile:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(shop_id)
            primary = await uow.customers.get_by_id(shop_id, primary_id)
            if primary is None:
                raise ValueError("Primary customer not found")

            for dup_id in duplicate_ids:
                if dup_id == primary_id:
                    continue
                dup = await uow.customers.get_by_id(shop_id, dup_id)
                if dup is None:
                    continue
                if not primary.phone and dup.phone:
                    primary.phone = dup.phone
                if not primary.email and dup.email:
                    primary.email = dup.email
                if not primary.address and dup.address:
                    primary.address = dup.address

                # Reassign vehicles then remove duplicate customer row
                vehicles = await uow.vehicles.list_by_customer(shop_id, dup_id)
                for v in vehicles:
                    await uow.vehicles.update(
                        Vehicle(
                            id=v.id,
                            shop_id=v.shop_id,
                            vin=v.vin,
                            year=v.year,
                            make=v.make,
                            model=v.model,
                            mileage=v.mileage,
                            customer_id=primary_id,
                            license_plate=v.license_plate,
                            created_at=v.created_at,
                        )
                    )
                await session.execute(
                    delete(CustomerModel).where(
                        CustomerModel.id == dup_id,
                        CustomerModel.shop_id == shop_id,
                    )
                )

            primary = await uow.customers.update(primary)
            await uow.commit()
            return _to_profile(primary)


class SqlVehicleDirectory:
    """VehicleDirectoryPort backed by SQL CRM tables."""

    async def find_by_id(self, shop_id: UUID, vehicle_id: UUID) -> VehicleRecord | None:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(shop_id)
            row = await uow.vehicles.get_by_id(shop_id, vehicle_id)
            return _to_vehicle_record(row) if row else None

    async def find_by_vin(self, shop_id: UUID, vin: str) -> VehicleRecord | None:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(shop_id)
            row = await uow.vehicles.get_by_vin(shop_id, vin.upper())
            return _to_vehicle_record(row) if row else None

    async def list_by_customer(self, shop_id: UUID, customer_id: UUID) -> list[VehicleRecord]:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(shop_id)
            rows = await uow.vehicles.list_by_customer(shop_id, customer_id)
            return [_to_vehicle_record(r) for r in rows]

    async def create(self, vehicle: VehicleRecord) -> VehicleRecord:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(vehicle.shop_id)
            created = await uow.vehicles.add(
                Vehicle(
                    id=vehicle.id or uuid4(),
                    shop_id=vehicle.shop_id,
                    vin=vehicle.vin.upper(),
                    year=vehicle.year,
                    make=vehicle.make,
                    model=vehicle.model,
                    mileage=vehicle.mileage,
                    customer_id=vehicle.customer_id,
                    license_plate=vehicle.license_plate,
                )
            )
            await uow.commit()
            return _to_vehicle_record(created)

    async def update(self, vehicle: VehicleRecord) -> VehicleRecord:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(vehicle.shop_id)
            updated = await uow.vehicles.update(
                Vehicle(
                    id=vehicle.id,
                    shop_id=vehicle.shop_id,
                    vin=vehicle.vin.upper(),
                    year=vehicle.year,
                    make=vehicle.make,
                    model=vehicle.model,
                    mileage=vehicle.mileage,
                    customer_id=vehicle.customer_id,
                    license_plate=vehicle.license_plate,
                )
            )
            await uow.commit()
            return _to_vehicle_record(updated)

    async def list_repairs(self, shop_id: UUID, vehicle_id: UUID) -> list[RepairRecord]:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(shop_id)
            rows = await uow.repair_histories.list_by_vehicle(shop_id, vehicle_id)
            return [
                RepairRecord(
                    id=r.id,
                    vehicle_id=r.vehicle_id,
                    service_type=r.service_type,
                    description=r.description,
                    cost=float(r.cost),
                    performed_at=r.created_at,
                    recommendation=r.recommendation,
                )
                for r in rows
            ]

    async def add_repair(self, shop_id: UUID, repair: RepairRecord) -> RepairRecord:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            await uow.bind_shop(shop_id)
            vehicle = await uow.vehicles.get_by_id(shop_id, repair.vehicle_id)
            if vehicle is None:
                raise ValueError("Vehicle not found")
            created = await uow.repair_histories.add(
                RepairHistory(
                    id=repair.id or uuid4(),
                    shop_id=shop_id,
                    vehicle_id=repair.vehicle_id,
                    customer_id=vehicle.customer_id,
                    service_type=repair.service_type,
                    description=repair.description,
                    cost=Decimal(str(repair.cost)).quantize(Decimal("0.01")),
                    recommendation=repair.recommendation,
                    # Preserve source/history date on import (not insert-time now()).
                    created_at=_as_utc(repair.performed_at),
                )
            )
            await uow.commit()
            return RepairRecord(
                id=created.id,
                vehicle_id=created.vehicle_id,
                service_type=created.service_type,
                description=created.description,
                cost=float(created.cost),
                performed_at=created.created_at,
                recommendation=created.recommendation,
            )
