"""Audience resolution unit tests (no DB)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.domain.entities import Customer, RepairHistory, Vehicle
from app.marketing.audience import (
    _ShopAudienceContext,
    resolve_from_context,
)
from app.marketing.enums import CampaignType
from app.scheduling.enums import AppointmentStatus
from app.scheduling.models import Appointment


def _ctx(**kwargs) -> _ShopAudienceContext:
    shop_id = kwargs.get("shop_id", uuid4())
    now = kwargs.get("now", datetime.now(timezone.utc))
    return _ShopAudienceContext(
        shop_id=shop_id,
        shop_name=kwargs.get("shop_name", "Test Shop"),
        customers=kwargs.get("customers", {}),
        vehicles_by_customer=kwargs.get("vehicles_by_customer", {}),
        vehicles_by_id=kwargs.get("vehicles_by_id", {}),
        repairs=kwargs.get("repairs", []),
        walk_ins=kwargs.get("walk_ins", []),
        appointments=kwargs.get("appointments", []),
        declined_memory_customer_ids=kwargs.get("declined_memory_customer_ids", set()),
        now=now,
    )


def test_resolve_inactive_customers():
    shop_id = uuid4()
    now = datetime.now(timezone.utc)
    old = Customer(
        id=uuid4(),
        shop_id=shop_id,
        name="Old Patron",
        phone="+15550001",
        created_at=now - timedelta(days=200),
    )
    recent = Customer(
        id=uuid4(),
        shop_id=shop_id,
        name="Recent Patron",
        phone="+15550002",
        created_at=now - timedelta(days=10),
    )
    ctx = _ctx(
        shop_id=shop_id,
        now=now,
        customers={old.id: old, recent.id: recent},
    )
    members = resolve_from_context(ctx, CampaignType.INACTIVE_CUSTOMER)
    assert [m.customer_id for m in members] == [old.id]
    assert members[0].metadata["shop"] == "Test Shop"


def test_resolve_declined_from_repair_recommendation():
    shop_id = uuid4()
    customer = Customer(id=uuid4(), shop_id=shop_id, name="Alex", phone="+15550003")
    vehicle = Vehicle(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vin="1HGCM82633A004352",
        year=2016,
        make="Honda",
        model="Accord",
        mileage=80000,
    )
    repair = RepairHistory(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_type="brakes",
        description="Front pads",
        cost=Decimal("420.00"),
        recommendation="Customer declined brake job",
        created_at=datetime.now(timezone.utc),
    )
    ctx = _ctx(
        shop_id=shop_id,
        customers={customer.id: customer},
        vehicles_by_id={vehicle.id: vehicle},
        vehicles_by_customer={customer.id: [vehicle]},
        repairs=[repair],
    )
    members = resolve_from_context(ctx, CampaignType.DECLINED_ESTIMATE)
    assert len(members) == 1
    assert members[0].metadata["service"] == "brakes"
    assert "Honda Accord" in members[0].metadata["vehicle"]


def test_resolve_open_recommendations_from_repair_notes():
    shop_id = uuid4()
    customer = Customer(id=uuid4(), shop_id=shop_id, name="Jordan", phone="+15550005")
    vehicle = Vehicle(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vin="1HGCM82633A004353",
        year=2018,
        make="Toyota",
        model="Camry",
        mileage=62000,
    )
    open_repair = RepairHistory(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_type="inspection",
        description="Multi-point inspection",
        cost=Decimal("89.00"),
        recommendation="Replace pads within 6 months",
        created_at=datetime.now(timezone.utc),
    )
    declined_repair = RepairHistory(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_type="brakes",
        description="Estimate",
        cost=Decimal("420.00"),
        recommendation="Customer declined brake job",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    ctx = _ctx(
        shop_id=shop_id,
        customers={customer.id: customer},
        vehicles_by_id={vehicle.id: vehicle},
        vehicles_by_customer={customer.id: [vehicle]},
        repairs=[open_repair, declined_repair],
    )
    members = resolve_from_context(
        ctx,
        CampaignType.MAINTENANCE_REMINDER,
        tags=["open_recommendation"],
        segment="open_recommendation",
    )
    assert len(members) == 1
    assert members[0].metadata["service"] == "Replace pads within 6 months"
    assert members[0].metadata["source"] == "open_recommendation"


def test_resolve_open_recommendations_combines_tire_and_brake():
    shop_id = uuid4()
    customer = Customer(id=uuid4(), shop_id=shop_id, name="Riley Chen", phone="+15550330")
    vehicle = Vehicle(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vin="1G1YY22G165123456",
        year=2021,
        make="Chevrolet",
        model="Corvette",
        mileage=18500,
    )
    tire = RepairHistory(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_type="Tire Rotation",
        description="Rotated all four",
        cost=Decimal("39.99"),
        recommendation=None,
        created_at=datetime.now(timezone.utc),
    )
    brake = RepairHistory(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_type="Brake Repair",
        description="Front pads",
        cost=Decimal("320.00"),
        recommendation=None,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    oil = RepairHistory(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_type="Oil Change",
        description="Synthetic",
        cost=Decimal("119.00"),
        recommendation=None,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    ctx = _ctx(
        shop_id=shop_id,
        customers={customer.id: customer},
        vehicles_by_id={vehicle.id: vehicle},
        vehicles_by_customer={customer.id: [vehicle]},
        repairs=[tire, brake, oil],
    )
    members = resolve_from_context(
        ctx,
        CampaignType.MAINTENANCE_REMINDER,
        tags=["open_recommendation"],
    )
    assert len(members) == 1
    service = members[0].metadata["service"]
    assert "Tire Rotation" in service
    assert "Brake Repair" in service
    assert "Oil" not in service


def test_resolve_maintenance_maps_shop_catalog_tire_and_brake():
    shop_id = uuid4()
    now = datetime.now(timezone.utc)
    customer = Customer(id=uuid4(), shop_id=shop_id, name="Riley Chen", phone="+15550330")
    vehicle = Vehicle(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vin="1G1YY22G165123456",
        year=2021,
        make="Chevrolet",
        model="Corvette",
        mileage=18500,
        created_at=now - timedelta(days=30),
    )
    tire = RepairHistory(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_type="Tire Rotation",
        description="Rotated",
        cost=Decimal("39.99"),
        created_at=now - timedelta(days=1200),
    )
    brake = RepairHistory(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_type="Brake Repair",
        description="Pads",
        cost=Decimal("320.00"),
        created_at=now - timedelta(days=800),
    )
    oil = RepairHistory(
        id=uuid4(),
        shop_id=shop_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_type="Oil Change",
        description="Synthetic",
        cost=Decimal("119.00"),
        created_at=now - timedelta(days=10),
    )
    ctx = _ctx(
        shop_id=shop_id,
        now=now,
        customers={customer.id: customer},
        vehicles_by_id={vehicle.id: vehicle},
        vehicles_by_customer={customer.id: [vehicle]},
        repairs=[tire, brake, oil],
    )
    members = resolve_from_context(ctx, CampaignType.MAINTENANCE_REMINDER)
    assert len(members) == 1
    service = members[0].metadata["service"]
    assert "Brake replacement" in service
    assert "Tire replacement" in service


def test_resolve_missed_appointments_via_tag():
    shop_id = uuid4()
    customer = Customer(id=uuid4(), shop_id=shop_id, name="Sam", phone="+15550004")
    appt = Appointment(
        id=uuid4(),
        shop_id=shop_id,
        start=datetime.now(timezone.utc) - timedelta(days=3),
        end=datetime.now(timezone.utc) - timedelta(days=3) + timedelta(hours=1),
        status=AppointmentStatus.NO_SHOW.value,
        repair_type="oil_change",
        customer_id=customer.id,
    )
    ctx = _ctx(
        shop_id=shop_id,
        customers={customer.id: customer},
        appointments=[appt],
    )
    members = resolve_from_context(
        ctx,
        CampaignType.THANK_YOU,
        tags=["missed_appointment"],
        segment="missed_appointment",
    )
    assert len(members) == 1
    assert members[0].metadata["service"] == "oil_change"
