"""Admin console API — JWT + platform allowlist gate + dashboard shape."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.config import settings
from app.infrastructure.security import create_access_token
from app.main import app
from tests.auth_helpers import register_shop_via_otp


@pytest.fixture
def admin_username(monkeypatch: pytest.MonkeyPatch) -> str:
    username = "platform_admin"
    monkeypatch.setattr(settings, "platform_admin_usernames", username)
    return username


# Back-compat alias for fixtures/tests that still name the allowlist "admin_email".
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
async def test_admin_requires_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/admin/dashboard")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_admin_rejects_non_allowlisted_user(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        other = await register_shop_via_otp(client, email="not-admin@example.com")
        res = await client.get(
            "/v1/admin/dashboard",
            headers={"Authorization": f"Bearer {other['access_token']}"},
        )
    assert res.status_code == 403
    assert res.json()["detail"] == "Platform admin required"


@pytest.mark.asyncio
async def test_admin_rejects_email_header_spoof(admin_username: str) -> None:
    """Legacy X-Platform-Admin-Email alone must not grant access."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/v1/admin/dashboard",
            headers={"X-Platform-Admin-Email": admin_username},
        )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_admin_dashboard_ok(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/admin/dashboard", headers=_admin_headers(admin_email))
    assert res.status_code == 200
    body = res.json()
    assert "shops" in body
    assert "users" in body
    assert "plans" in body
    assert "payments" in body
    assert "tokens" in body
    assert "sms" in body
    assert "voice" in body
    assert "system" in body


@pytest.mark.asyncio
async def test_admin_sections(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    paths = [
        "/v1/admin/organizations",
        "/v1/admin/billing",
        "/v1/admin/usage",
        "/v1/admin/users",
        "/v1/admin/system",
        "/v1/admin/notifications",
        "/v1/admin/settings",
        "/v1/platform/overview",
    ]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = _admin_headers(admin_email)
        for path in paths:
            res = await client.get(path, headers=headers)
            assert res.status_code == 200, path


@pytest.mark.asyncio
async def test_admin_organizations_shape(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/v1/admin/organizations",
            headers=_admin_headers(admin_email),
        )
    assert res.status_code == 200
    body = res.json()
    assert "shops" in body
    assert "enterprise_orgs" in body
    for shop in body["shops"]:
        assert "shop_id" in shop
        assert "shop_name" in shop
        assert "owner_name" in shop
        assert "last_activity_at" in shop
        assert "status" in shop
        assert "created_at" in shop


@pytest.mark.asyncio
async def test_admin_organization_detail_404(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/v1/admin/organizations/00000000-0000-0000-0000-000000000000",
            headers=_admin_headers(admin_email),
        )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_admin_organization_detail_actions(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        shop = await register_shop_via_otp(client, email="org-actions@example.com")
        shop_id = shop["shop_id"]
        user_id = shop["user_id"]
        headers = _admin_headers(admin_email)

        detail = await client.get(f"/v1/admin/organizations/{shop_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["shop"]["shop_id"] == shop_id
        assert "usage" in body
        assert "period" in body["usage"]
        assert "plans" in body
        assert isinstance(body["plans"], list)
        assert len(body["members"]) >= 1

        usage = await client.get(f"/v1/admin/organizations/{shop_id}/usage", headers=headers)
        assert usage.status_code == 200
        assert usage.json()["shop_id"] == shop_id

        plans = body["plans"]
        assert plans, "expected seeded plans"
        target_plan = next((p for p in plans if p["id"] != body["shop"]["plan_id"]), plans[0])
        plan_res = await client.post(
            f"/v1/admin/organizations/{shop_id}/plan",
            headers=headers,
            json={"plan_id": target_plan["id"]},
        )
        assert plan_res.status_code == 200, plan_res.text
        assert plan_res.json()["plan_id"] == target_plan["id"]

        reset = await client.post(
            f"/v1/admin/organizations/{shop_id}/members/{user_id}/password-reset",
            headers=headers,
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["ok"] is True

        init = await client.post(
            f"/v1/admin/organizations/{shop_id}/members/{user_id}/password-initialize",
            headers=headers,
            json={},
        )
        assert init.status_code == 200, init.text
        init_body = init.json()
        assert init_body["ok"] is True
        assert isinstance(init_body.get("temporary_password"), str)
        assert len(init_body["temporary_password"]) >= 8

        custom = await client.post(
            f"/v1/admin/organizations/{shop_id}/members/{user_id}/password-initialize",
            headers=headers,
            json={"new_password": "TempPass99!"},
        )
        assert custom.status_code == 200, custom.text
        assert custom.json()["temporary_password"] == "TempPass99!"

        suspend = await client.post(
            f"/v1/admin/organizations/{shop_id}/members/{user_id}/suspend",
            headers=headers,
        )
        assert suspend.status_code == 200, suspend.text
        assert suspend.json()["is_active"] is False

        activate = await client.post(
            f"/v1/admin/organizations/{shop_id}/members/{user_id}/activate",
            headers=headers,
        )
        assert activate.status_code == 200, activate.text
        assert activate.json()["is_active"] is True

        platform_suspend = await client.post(
            f"/v1/platform/shops/{shop_id}/suspend",
            headers=headers,
        )
        assert platform_suspend.status_code == 200, platform_suspend.text
        assert platform_suspend.json()["status"] == "suspended"


@pytest.mark.asyncio
async def test_admin_organization_twilio_number_lifecycle(
    admin_email: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "twilio_auto_provision_numbers", True)
    monkeypatch.setattr(settings, "twilio_provider", "fake")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        shop = await register_shop_via_otp(
            client, email=f"twilio-admin-{uuid4().hex[:10]}@example.com"
        )
        shop_id = shop["shop_id"]
        headers = _admin_headers(admin_email)

        # Clear any signup-provisioned number so assign path is testable end-to-end.
        existing = await client.get("/v1/tenant/shop", headers={
            "Authorization": f"Bearer {shop['access_token']}",
        })
        if existing.status_code == 200 and existing.json().get("sms_phone_e164"):
            cleared = await client.delete(
                f"/v1/admin/organizations/{shop_id}/twilio-number",
                headers=headers,
            )
            assert cleared.status_code == 200, cleared.text
            assert cleared.json()["twilio_phone_e164"] is None

        empty_delete = await client.delete(
            f"/v1/admin/organizations/{shop_id}/twilio-number",
            headers=headers,
        )
        assert empty_delete.status_code == 400

        assign = await client.post(
            f"/v1/admin/organizations/{shop_id}/twilio-number",
            headers=headers,
            json={},
        )
        assert assign.status_code == 200, assign.text
        assign_body = assign.json()
        assert assign_body["ok"] is True
        assert assign_body["twilio_phone_e164"]
        assert assign_body["sms_phone_e164"] == assign_body["voice_phone_e164"]
        first = assign_body["twilio_phone_e164"]

        # Already assigned → reject second auto-assign.
        again = await client.post(
            f"/v1/admin/organizations/{shop_id}/twilio-number",
            headers=headers,
            json={},
        )
        assert again.status_code == 400

        reset = await client.post(
            f"/v1/admin/organizations/{shop_id}/twilio-number/reset",
            headers=headers,
        )
        assert reset.status_code == 200, reset.text
        reset_body = reset.json()
        assert reset_body["ok"] is True
        assert reset_body["twilio_phone_e164"]
        assert reset_body["previous_twilio_phone_e164"] == first

        manual_phone = f"+1206555{uuid4().int % 10_000:04d}"
        # Manual assign while held → reject
        blocked = await client.post(
            f"/v1/admin/organizations/{shop_id}/twilio-number",
            headers=headers,
            json={"phone_e164": manual_phone},
        )
        assert blocked.status_code == 400

        deleted = await client.delete(
            f"/v1/admin/organizations/{shop_id}/twilio-number",
            headers=headers,
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["twilio_phone_e164"] is None
        assert deleted.json()["released_from_provider"] is False
        assert deleted.json()["kept_on_twilio"] is True
        assert deleted.json()["action"] == "unassigned"
        assert "webhooks_cleared" not in deleted.json() or deleted.json().get("webhooks_cleared") is None

        manual = await client.post(
            f"/v1/admin/organizations/{shop_id}/twilio-number",
            headers=headers,
            json={"phone_e164": manual_phone},
        )
        assert manual.status_code == 200, manual.text
        assert manual.json()["twilio_phone_e164"] == manual_phone
        assert manual.json()["provider"] == "manual"

        users = await client.get("/v1/admin/users", headers=headers)
        assert users.status_code == 200
        row = next(
            (u for u in users.json()["users"] if u["shop_id"] == shop_id),
            None,
        )
        assert row is not None
        assert row["twilio_phone_e164"] == manual_phone

        orgs = await client.get("/v1/admin/organizations", headers=headers)
        assert orgs.status_code == 200
        org_row = next(
            (s for s in orgs.json()["shops"] if s["shop_id"] == shop_id),
            None,
        )
        assert org_row is not None
        assert org_row["twilio_phone_e164"] == manual_phone
        assert org_row["sms_phone_e164"] == manual_phone
        assert org_row["voice_phone_e164"] == manual_phone


@pytest.mark.asyncio
async def test_admin_billing_shape(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/admin/billing", headers=_admin_headers(admin_email))
    assert res.status_code == 200
    body = res.json()
    assert "summary" in body
    assert "revenue_summary" in body
    assert "payment_status" in body
    assert "by_status" in body["payment_status"]
    assert "active_plans" in body
    assert "subscriptions" in body
    assert "failed_payments" in body
    assert "plans" in body
    assert "payments" in body
    rev = body["revenue_summary"]
    for key in (
        "subscriptions",
        "paid_active",
        "trialing",
        "active",
        "failed_payments",
        "with_stripe",
        "mrr_cents",
        "arr_cents",
    ):
        assert key in rev
    assert rev["arr_cents"] == rev["mrr_cents"] * 12
