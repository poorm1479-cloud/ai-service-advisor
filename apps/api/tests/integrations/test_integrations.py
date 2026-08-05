"""Phase 18 External Integration Layer tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.integrations.core.registry import build_default_registry
from app.integrations.enums import (
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)
from app.integrations.factory import build_integrations_runtime, reset_integrations_runtime
from app.integrations.models import CapabilityRequest, TenantScopedRecord
from app.integrations.security import TenantIsolationError, assert_same_tenant, stamp_tenant
from app.integrations.store import InMemoryIntegrationStore


@pytest.fixture(autouse=True)
def _reset():
    reset_integrations_runtime()
    yield
    reset_integrations_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def other_shop():
    return uuid4()


@pytest.fixture
def runtime():
    return build_integrations_runtime(store=InMemoryIntegrationStore())


def test_all_required_adapters_registered():
    registry = build_default_registry()
    providers = {a.provider for a in registry.list()}
    required = {
        IntegrationProvider.SHOPMONKEY,
        IntegrationProvider.TEKMETRIC,
        IntegrationProvider.AUTOLEAP,
        IntegrationProvider.MITCHELL,
        IntegrationProvider.QUICKBOOKS,
        IntegrationProvider.TWILIO,
        IntegrationProvider.EMAIL,
        IntegrationProvider.STRIPE,
    }
    assert required == providers


def test_capability_matrix_covers_all_capabilities():
    registry = build_default_registry()
    for cap in IntegrationCapability:
        assert registry.providers_for(cap), f"No provider for {cap.value}"


def test_dms_category_adapters():
    registry = build_default_registry()
    dms = registry.list_by_category(IntegrationCategory.DMS)
    assert {a.provider for a in dms} == {
        IntegrationProvider.SHOPMONKEY,
        IntegrationProvider.TEKMETRIC,
        IntegrationProvider.AUTOLEAP,
        IntegrationProvider.MITCHELL,
    }


def test_tenant_stamp_and_isolation():
    shop = uuid4()
    stamped = stamp_tenant({"name": "A"}, shop_id=shop)
    assert stamped["tenant_id"] == str(shop)
    assert stamped["shop_id"] == str(shop)
    with pytest.raises(TenantIsolationError):
        assert_same_tenant(expected_shop_id=shop, actual_shop_id=uuid4())


@pytest.mark.asyncio
async def test_connect_mitchell_demo(runtime, shop_id):
    conn = await runtime.service.connect(
        shop_id=shop_id,
        provider=IntegrationProvider.MITCHELL,
        demo=True,
    )
    assert conn.provider == IntegrationProvider.MITCHELL
    assert conn.status.value == "connected"
    listed = await runtime.service.list_connections(shop_id)
    assert any(c["provider"] == "mitchell" and c["status"] == "connected" for c in listed)
    tested = await runtime.service.test_connection(
        shop_id=shop_id, provider=IntegrationProvider.MITCHELL
    )
    assert tested["ok"] is True
    assert tested["provider"] == "mitchell"


@pytest.mark.asyncio
async def test_connect_and_import_customers_tenant_scoped(runtime, shop_id, other_shop):
    conn = await runtime.service.connect(
        shop_id=shop_id,
        provider=IntegrationProvider.SHOPMONKEY,
        demo=True,
    )
    assert conn.tenant_id == shop_id
    assert conn.shop_id == shop_id

    result = await runtime.service.import_customer_data(
        shop_id=shop_id,
        provider=IntegrationProvider.SHOPMONKEY,
        emit_workflow=False,
        invoke_plugins=False,
    )
    assert result.ok
    assert result.tenant_id == shop_id
    assert result.records
    for record in result.records:
        assert isinstance(record, TenantScopedRecord)
        assert record.tenant_id == shop_id
        assert record.shop_id == shop_id
        assert record.data["tenant_id"] == str(shop_id)

    # Other shop cannot see this connection
    listed = await runtime.service.list_connections(other_shop)
    assert listed == []


@pytest.mark.asyncio
async def test_import_vehicles_and_repairs(runtime, shop_id):
    await runtime.service.connect(
        shop_id=shop_id, provider=IntegrationProvider.TEKMETRIC, demo=True
    )
    vehicles = await runtime.service.import_vehicle_data(
        shop_id=shop_id,
        provider=IntegrationProvider.TEKMETRIC,
        emit_workflow=False,
        invoke_plugins=False,
    )
    repairs = await runtime.service.import_repair_history(
        shop_id=shop_id,
        provider=IntegrationProvider.TEKMETRIC,
        emit_workflow=False,
        invoke_plugins=False,
    )
    assert vehicles.ok and repairs.ok
    assert all(r.tenant_id == shop_id for r in vehicles.records + repairs.records)


@pytest.mark.asyncio
async def test_sync_appointment_invoice_payment(runtime, shop_id):
    await runtime.service.connect(
        shop_id=shop_id, provider=IntegrationProvider.AUTOLEAP, demo=True
    )
    await runtime.service.connect(
        shop_id=shop_id, provider=IntegrationProvider.QUICKBOOKS, demo=True
    )
    await runtime.service.connect(
        shop_id=shop_id, provider=IntegrationProvider.STRIPE, demo=True
    )

    appt = await runtime.service.sync_appointment(
        shop_id=shop_id,
        provider=IntegrationProvider.AUTOLEAP,
        emit_workflow=False,
        invoke_plugins=False,
    )
    inv = await runtime.service.sync_invoice(
        shop_id=shop_id,
        provider=IntegrationProvider.QUICKBOOKS,
        emit_workflow=False,
        invoke_plugins=False,
    )
    pay = await runtime.service.sync_payment(
        shop_id=shop_id,
        provider=IntegrationProvider.STRIPE,
        emit_workflow=False,
        invoke_plugins=False,
    )
    assert appt.ok and inv.ok and pay.ok


@pytest.mark.asyncio
async def test_send_and_receive_messages(runtime, shop_id):
    await runtime.service.connect(
        shop_id=shop_id, provider=IntegrationProvider.TWILIO, demo=True
    )
    sent = await runtime.service.send_customer_message(
        shop_id=shop_id,
        provider=IntegrationProvider.TWILIO,
        payload={"to": "+15550001", "body": "Your car is ready"},
        emit_workflow=False,
        invoke_plugins=False,
    )
    received = await runtime.service.receive_customer_message(
        shop_id=shop_id,
        provider=IntegrationProvider.EMAIL,
        payload={"from": "c@example.com", "body": "Thanks"},
        emit_workflow=False,
        invoke_plugins=False,
    )
    assert sent.ok and received.ok
    assert sent.records[0].data["direction"] == "outbound"
    assert received.records[0].data["direction"] == "inbound"
    assert received.records[0].tenant_id == shop_id


@pytest.mark.asyncio
async def test_unsupported_capability_returns_error(runtime, shop_id):
    result = await runtime.service.execute(
        CapabilityRequest(
            capability=IntegrationCapability.SYNC_PAYMENT,
            shop_id=shop_id,
            emit_workflow=False,
            invoke_plugins=False,
        ),
        provider=IntegrationProvider.SHOPMONKEY,
    )
    assert result.ok is False
    assert result.error


@pytest.mark.asyncio
async def test_cross_shop_connection_access_denied(runtime, shop_id, other_shop):
    conn = await runtime.service.connect(
        shop_id=shop_id, provider=IntegrationProvider.STRIPE, demo=True
    )
    with pytest.raises(TenantIsolationError):
        await runtime.store.get(other_shop, conn.id)


@pytest.mark.asyncio
async def test_execute_with_workflow_emit(runtime, shop_id):
    """Emitting into workflow must not raise; uses existing domain events."""
    result = await runtime.service.import_customer_data(
        shop_id=shop_id,
        provider=IntegrationProvider.SHOPMONKEY,
        emit_workflow=True,
        invoke_plugins=False,
    )
    assert result.ok
    assert result.workflow_event == "crm.updated"
