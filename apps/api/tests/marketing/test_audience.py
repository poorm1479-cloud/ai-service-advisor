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
