"""Remove/unassign must never call Twilio release (delete IncomingPhoneNumber)."""

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
async def test_admin_remove_never_calls_twilio_release(
    admin_username: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "twilio_auto_provision_numbers", True)
    monkeypatch.setattr(settings, "twilio_provider", "fake")

    release_calls: list[str] = []

    async def _boom_release(*, phone_e164: str | None) -> bool:
        release_calls.append(phone_e164 or "")
        raise AssertionError("release_shop_number must not run on Remove")

    monkeypatch.setattr(
        "app.telephony.numbers.release_shop_number",
        _boom_release,
    )
    monkeypatch.setattr(
        "app.admin.service.release_shop_number",
        _boom_release,
        raising=False,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        shop = await register_shop_via_otp(
            client, email=f"keep-twilio-{uuid4().hex[:10]}@example.com"
        )
        shop_id = shop["shop_id"]
        headers = _admin_headers(admin_username)

        phone = f"+1206555{uuid4().int % 10_000:04d}"
        # Ensure a clean assignable state.
        await client.delete(
            f"/v1/admin/organizations/{shop_id}/twilio-number",
            headers=headers,
        )
        assigned = await client.post(
            f"/v1/admin/organizations/{shop_id}/twilio-number",
            headers=headers,
            json={"phone_e164": phone},
        )
        assert assigned.status_code == 200, assigned.text

        removed = await client.delete(
            f"/v1/admin/organizations/{shop_id}/twilio-number",
            headers=headers,
        )
        assert removed.status_code == 200, removed.text
        body = removed.json()
        assert body["twilio_phone_e164"] is None
        assert body["released_from_provider"] is False
        assert body["kept_on_twilio"] is True
        assert body["action"] == "unassigned"
        assert release_calls == []
