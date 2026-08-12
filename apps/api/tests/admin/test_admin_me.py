"""Admin self-service profile + password endpoints."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.enums import AccountType
from app.infrastructure.config import settings
from app.infrastructure.database import SessionLocal
from app.infrastructure.models import UserModel
from app.infrastructure.security import create_access_token, hash_password, verify_password
from app.main import app
from app.saas.rate_limit import admin_login_lockout


@pytest.fixture
def admin_username(monkeypatch: pytest.MonkeyPatch) -> str:
    username = f"padmin_{uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "platform_admin_usernames", username)
    return username


async def _seed_platform_admin(
    username: str,
    password: str = "AdminPass123!",
    *,
    full_name: str | None = None,
) -> str:
    user_id = uuid4()
    async with SessionLocal() as session:
        session.add(
            UserModel(
                id=user_id,
                username=username,
                phone=None,
                full_name=full_name or username,
                password_hash=hash_password(password),
                primary_auth_method="username",
                account_type=AccountType.PLATFORM_ADMIN.value,
            )
        )
        await session.commit()
    return str(user_id)


def _admin_headers(user_id: str, username: str) -> dict[str, str]:
    token = create_access_token(
        subject=user_id,
        shop_id=None,
        role="platform_admin",
        account_type="platform_admin",
        username=username,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_me_requires_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/admin/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_admin_me_get_and_name_immutable(admin_username: str) -> None:
    user_id = await _seed_platform_admin(admin_username, full_name="Original Admin")
    headers = _admin_headers(user_id, admin_username)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        get_res = await client.get("/v1/admin/me", headers=headers)
        assert get_res.status_code == 200
        body = get_res.json()
        assert body["username"] == admin_username
        assert body["full_name"] == "Original Admin"
        assert body["user_id"] == user_id

        patch_res = await client.patch(
            "/v1/admin/me",
            headers=headers,
            json={"full_name": "Updated Admin"},
        )
        assert patch_res.status_code == 403

        again = await client.get("/v1/admin/me", headers=headers)
        assert again.json()["full_name"] == "Original Admin"


@pytest.mark.asyncio
async def test_admin_me_rejects_name_change(admin_username: str) -> None:
    user_id = await _seed_platform_admin(admin_username)
    headers = _admin_headers(user_id, admin_username)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            "/v1/admin/me",
            headers=headers,
            json={"full_name": "Someone Else"},
        )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_change_password_roundtrip(admin_username: str) -> None:
    admin_login_lockout.reset()
    password = "AdminPass123!"
    new_password = "NewAdminPass456!"
    user_id = await _seed_platform_admin(admin_username, password)
    headers = _admin_headers(user_id, admin_username)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.post(
            "/v1/admin/me/password",
            headers=headers,
            json={"current_password": "wrong", "new_password": new_password},
        )
        assert bad.status_code == 400
        assert bad.json()["detail"] == "Current password is incorrect"

        same = await client.post(
            "/v1/admin/me/password",
            headers=headers,
            json={"current_password": password, "new_password": password},
        )
        assert same.status_code == 400

        ok = await client.post(
            "/v1/admin/me/password",
            headers=headers,
            json={"current_password": password, "new_password": new_password},
        )
        assert ok.status_code == 200
        assert ok.json() == {"ok": True}

        login = await client.post(
            "/v1/auth/admin/login",
            json={"username": admin_username, "password": new_password},
        )
        assert login.status_code == 200

    async with SessionLocal() as session:
        user = await session.get(UserModel, UUID(user_id))
        assert user is not None
        assert verify_password(new_password, user.password_hash)
