"""Twilio number auto-provisioning on shop signup."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.telephony.numbers import (
    FakeNumberProvisioner,
    TwilioNumberProvisioner,
    provision_shop_number,
    release_shop_number,
)

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


@pytest.mark.asyncio
async def test_fake_provisioner_assigns_unique_e164():
    shop_a = uuid4()
    shop_b = uuid4()
    a = await FakeNumberProvisioner().provision(shop_id=shop_a, friendly_name="A")
    b = await FakeNumberProvisioner().provision(shop_id=shop_b, friendly_name="B")
    assert a.phone_e164.startswith("+1800")
    assert b.phone_e164.startswith("+1800")
    assert a.phone_e164 != b.phone_e164
    assert a.provider == "fake"
    # deterministic per shop
    a2 = await FakeNumberProvisioner().provision(shop_id=shop_a, friendly_name="A")
    assert a2.phone_e164 == a.phone_e164


@pytest.mark.asyncio
async def test_provision_disabled_returns_none(monkeypatch):
    from app.admin.settings import PlatformSettingsService

    async def _disabled(self) -> bool:
        return False

    monkeypatch.setattr(
        PlatformSettingsService,
        "twilio_auto_provision_numbers",
        _disabled,
    )
    result = await provision_shop_number(shop_id=uuid4(), shop_name="Disabled")
    assert result is None


@pytest.mark.asyncio
async def test_provision_respects_platform_setting_override(monkeypatch, require_db):
    """Admin DB toggle wins over env default for signup auto-provision."""
    from app.admin.settings import EditableSettingsPatch, PlatformSettingsService
    from app.infrastructure import config as cfg

    monkeypatch.setattr(cfg.settings, "twilio_provider", "fake")
    svc = PlatformSettingsService()
    await svc.patch(
        EditableSettingsPatch(twilio_auto_provision_numbers=False),
        updated_by="test",
    )
    try:
        result = await provision_shop_number(shop_id=uuid4(), shop_name="OverrideOff")
        assert result is None
        forced = await provision_shop_number(
            shop_id=uuid4(), shop_name="ForceStillWorks", force=True
        )
        assert forced is not None
        assert forced.phone_e164.startswith("+1800")
    finally:
        await svc.patch(
            EditableSettingsPatch(twilio_auto_provision_numbers=True),
            updated_by="test",
        )


@pytest.mark.asyncio
async def test_fake_release_shop_number(monkeypatch):
    from app.infrastructure import config as cfg
    from app.telephony.numbers import release_shop_number

    monkeypatch.setattr(cfg.settings, "twilio_provider", "fake")
    assert await release_shop_number(phone_e164="+18001234567") is True
    assert await release_shop_number(phone_e164=None) is False
    assert await release_shop_number(phone_e164="") is False


@pytest.mark.asyncio
async def test_fake_provisioner_randomize_differs():
    shop = uuid4()
    a = await FakeNumberProvisioner(randomize=True).provision(shop_id=shop, friendly_name="A")
    b = await FakeNumberProvisioner(randomize=True).provision(shop_id=shop, friendly_name="B")
    # High chance of distinct; if collision re-roll once in rare case
    if a.phone_e164 == b.phone_e164:
        b = await FakeNumberProvisioner(randomize=True).provision(shop_id=shop, friendly_name="B2")
    assert a.phone_e164.startswith("+1800")
    assert b.phone_e164.startswith("+1800")


@pytest.mark.asyncio
async def test_twilio_provisioner_search_and_purchase(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class _Resp:
        def __init__(self, payload: dict, status: int = 200) -> None:
            self._payload = payload
            self.status_code = status

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self) -> dict:
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url: str, params=None):
            calls.append(("GET", {"url": url, "params": params}))
            if "AvailablePhoneNumbers" in url:
                return _Resp(
                    {"available_phone_numbers": [{"phone_number": "+12065550199"}]}
                )
            # Owned inventory empty → must purchase
            return _Resp({"incoming_phone_numbers": []})

        async def post(self, url: str, data=None):
            calls.append(("POST", {"url": url, "data": data}))
            return _Resp(
                {"sid": "PN123", "phone_number": "+12065550199"},
                status=201,
            )

    async def _no_assigned() -> set[str]:
        return set()

    monkeypatch.setattr("app.telephony.numbers.httpx.AsyncClient", _Client)
    monkeypatch.setattr("app.telephony.numbers.assigned_shop_phones", _no_assigned)

    provisioner = TwilioNumberProvisioner(
        account_sid="ACtest",
        auth_token="token",
        country="US",
        area_code="206",
        webhook_base_url="https://example.com",
    )
    result = await provisioner.provision(shop_id=uuid4(), friendly_name="Test Shop")
    assert result.phone_e164 == "+12065550199"
    assert result.sid == "PN123"
    assert result.provider == "twilio"
    assert any(c[0] == "GET" for c in calls)
    post = next(
        c
        for c in calls
        if c[0] == "POST" and str(c[1]["url"]).endswith("/IncomingPhoneNumbers.json")
    )
    data = post[1]["data"]
    assert data["PhoneNumber"] == "+12065550199"
    assert data["SmsUrl"] == "https://example.com/v1/webhooks/twilio/sms"
    assert data["VoiceUrl"] == "https://example.com/v1/webhooks/twilio/voice"
    assert "StatusCallback" in data


@pytest.mark.asyncio
async def test_twilio_provisioner_reuses_idle_owned_number(monkeypatch):
    """Prefer account-owned idle numbers over purchasing."""
    calls: list[tuple[str, dict]] = []

    class _Resp:
        def __init__(self, payload: dict, status: int = 200) -> None:
            self._payload = payload
            self.status_code = status

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self) -> dict:
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url: str, params=None):
            calls.append(("GET", {"url": url, "params": params}))
            assert "AvailablePhoneNumbers" not in url
            return _Resp(
                {
                    "incoming_phone_numbers": [
                        {
                            "sid": "PNidle",
                            "phone_number": "+12065550111",
                            "capabilities": {"sms": True, "voice": True},
                        }
                    ]
                }
            )

        async def post(self, url: str, data=None):
            calls.append(("POST", {"url": url, "data": data}))
            assert "/IncomingPhoneNumbers/PNidle.json" in url
            assert "PhoneNumber" not in (data or {})
            return _Resp(
                {"sid": "PNidle", "phone_number": "+12065550111"},
                status=200,
            )

    async def _no_assigned() -> set[str]:
        return set()

    monkeypatch.setattr("app.telephony.numbers.httpx.AsyncClient", _Client)
    monkeypatch.setattr("app.telephony.numbers.assigned_shop_phones", _no_assigned)

    provisioner = TwilioNumberProvisioner(
        account_sid="ACtest",
        auth_token="token",
        country="US",
        webhook_base_url="https://example.com",
    )
    result = await provisioner.provision(shop_id=uuid4(), friendly_name="Reuse Shop")
    assert result.phone_e164 == "+12065550111"
    assert result.sid == "PNidle"
    assert not any("AvailablePhoneNumbers" in str(c[1].get("url")) for c in calls)
    post = next(c for c in calls if c[0] == "POST")
    assert post[1]["data"]["FriendlyName"] == "Reuse Shop"
    assert post[1]["data"]["SmsUrl"] == "https://example.com/v1/webhooks/twilio/sms"


@pytest.mark.asyncio
async def test_twilio_provisioner_skips_assigned_and_buys(monkeypatch):
    """Numbers already assigned to shops must not be reused."""
    calls: list[tuple[str, dict]] = []

    class _Resp:
        def __init__(self, payload: dict, status: int = 200) -> None:
            self._payload = payload
            self.status_code = status

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self) -> dict:
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url: str, params=None):
            calls.append(("GET", {"url": url, "params": params}))
            if "AvailablePhoneNumbers" in url:
                return _Resp(
                    {"available_phone_numbers": [{"phone_number": "+12065550999"}]}
                )
            return _Resp(
                {
                    "incoming_phone_numbers": [
                        {
                            "sid": "PNtaken",
                            "phone_number": "+12065550111",
                            "capabilities": {"sms": True, "voice": True},
                        }
                    ]
                }
            )

        async def post(self, url: str, data=None):
            calls.append(("POST", {"url": url, "data": data}))
            return _Resp(
                {"sid": "PNnew", "phone_number": "+12065550999"},
                status=201,
            )

    async def _assigned() -> set[str]:
        return {"+12065550111"}

    monkeypatch.setattr("app.telephony.numbers.httpx.AsyncClient", _Client)
    monkeypatch.setattr("app.telephony.numbers.assigned_shop_phones", _assigned)

    provisioner = TwilioNumberProvisioner(
        account_sid="ACtest",
        auth_token="token",
        country="US",
        webhook_base_url="https://example.com",
    )
    result = await provisioner.provision(shop_id=uuid4(), friendly_name="New Shop")
    assert result.phone_e164 == "+12065550999"
    assert result.sid == "PNnew"
    purchase = next(
        c
        for c in calls
        if c[0] == "POST" and str(c[1]["url"]).endswith("/IncomingPhoneNumbers.json")
    )
    assert purchase[1]["data"]["PhoneNumber"] == "+12065550999"
    # Must not POST update to the taken SID
    assert not any("PNtaken" in str(c[1].get("url")) for c in calls if c[0] == "POST")


@pytest.mark.asyncio
async def test_register_assigns_shop_channel_phone(client, monkeypatch):
    from tests.auth_helpers import register_shop_via_otp

    from app.infrastructure import config as cfg

    monkeypatch.setattr(cfg.settings, "twilio_auto_provision_numbers", True)
    monkeypatch.setattr(cfg.settings, "twilio_provider", "fake")

    auth = await register_shop_via_otp(client, shop_name=f"Provision Garage {uuid4().hex[:8]}")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    res = await client.get("/v1/tenant/shop", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sms_phone_e164"]
    assert body["sms_phone_e164"].startswith("+1800")
    assert body["voice_phone_e164"] == body["sms_phone_e164"]
