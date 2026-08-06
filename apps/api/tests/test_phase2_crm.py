"""Phase 2 CRM — customers, vehicles, repair & communication history."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

VALID_VIN = "1HGCM82633A004352"


@pytest.fixture
async def require_db():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    import os

    url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://asa:asa@localhost:5432/ai_service_advisor",
    )
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL not available")
    finally:
        await engine.dispose()


@pytest.fixture
async def client(require_db):
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _register(client: AsyncClient, suffix: str) -> dict:
    from tests.auth_helpers import register_shop_via_otp

    return await register_shop_via_otp(
        client,
        suffix=suffix,
        shop_name=f"CRM Shop {suffix}",
        shop_slug=f"crm-{suffix}",
        owner_full_name="CRM Owner",
        email=f"crm-{suffix}@example.com",
    )


async def test_customer_crud_search_and_update(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    auth = await _register(client, suffix)
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    create = await client.post(
        "/v1/customers",
        headers=headers,
        json={
            "name": "Jane Driver",
            "phone": "555-0100",
            "email": "jane@example.com",
            "address": "100 Main St",
        },
    )
    assert create.status_code == 201, create.text
    customer_id = create.json()["id"]
    assert create.json()["address"] == "100 Main St"

    search = await client.get("/v1/customers", headers=headers, params={"q": "Jane"})
    assert search.status_code == 200
    assert any(c["id"] == customer_id for c in search.json())

    update = await client.patch(
        f"/v1/customers/{customer_id}",
        headers=headers,
        json={"phone": "555-0199", "address": "200 Oak Ave"},
    )
    assert update.status_code == 200, update.text
    assert update.json()["phone"] == "555-0199"
    assert update.json()["address"] == "200 Oak Ave"
    assert update.json()["name"] == "Jane Driver"


async def test_create_customer_rejects_duplicate_phone_or_email(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    auth = await _register(client, suffix)
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    first = await client.post(
        "/v1/customers",
        headers=headers,
        json={
            "name": "Jane Driver",
            "phone": "555-010-0123",
            "email": "jane@example.com",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["phone"] == "+15550100123"

    # UI formats as "+1 NXX NXX XXXX" — must still collide with 10-digit storage
    dup_phone = await client.post(
        "/v1/customers",
        headers=headers,
        json={"name": "Other Person", "phone": "+1 555 010 0123"},
    )
    assert dup_phone.status_code == 409
    assert "phone" in dup_phone.json()["detail"].lower()

    dup_email = await client.post(
        "/v1/customers",
        headers=headers,
        json={"name": "Other Person", "email": "Jane@example.com"},
    )
    assert dup_email.status_code == 409
    assert "email" in dup_email.json()["detail"].lower()

    other = await client.post(
        "/v1/customers",
        headers=headers,
        json={"name": "Bob Owner", "phone": "555-020-0456"},
    )
    assert other.status_code == 201, other.text


async def test_vehicle_history_and_communication_timeline(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    auth = await _register(client, suffix)
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    customer = await client.post(
        "/v1/customers",
        headers=headers,
        json={"name": "Bob Owner", "phone": "555-0200"},
    )
    customer_id = customer.json()["id"]

    vehicle = await client.post(
        f"/v1/customers/{customer_id}/vehicles",
        headers=headers,
        json={
            "vin": VALID_VIN,
            "license_plate": "ABC1234",
            "year": 2018,
            "make": "Honda",
            "model": "Accord",
            "mileage": 82000,
        },
    )
    assert vehicle.status_code == 201, vehicle.text
    vehicle_id = vehicle.json()["id"]
    assert vehicle.json()["vin"] == VALID_VIN

    bad_vin = await client.post(
        f"/v1/customers/{customer_id}/vehicles",
        headers=headers,
        json={
            "vin": "INVALIDVIN0000000",
            "year": 2018,
            "make": "Honda",
            "model": "Civic",
            "mileage": 10,
        },
    )
    assert bad_vin.status_code == 422

    repair = await client.post(
        f"/v1/vehicles/{vehicle_id}/history",
        headers=headers,
        json={
            "service_type": "Oil Change",
            "description": "Full synthetic oil change",
            "cost": "89.99",
            "recommendation": "Return in 5,000 miles",
        },
    )
    assert repair.status_code == 201, repair.text

    history = await client.get(f"/v1/vehicles/{vehicle_id}/history", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["service_type"] == "Oil Change"

    detail = await client.get(f"/v1/vehicles/{vehicle_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["vehicle"]["id"] == vehicle_id
    assert len(detail.json()["repair_history"]) == 1

    updated = await client.patch(
        f"/v1/vehicles/{vehicle_id}",
        headers=headers,
        json={
            "license_plate": "XYZ9876",
            "mileage": 84500,
            "make": "Honda",
            "model": "Accord Sport",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["license_plate"] == "XYZ9876"
    assert updated.json()["mileage"] == 84500
    assert updated.json()["model"] == "Accord Sport"

    comm = await client.post(
        f"/v1/customers/{customer_id}/communications",
        headers=headers,
        json={
            "channel": "sms",
            "direction": "outgoing",
            "message": "Your oil change is complete.",
        },
    )
    assert comm.status_code == 201, comm.text

    timeline = await client.get(
        f"/v1/customers/{customer_id}/communications", headers=headers
    )
    assert timeline.status_code == 200
    assert len(timeline.json()) == 1
    assert timeline.json()[0]["channel"] == "sms"

    customer_detail = await client.get(f"/v1/customers/{customer_id}", headers=headers)
    assert customer_detail.status_code == 200
    assert len(customer_detail.json()["vehicles"]) == 1
    assert len(customer_detail.json()["communications"]) == 1
    assert len(customer_detail.json()["repair_history"]) == 1
    assert customer_detail.json()["repair_history"][0]["service_type"] == "Oil Change"

    repair_id = repair.json()["id"]
    deleted_repair = await client.delete(
        f"/v1/vehicles/{vehicle_id}/history/{repair_id}", headers=headers
    )
    assert deleted_repair.status_code == 204, deleted_repair.text

    history_after = await client.get(f"/v1/vehicles/{vehicle_id}/history", headers=headers)
    assert history_after.status_code == 200
    assert history_after.json() == []

    customer_after_repair_delete = await client.get(
        f"/v1/customers/{customer_id}", headers=headers
    )
    assert customer_after_repair_delete.status_code == 200
    assert customer_after_repair_delete.json()["repair_history"] == []

    gone_repair = await client.delete(
        f"/v1/vehicles/{vehicle_id}/history/{repair_id}", headers=headers
    )
    assert gone_repair.status_code == 404

    # Re-add so vehicle delete still exercises cascade of remaining history cleanup
    repair_again = await client.post(
        f"/v1/vehicles/{vehicle_id}/history",
        headers=headers,
        json={
            "service_type": "Brake Inspection",
            "description": "Pads within spec",
            "cost": "0",
        },
    )
    assert repair_again.status_code == 201, repair_again.text

    deleted = await client.delete(f"/v1/vehicles/{vehicle_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text

    gone = await client.get(f"/v1/vehicles/{vehicle_id}", headers=headers)
    assert gone.status_code == 404

    after_delete = await client.get(f"/v1/customers/{customer_id}", headers=headers)
    assert after_delete.status_code == 200
    assert after_delete.json()["vehicles"] == []


async def test_crm_shop_isolation(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    shop_a = await _register(client, f"a-{suffix}")
    shop_b = await _register(client, f"b-{suffix}")
    headers_a = {"Authorization": f"Bearer {shop_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {shop_b['access_token']}"}

    customer_a = await client.post(
        "/v1/customers",
        headers=headers_a,
        json={"name": "Secret Customer", "phone": "555-9999"},
    )
    assert customer_a.status_code == 201
    customer_id = customer_a.json()["id"]

    vehicle_a = await client.post(
        f"/v1/customers/{customer_id}/vehicles",
        headers=headers_a,
        json={
            "vin": VALID_VIN,
            "year": 2020,
            "make": "Toyota",
            "model": "Camry",
            "mileage": 1000,
        },
    )
    assert vehicle_a.status_code == 201
    vehicle_id = vehicle_a.json()["id"]

    list_b = await client.get("/v1/customers", headers=headers_b, params={"q": "Secret"})
    assert list_b.status_code == 200
    assert list_b.json() == []

    get_customer_b = await client.get(f"/v1/customers/{customer_id}", headers=headers_b)
    assert get_customer_b.status_code == 404

    get_vehicle_b = await client.get(f"/v1/vehicles/{vehicle_id}", headers=headers_b)
    assert get_vehicle_b.status_code == 404

    delete_vehicle_b = await client.delete(f"/v1/vehicles/{vehicle_id}", headers=headers_b)
    assert delete_vehicle_b.status_code == 404

    still_there = await client.get(f"/v1/vehicles/{vehicle_id}", headers=headers_a)
    assert still_there.status_code == 200


async def test_customer_directory_batches_vehicles_and_last_service(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    auth = await _register(client, suffix)
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    customer = await client.post(
        "/v1/customers",
        headers=headers,
        json={"name": "Dir Customer", "phone": "555-0300"},
    )
    assert customer.status_code == 201
    customer_id = customer.json()["id"]

    vehicle = await client.post(
        f"/v1/customers/{customer_id}/vehicles",
        headers=headers,
        json={
            "vin": VALID_VIN,
            "year": 2019,
            "make": "Ford",
            "model": "F-150",
            "mileage": 40000,
        },
    )
    assert vehicle.status_code == 201
    vehicle_id = vehicle.json()["id"]

    repair = await client.post(
        f"/v1/vehicles/{vehicle_id}/history",
        headers=headers,
        json={
            "service_type": "Brake Pads",
            "description": "Front pads replaced",
            "cost": "220.00",
        },
    )
    assert repair.status_code == 201

    directory = await client.get("/v1/customers/directory", headers=headers)
    assert directory.status_code == 200, directory.text
    rows = directory.json()
    assert len(rows) >= 1
    row = next(r for r in rows if r["customer"]["id"] == customer_id)
    assert len(row["vehicles"]) == 1
    assert row["vehicles"][0]["vin"] == VALID_VIN
    assert row["last_service"] is not None
    assert row["last_service"]["service_type"] == "Brake Pads"

    by_vin = await client.get(
        "/v1/customers/directory", headers=headers, params={"q": VALID_VIN[-6:]}
    )
    assert by_vin.status_code == 200
    assert any(r["customer"]["id"] == customer_id for r in by_vin.json())


async def test_delete_customer(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    shop = await _register(client, suffix)
    headers = {"Authorization": f"Bearer {shop['access_token']}"}

    created = await client.post(
        "/v1/customers",
        headers=headers,
        json={"name": "Delete Me", "phone": "555-0100", "email": f"del-{suffix}@example.com"},
    )
    assert created.status_code == 201, created.text
    customer_id = created.json()["id"]

    vehicle = await client.post(
        f"/v1/customers/{customer_id}/vehicles",
        headers=headers,
        json={
            "vin": VALID_VIN,
            "year": 2019,
            "make": "Ford",
            "model": "Focus",
            "mileage": 50000,
        },
    )
    assert vehicle.status_code == 201, vehicle.text
    vehicle_id = vehicle.json()["id"]

    comm = await client.post(
        f"/v1/customers/{customer_id}/communications",
        headers=headers,
        json={
            "channel": "sms",
            "direction": "outgoing",
            "message": "See you soon",
        },
    )
    assert comm.status_code == 201, comm.text

    deleted = await client.delete(f"/v1/customers/{customer_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text

    gone = await client.get(f"/v1/customers/{customer_id}", headers=headers)
    assert gone.status_code == 404

    # Vehicles and related CRM data are hard-deleted with the customer
    vehicle_detail = await client.get(f"/v1/vehicles/{vehicle_id}", headers=headers)
    assert vehicle_detail.status_code == 404

    missing = await client.delete(f"/v1/customers/{customer_id}", headers=headers)
    assert missing.status_code == 404
