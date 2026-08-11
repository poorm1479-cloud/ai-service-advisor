"""Walk-in intake — no customer required at arrival."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

VALID_VIN = "1FTFW1ET5DFC10312"
OTHER_VIN = "2HGES16575H580247"


@pytest.fixture
async def require_db():
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

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
        shop_name=f"Walkin Shop {suffix}",
        shop_slug=f"walkin-{suffix}",
        owner_full_name="Walkin Owner",
        email=f"walkin-{suffix}@example.com",
    )


async def test_create_walk_in_without_customer(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    auth = await _register(client, suffix)
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    arrived = datetime.now(timezone.utc).isoformat()

    res = await client.post(
        "/v1/walk-ins",
        headers=headers,
        json={
            "vin": VALID_VIN,
            "year": 2014,
            "make": "Ford",
            "model": "F-150",
            "mileage": 120000,
            "complaint": "Brakes squeaking on arrival",
            "arrived_at": arrived,
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["visit"]["customer_id"] is None
    assert body["customer"] is None
    assert body["vehicle"]["customer_id"] is None
    assert body["visit"]["status"] == "open"
    assert "Brakes squeaking" in body["visit"]["complaint"]


async def test_convert_attach_repair_and_isolation(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    shop_a = await _register(client, f"a-{suffix}")
    shop_b = await _register(client, f"b-{suffix}")
    headers_a = {"Authorization": f"Bearer {shop_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {shop_b['access_token']}"}

    created = await client.post(
        "/v1/walk-ins",
        headers=headers_a,
        json={
            "vin": VALID_VIN,
            "year": 2016,
            "make": "Honda",
            "model": "Civic",
            "mileage": 80000,
            "complaint": "Check engine light",
        },
    )
    assert created.status_code == 201, created.text
    visit_id = created.json()["visit"]["id"]

    # Attach repair history before customer exists
    repair = await client.post(
        f"/v1/walk-ins/{visit_id}/repair-history",
        headers=headers_a,
        json={
            "service_type": "Diagnostics",
            "description": "Scanned codes P0420",
            "cost": "120.00",
            "recommendation": "Replace catalytic converter",
        },
    )
    assert repair.status_code == 200, repair.text
    assert len(repair.json()["repair_history"]) == 1
    assert repair.json()["repair_history"][0]["customer_id"] is None

    # Convert — name required, phone optional
    converted = await client.post(
        f"/v1/walk-ins/{visit_id}/convert-customer",
        headers=headers_a,
        json={"name": "Walkin Guest"},
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["visit"]["status"] == "converted"
    assert converted.json()["customer"]["name"] == "Walkin Guest"
    assert converted.json()["customer"]["phone"] is None
    assert converted.json()["vehicle"]["customer_id"] == converted.json()["customer"]["id"]

    # Attach another vehicle by details
    attached = await client.post(
        f"/v1/walk-ins/{visit_id}/attach-vehicle",
        headers=headers_a,
        json={
            "vin": OTHER_VIN,
            "year": 2015,
            "make": "Honda",
            "model": "Fit",
            "mileage": 90000,
            "license_plate": "WALK1",
        },
    )
    assert attached.status_code == 200, attached.text
    assert attached.json()["vehicle"]["vin"] == OTHER_VIN
    assert attached.json()["vehicle"]["customer_id"] == converted.json()["customer"]["id"]

    # Cross-shop isolation
    list_b = await client.get("/v1/walk-ins", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json() == []

    get_b = await client.get(f"/v1/walk-ins/{visit_id}", headers=headers_b)
    assert get_b.status_code == 404


async def test_close_walk_in(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    auth = await _register(client, suffix)
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    created = await client.post(
        "/v1/walk-ins",
        headers=headers,
        json={
            "vin": VALID_VIN,
            "year": 2014,
            "make": "Ford",
            "model": "F-150",
            "mileage": 120000,
            "complaint": "Oil change",
        },
    )
    assert created.status_code == 201, created.text
    visit_id = created.json()["visit"]["id"]

    closed = await client.post(f"/v1/walk-ins/{visit_id}/close", headers=headers)
    assert closed.status_code == 200, closed.text
    assert closed.json()["visit"]["status"] == "closed"

    again = await client.post(f"/v1/walk-ins/{visit_id}/close", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["visit"]["status"] == "closed"

    blocked = await client.post(
        f"/v1/walk-ins/{visit_id}/repair-history",
        headers=headers,
        json={
            "service_type": "Oil Change",
            "description": "After close",
            "cost": "49.00",
        },
    )
    assert blocked.status_code == 409, blocked.text

    cannot_cancel = await client.post(f"/v1/walk-ins/{visit_id}/cancel", headers=headers)
    assert cannot_cancel.status_code == 409, cannot_cancel.text


async def test_cancel_walk_in(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    auth = await _register(client, suffix)
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    created = await client.post(
        "/v1/walk-ins",
        headers=headers,
        json={
            "vin": VALID_VIN,
            "year": 2014,
            "make": "Ford",
            "model": "F-150",
            "mileage": 120000,
            "complaint": "Brake noise",
        },
    )
    assert created.status_code == 201, created.text
    visit_id = created.json()["visit"]["id"]

    cancelled = await client.post(f"/v1/walk-ins/{visit_id}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["visit"]["status"] == "cancelled"

    again = await client.post(f"/v1/walk-ins/{visit_id}/cancel", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["visit"]["status"] == "cancelled"

    blocked_repair = await client.post(
        f"/v1/walk-ins/{visit_id}/repair-history",
        headers=headers,
        json={
            "service_type": "Brakes",
            "description": "After cancel",
            "cost": "99.00",
        },
    )
    assert blocked_repair.status_code == 409, blocked_repair.text

    cannot_close = await client.post(f"/v1/walk-ins/{visit_id}/close", headers=headers)
    assert cannot_close.status_code == 409, cannot_close.text

    cannot_convert = await client.post(
        f"/v1/walk-ins/{visit_id}/convert-customer",
        headers=headers,
        json={"name": "Should Fail"},
    )
    assert cannot_convert.status_code == 409, cannot_convert.text


async def test_no_vin_match_by_plate_links_customer(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    auth = await _register(client, suffix)
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    customer = await client.post(
        "/v1/customers",
        headers=headers,
        json={"name": "Plate Match Guest", "phone": "+15551234567"},
    )
    assert customer.status_code == 201, customer.text
    customer_id = customer.json()["id"]

    vehicle = await client.post(
        f"/v1/customers/{customer_id}/vehicles",
        headers=headers,
        json={
            "vin": VALID_VIN,
            "license_plate": "ABC1234",
            "year": 2018,
            "make": "Toyota",
            "model": "Camry",
            "mileage": 50000,
        },
    )
    assert vehicle.status_code == 201, vehicle.text

    assist = await client.get(
        "/v1/vehicles/match-assist",
        headers=headers,
        params={"license_plate": "abc-1234"},
    )
    assert assist.status_code == 200, assist.text
    assert assist.json()["match_type"] == "license_plate"
    assert assist.json()["existing"]["vin"] == VALID_VIN
    assert assist.json()["existing"]["customer_id"] == customer_id

    # Temp VIN + same plate should attach to the existing vehicle/customer
    created = await client.post(
        "/v1/walk-ins",
        headers=headers,
        json={
            "vin": "TMPABCDEFGHJKLMNP",
            "license_plate": "ABC1234",
            "year": 2018,
            "make": "Toyota",
            "model": "Camry",
            "mileage": 51000,
            "complaint": "Oil change",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["vehicle"]["id"] == vehicle.json()["id"]
    assert body["vehicle"]["vin"] == VALID_VIN
    assert body["visit"]["customer_id"] == customer_id
    assert body["customer"]["name"] == "Plate Match Guest"
