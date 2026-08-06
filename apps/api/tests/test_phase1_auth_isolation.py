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
    body = await register_shop_via_otp(client, shop_name=f"Phase1 Garage {uuid.uuid4().hex[:6]}")
    phone = body["_test_phone"]
    slug = body["_test_slug"]
    email = body["_test_email"]
    shop_name = body["_test_shop_name"]

    assert body["role"] == "owner"
    assert body["phone"] == phone
    assert body["refresh_token"]
    assert body["access_token"]
    assert body["shop_slug"] == slug
    assert slug  # auto-generated from name

    login = await client.post(
        "/v1/auth/login",
        json={"phone": phone, "password": "password123", "shop_name": shop_name},
    )
    assert login.status_code == 200, login.text

    # Email remains a secondary login option; legacy shop_slug still accepted
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
    assert me.json()["shop_name"] == shop_name
    assert me.json()["role"] == "owner"

    reuse = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert reuse.status_code == 401


async def test_register_rejects_duplicate_shop_slug(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    slug = f"taken-slug-{suffix}"
    first = await register_shop_via_otp(
        client,
        shop_name=f"First Garage {suffix}",
        shop_slug=slug,
        email=f"first-{suffix}@example.com",
    )
    assert first["shop_slug"] == slug

    # Same preferred slug, different shop name → 409
    res = await client.post(
        "/v1/auth/register",
        json={
            "shop_name": f"Second Garage {suffix}",
            "shop_slug": slug,
            "auth_method": "phone",
            "owner_phone": f"+1555{int(suffix[:7], 16) % 10_000_000:07d}",
            "owner_full_name": "Other Owner",
            "password": "password123",
            "owner_email": f"second-{suffix}@example.com",
        },
    )
    assert res.status_code == 409, res.text
    assert "slug" in res.json()["detail"].lower()


async def test_register_auto_suffixes_colliding_name_slug(client: AsyncClient):
    """Different display names that slugify to the same base get unique slugs."""
    suffix = uuid.uuid4().hex[:8]
    first = await register_shop_via_otp(
        client,
        shop_name=f"Acme Auto {suffix}",
        email=f"slug-a-{suffix}@example.com",
    )
    base = first["shop_slug"]
    assert base  # e.g. acme-auto-<suffix>

    # Extra punctuation collapses to the same slugify base as the first name.
    res = await client.post(
        "/v1/auth/register",
        json={
            "shop_name": f"Acme  Auto!! {suffix}",
            "auth_method": "phone",
            "owner_phone": f"+1556{int(suffix[:7], 16) % 10_000_000:07d}",
            "owner_full_name": "Other Owner",
            "password": "password123",
            "owner_email": f"slug-b-{suffix}@example.com",
        },
    )
    assert res.status_code == 201, res.text
    second_slug = res.json()["shop_slug"]
    assert second_slug != base
    assert second_slug == f"{base}-2" or second_slug.startswith(f"{base}-")


async def test_register_rejects_duplicate_shop_name(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    name = f"Unique Name Garage {suffix}"
    await register_shop_via_otp(
        client,
        shop_name=name,
        email=f"name-a-{suffix}@example.com",
    )
    res = await client.post(
        "/v1/auth/register",
        json={
            "shop_name": name,
            "auth_method": "phone",
            "owner_phone": f"+1556{int(suffix[:7], 16) % 10_000_000:07d}",
            "owner_full_name": "Other Owner",
            "password": "password123",
            "owner_email": f"name-b-{suffix}@example.com",
        },
    )
    assert res.status_code == 409, res.text
    assert "name" in res.json()["detail"].lower()


async def test_shop_isolation(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    a = await register_shop_via_otp(
        client,
        suffix=f"a{suffix[:6]}",
        shop_name=f"Shop A {suffix}",
        shop_slug=f"shop-a-{suffix}",
        email=f"owner-a-{suffix}@example.com",
    )
    b = await register_shop_via_otp(
        client,
        suffix=f"b{suffix[:6]}",
        shop_name=f"Shop B {suffix}",
        shop_slug=f"shop-b-{suffix}",
        email=f"owner-b-{suffix}@example.com",
    )
    assert a["shop_id"] != b["shop_id"]
    assert a["phone"] != b["phone"]


async def test_logout(client: AsyncClient):
    body = await register_shop_via_otp(client, shop_name=f"Logout Shop {uuid.uuid4().hex[:6]}")
    refresh = body["refresh_token"]
    out = await client.post("/v1/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 204
    reuse = await client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert reuse.status_code == 401
