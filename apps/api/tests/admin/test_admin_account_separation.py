"""Platform admin accounts are separate from shop registrants."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.domain.enums import AccountType
from app.infrastructure.config import settings
from app.infrastructure.database import SessionLocal
from app.infrastructure.models import ShopMembershipModel, ShopModel, UserModel
from app.infrastructure.security import hash_password
from app.main import app
from tests.auth_helpers import register_shop_via_otp


@pytest.fixture
def admin_username(monkeypatch: pytest.MonkeyPatch) -> str:
    username = f"padmin_{uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "platform_admin_usernames", username)
    return username


async def _seed_platform_admin(
    username: str,
    password: str = "AdminPass123!",
    *,
    phone: str | None = None,
) -> None:
    async with SessionLocal() as session:
        session.add(
            UserModel(
                id=uuid4(),
                username=username,
                phone=phone,
                full_name=username,
                password_hash=hash_password(password),
                primary_auth_method="username",
                account_type=AccountType.PLATFORM_ADMIN.value,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_shop_register_creates_shop_account_not_admin(admin_username: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        shop = await register_shop_via_otp(client, shop_name="Separation Garage")
        assert shop["account_type"] == AccountType.SHOP.value
        assert shop["shop_id"] is not None
        assert shop["role"] == "owner"

    async with SessionLocal() as session:
        user = await session.scalar(select(UserModel).where(UserModel.phone == shop["_test_phone"]))
        assert user is not None
        assert user.account_type == AccountType.SHOP.value
        assert (user.username or "") != admin_username


@pytest.mark.asyncio
async def test_shop_login_rejects_platform_admin(admin_username: str) -> None:
    password = "AdminPass123!"
    phone = f"+1555{uuid4().int % 10_000_000:07d}"
    await _seed_platform_admin(admin_username, password, phone=phone)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/auth/login",
            json={"phone": phone, "password": password, "shop_slug": "any-shop"},
        )
    assert res.status_code == 401
    assert "admin sign-in" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_login_rejects_shop_user(admin_username: str) -> None:
    from app.saas.rate_limit import admin_login_lockout

    admin_login_lockout.reset()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_shop_via_otp(client)
        res = await client.post(
            "/v1/auth/admin/login",
            json={
                "username": f"shop_{uuid4().hex[:8]}",
                "password": "password123",
            },
        )
    assert res.status_code == 401
    assert res.json()["detail"] == "Login failed"


@pytest.mark.asyncio
async def test_admin_login_lockout_after_three_failures(admin_username: str) -> None:
    from app.saas.rate_limit import admin_login_lockout

    admin_login_lockout.reset()
    password = "AdminPass123!"
    await _seed_platform_admin(admin_username, password)
    transport = ASGITransport(app=app)
    payload = {"username": admin_username, "password": "wrong-password"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(2):
            res = await client.post("/v1/auth/admin/login", json=payload)
            assert res.status_code == 401
            assert res.json()["detail"] == "Login failed"

        res = await client.post("/v1/auth/admin/login", json=payload)
        assert res.status_code == 429
        detail = res.json()["detail"]
        assert detail["message"] == "Too many failed attempts. Try again later."
        assert 590 <= detail["retry_after"] <= 600
        assert res.headers.get("Retry-After") == str(detail["retry_after"])

        res = await client.post(
            "/v1/auth/admin/login",
            json={"username": admin_username, "password": password},
        )
        assert res.status_code == 429
        detail = res.json()["detail"]
        assert detail["message"] == "Too many failed attempts. Try again later."
        assert detail["retry_after"] > 0


@pytest.mark.asyncio
async def test_admin_login_ok_without_shop(admin_username: str) -> None:
    from app.saas.rate_limit import admin_login_lockout

    admin_login_lockout.reset()
    password = "AdminPass123!"
    await _seed_platform_admin(admin_username, password)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/auth/admin/login",
            json={"username": admin_username, "password": password},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["account_type"] == AccountType.PLATFORM_ADMIN.value
        assert body["role"] == AccountType.PLATFORM_ADMIN.value
        assert body["shop_id"] is None
        assert body["access_token"]

        me = await client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert me.status_code == 403

        dash = await client.get(
            "/v1/admin/system",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert dash.status_code == 200

    async with SessionLocal() as session:
        user = await session.scalar(select(UserModel).where(UserModel.username == admin_username))
        assert user is not None
        assert user.account_type == AccountType.PLATFORM_ADMIN.value
        memberships = (
            await session.scalars(
                select(ShopMembershipModel).where(ShopMembershipModel.user_id == user.id)
            )
        ).all()
        assert memberships == []
        shops = (
            await session.scalars(select(ShopModel).where(ShopModel.slug == admin_username.replace("_", "-")))
        ).all()
        assert shops == []
