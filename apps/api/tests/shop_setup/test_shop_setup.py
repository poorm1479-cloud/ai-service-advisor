"""Shop setup wizard + service catalog API tests."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.auth_helpers import register_shop_via_otp

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://asa:asa@localhost:5432/ai_service_advisor",
)


async def _db_available() -> bool:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def require_db():
    if not await _db_available():
        pytest.skip("PostgreSQL not available — set DATABASE_URL and run migrations")


@pytest.fixture
async def client(require_db):
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _hours() -> list[dict]:
    return [
        {
            "weekday": d,
            "open_time": "08:00",
            "close_time": "17:00",
            "closed": d >= 5,
        }
        for d in range(7)
    ]


async def test_setup_wizard_and_phone_catalog(client: AsyncClient):
    reg = await register_shop_via_otp(client, shop_name="Setup Garage")
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    status = await client.get("/v1/shop/setup/status", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["setup_completed"] is False
    assert "services" in status.json()["missing"]

    state = await client.get("/v1/shop/setup", headers=headers)
    assert state.status_code == 200, state.text
    body = state.json()
    assert "starter_services" in body["meta"]
    # Signup contact should prefill shop profile (no re-entry in Settings/Setup).
    assert body["profile"]["phone"] == reg["_test_phone"]
    assert body["profile"]["email"] == reg["_test_email"]

    complete = await client.post(
        "/v1/shop/setup/complete",
        headers=headers,
        json={
            "profile": {
                "name": "Setup Garage",
                "timezone": "America/Los_Angeles",
                "phone": "+15551234567",
            },
            "business_hours": _hours(),
            "services": [
                {
                    "name": "Oil Change",
                    "category": "maintenance",
                    "duration_minutes": 30,
                    "price": "49.99",
                    "skill": "oil_change",
                    "bay": "quick_service",
                    "active": True,
                }
            ],
        },
    )
    assert complete.status_code == 200, complete.text
    body = complete.json()
    assert body["status"]["setup_completed"] is True
    assert len(body["services"]) == 1

    catalog = await client.get("/v1/shop/phone-catalog", headers=headers)
    assert catalog.status_code == 200, catalog.text
    payload = catalog.json()
    assert payload["bookable_service_count"] == 1
    assert payload["services"][0]["skill"] == "oil_change"
    assert payload["services"][0]["bay"] == "quick_service"
    assert len(payload["business_hours"]) == 7

    created = await client.post(
        "/v1/shop/services",
        headers=headers,
        json={
            "name": "Brake Job",
            "category": "brakes",
            "duration_minutes": 90,
            "price": "220.00",
            "skill": "brakes",
            "bay": "general",
            "active": True,
        },
    )
    assert created.status_code == 201, created.text
    service_id = created.json()["id"]

    patched = await client.patch(
        f"/v1/shop/services/{service_id}",
        headers=headers,
        json={"price": "199.00", "active": True},
    )
    assert patched.status_code == 200, patched.text
    assert str(patched.json()["price"]) in {"199.00", "199.0"}

    settings = await client.patch(
        "/v1/shop/settings",
        headers=headers,
        json={"profile": {"phone": "+15557654321", "city": "Dallas"}},
    )
    assert settings.status_code == 200, settings.text
    assert settings.json()["profile"]["phone"] == "+15557654321"
    assert settings.json()["profile"]["city"] == "Dallas"

    new_hours = [
        {
            "weekday": d,
            "open_time": "09:30:00" if d == 0 else "09:30",
            "close_time": "18:30",
            "closed": d >= 6,
        }
        for d in range(7)
    ]
    hours_patch = await client.patch(
        "/v1/shop/settings",
        headers=headers,
        json={"business_hours": new_hours},
    )
    assert hours_patch.status_code == 200, hours_patch.text
    assert hours_patch.json()["business_hours"][0]["open_time"] == "09:30"
    assert hours_patch.json()["business_hours"][5]["closed"] is False
    assert hours_patch.json()["business_hours"][6]["closed"] is True

    reloaded = await client.get("/v1/shop/setup", headers=headers)
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json()["business_hours"][0]["open_time"] == "09:30"
    assert reloaded.json()["business_hours"][0]["close_time"] == "18:30"
    assert reloaded.json()["business_hours"][6]["closed"] is True

    all_closed = [
        {
            "weekday": d,
            "open_time": "09:30",
            "close_time": "18:30",
            "closed": True,
        }
        for d in range(7)
    ]
    closed_patch = await client.patch(
        "/v1/shop/settings",
        headers=headers,
        json={"business_hours": all_closed},
    )
    assert closed_patch.status_code == 200, closed_patch.text
    assert all(h["closed"] is True for h in closed_patch.json()["business_hours"])
    assert closed_patch.json()["status"]["has_business_hours"] is True

    closed_reload = await client.get("/v1/shop/setup", headers=headers)
    assert closed_reload.status_code == 200, closed_reload.text
    assert all(h["closed"] is True for h in closed_reload.json()["business_hours"])


async def test_phone_signup_setup_email_syncs_to_owner_profile(client: AsyncClient):
    """Phone-only register has no User.email; setup shop email must fill Settings."""
    import uuid

    tag = uuid.uuid4().hex[:8]
    phone = f"+1555{int(tag[:7], 16) % 10_000_000:07d}"
    email = f"setup-{tag}@example.com"
    register = await client.post(
        "/v1/auth/register",
        json={
            "shop_name": "Phone Only Garage",
            "shop_slug": f"phone-only-{tag}",
            "auth_method": "phone",
            "owner_phone": phone,
            "owner_full_name": "Phone Owner",
            "password": "password123",
        },
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_before = await client.get("/v1/auth/me", headers=headers)
    assert me_before.status_code == 200, me_before.text
    assert me_before.json()["email"] in (None, "")

    complete = await client.post(
        "/v1/shop/setup/complete",
        headers=headers,
        json={
            "profile": {
                "name": "Phone Only Garage",
                "timezone": "America/Los_Angeles",
                "phone": phone,
                "email": email,
            },
            "business_hours": _hours(),
            "services": [
                {
                    "name": "Oil Change",
                    "category": "maintenance",
                    "duration_minutes": 30,
                    "price": "49.99",
                    "skill": "oil_change",
                    "bay": "quick_service",
                    "active": True,
                }
            ],
        },
    )
    assert complete.status_code == 200, complete.text

    me_after = await client.get("/v1/auth/me", headers=headers)
    assert me_after.status_code == 200, me_after.text
    assert me_after.json()["email"] == email

    profile = await client.patch(
        "/v1/tenant/me/profile",
        headers=headers,
        json={"full_name": "Phone Owner", "phone": phone, "email": email},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["email"] == email
