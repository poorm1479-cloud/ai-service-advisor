"""Phase 1 — auth, refresh tokens, shop isolation (phone + SMS OTP)."""

from __future__ import annotations

import os
import uuid

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


async def test_health(client: AsyncClient):
    res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"
    assert isinstance(body.get("phase"), str) and body["phase"]


async def test_register_without_otp(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    res = await client.post(
        "/v1/auth/register",
        json={
            "shop_name": "No OTP Garage",
            "shop_slug": f"no-otp-{suffix}",
            "auth_method": "phone",
            "owner_phone": f"+1555{int(suffix[:7], 16) % 10_000_000:07d}",
            "owner_full_name": "Owner",
            "password": "password123",
            "owner_email": f"owner-{suffix}@example.com",
        },
    )
    assert res.status_code == 201, res.text


async def test_register_login_refresh_me(client: AsyncClient):
    body = await register_shop_via_otp(client, shop_name="Phase1 Garage")
    phone = body["_test_phone"]
    slug = body["_test_slug"]
    email = body["_test_email"]

    assert body["role"] == "owner"
    assert body["phone"] == phone
    assert body["refresh_token"]
    assert body["access_token"]

    login = await client.post(
        "/v1/auth/login",
        json={"phone": phone, "password": "password123", "shop_slug": slug},
    )
    assert login.status_code == 200, login.text

    # Email remains a secondary login option
    login_email = await client.post(
        "/v1/auth/login",
        json={"email": email, "password": "password123", "shop_slug": slug},
    )
    assert login_email.status_code == 200, login_email.text

    refresh = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert refresh.status_code == 200, refresh.text
    new_access = refresh.json()["access_token"]

    me = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200
    assert me.json()["phone"] == phone
    assert me.json()["email"] == email
    assert me.json()["phone_verified"] is True
    assert me.json()["shop_slug"] == slug
    assert me.json()["role"] == "owner"

    reuse = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert reuse.status_code == 401


async def test_shop_isolation(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    a = await register_shop_via_otp(
        client,
        suffix=f"a{suffix[:6]}",
        shop_name="Shop A",
        shop_slug=f"shop-a-{suffix}",
        email=f"owner-a-{suffix}@example.com",
    )
    b = await register_shop_via_otp(
        client,
        suffix=f"b{suffix[:6]}",
        shop_name="Shop B",
        shop_slug=f"shop-b-{suffix}",
        email=f"owner-b-{suffix}@example.com",
    )
    assert a["shop_id"] != b["shop_id"]
    assert a["phone"] != b["phone"]


async def test_logout(client: AsyncClient):
    body = await register_shop_via_otp(client, shop_name="Logout Shop")
    refresh = body["refresh_token"]
    out = await client.post("/v1/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 204
    reuse = await client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert reuse.status_code == 401
