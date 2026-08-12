"""Admin platform settings GET/PATCH + dashboard stream smoke."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.config import settings
from app.infrastructure.security import create_access_token
from app.main import app


@pytest.fixture
def admin_username(monkeypatch: pytest.MonkeyPatch) -> str:
    username = "platform_admin"
    monkeypatch.setattr(settings, "platform_admin_usernames", username)
    return username


@pytest.fixture
def admin_email(admin_username: str) -> str:
    return admin_username


def _admin_headers(username: str) -> dict[str, str]:
    token = create_access_token(
        subject=str(uuid4()),
        shop_id=None,
        role="platform_admin",
        account_type="platform_admin",
        username=username,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_settings_requires_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/admin/settings")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_admin_settings_get_defaults(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    headers = _admin_headers(admin_email)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Normalize shared DB state before asserting defaults.
        await client.patch(
            "/v1/admin/settings",
            headers=headers,
            json={
                "dashboard_poll_seconds": 3,
                "notification_retention_days": 90,
                "toast_enabled": True,
                "maintenance_mode": False,
                "twilio_auto_provision_numbers": True,
                "openai_enabled": True,
            },
        )
        res = await client.get("/v1/admin/settings", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert "editable" in body
    assert "env_snapshot" in body
    editable = body["editable"]
    assert editable["dashboard_poll_seconds"] == 3
    assert editable["notification_retention_days"] == 90
    assert editable["toast_enabled"] is True
    assert editable["maintenance_mode"] is False
    assert editable["twilio_auto_provision_numbers"] is True
    assert editable["openai_enabled"] is True
    env = body["env_snapshot"]
    assert "environment" in env
    assert "ai_provider" in env
    assert "platform_admin_usernames" in env
    assert "openai_api_key" not in env
    assert "platform_admin_bootstrap_password" not in env
    assert "jwt_secret" not in env


@pytest.mark.asyncio
async def test_admin_settings_patch_roundtrip(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    headers = _admin_headers(admin_email)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        patch = await client.patch(
            "/v1/admin/settings",
            headers=headers,
            json={
                "dashboard_poll_seconds": 5,
                "notification_retention_days": 30,
                "toast_enabled": False,
                "maintenance_mode": True,
                "twilio_auto_provision_numbers": False,
                "openai_enabled": False,
            },
        )
        assert patch.status_code == 200, patch.text
        body = patch.json()
        assert body["editable"]["dashboard_poll_seconds"] == 5
        assert body["editable"]["notification_retention_days"] == 30
        assert body["editable"]["toast_enabled"] is False
        assert body["editable"]["maintenance_mode"] is True
        assert body["editable"]["twilio_auto_provision_numbers"] is False
        assert body["editable"]["openai_enabled"] is False
        assert body["updated_at"] is not None

        get = await client.get("/v1/admin/settings", headers=headers)
        assert get.status_code == 200
        again = get.json()["editable"]
        assert again["dashboard_poll_seconds"] == 5
        assert again["toast_enabled"] is False
        assert again["twilio_auto_provision_numbers"] is False
        assert again["openai_enabled"] is False

        # restore defaults for other tests sharing DB
        await client.patch(
            "/v1/admin/settings",
            headers=headers,
            json={
                "dashboard_poll_seconds": 3,
                "notification_retention_days": 90,
                "toast_enabled": True,
                "maintenance_mode": False,
                "twilio_auto_provision_numbers": True,
                "openai_enabled": True,
            },
        )


@pytest.mark.asyncio
async def test_admin_settings_rejects_out_of_range(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            "/v1/admin/settings",
            headers=_admin_headers(admin_email),
            json={"dashboard_poll_seconds": 1},
        )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_admin_dashboard_stream_requires_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/admin/dashboard/stream")
    assert res.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/v1/admin/organizations/stream",
        "/v1/admin/users/stream",
        "/v1/admin/billing/stream",
        "/v1/admin/usage/stream",
        "/v1/admin/system/stream",
        "/v1/admin/settings/stream",
    ],
)
async def test_admin_resource_streams_require_auth(path: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(path)
    assert res.status_code == 401


def test_dashboard_fingerprint_stable_for_kpis() -> None:
    from app.admin.service import AdminConsoleService

    svc = AdminConsoleService()
    base = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "environment": "test",
        "system": {"status": "ready"},
        "shops": {"total": 2, "suspended": 0, "by_status": {"active": 2}},
        "users": {"total": 5, "active": 4, "memberships": 5},
        "payments": {"mrr_cents": 1000, "with_stripe": 1},
        "tokens": {"ai_calls": 10, "period": "2026-08"},
        "sms": {"inbound_received": 1, "outbound_sent": 2},
        "voice": {"calls_started": 3, "live_calls": 0},
        "incidents": {"open": 0, "total": 1},
        "plans": {"total": 2},
    }
    a = svc.dashboard_fingerprint(base)
    shifted = {**base, "generated_at": "2026-01-02T00:00:00+00:00"}
    assert svc.dashboard_fingerprint(shifted) == a
    changed = {**base, "shops": {**base["shops"], "total": 3}}
    assert svc.dashboard_fingerprint(changed) != a


def test_resource_fingerprint_ignores_generated_at() -> None:
    from app.admin.service import AdminConsoleService

    svc = AdminConsoleService()
    base = {"generated_at": "2026-01-01T00:00:00+00:00", "total": 2, "name": "a"}
    a = svc.resource_fingerprint(base)
    assert svc.resource_fingerprint({**base, "generated_at": "2026-01-02T00:00:00+00:00"}) == a
    assert svc.resource_fingerprint({**base, "total": 3}) != a
