"""Twilio webhook HTTP tests (ASGI, fake provider)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.config import settings
from app.main import app
from app.sms.runtime import get_sms_runtime, reset_sms_runtime
from app.sms.store import InMemorySmsStore


@pytest.fixture(autouse=True)
def _sms_env(monkeypatch):
    monkeypatch.setattr(settings, "sms_enabled", True)
    monkeypatch.setattr(settings, "twilio_provider", "fake")
    monkeypatch.setattr(settings, "twilio_validate_signature", False)
    monkeypatch.setattr(settings, "twilio_from_number", "+15550001111")

    async def _noop_consume(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.saas.quotas.QuotaService.consume", _noop_consume)
    reset_sms_runtime()
    shop_id = uuid4()
    runtime = get_sms_runtime()
    if isinstance(runtime.store, InMemorySmsStore):
        runtime.store.register_shop_number(shop_id, "+15550001111")
    yield shop_id
    reset_sms_runtime()


@pytest.mark.asyncio
async def test_twilio_webhook_accepts_form(_sms_env):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/webhooks/twilio/sms",
            data={
                "From": "+15551230000",
                "To": "+15550001111",
                "Body": "I need to book an appointment",
                "MessageSid": "SMwebhook1",
                "AccountSid": "ACtest",
            },
        )
    assert res.status_code == 200
    assert "Response" in res.text

    runtime = get_sms_runtime()
    assert runtime.monitor.snapshot()["inbound_received"] >= 1


@pytest.mark.asyncio
async def test_twilio_webhook_health(_sms_env):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/webhooks/twilio/health")
    assert res.status_code == 200
    body = res.json()
    assert body["sms_enabled"] is True
    assert "metrics" in body
