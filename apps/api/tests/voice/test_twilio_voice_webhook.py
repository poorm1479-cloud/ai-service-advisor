"""Twilio Voice webhook HTTP tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.config import settings
from app.main import app
from app.voice.runtime import get_voice_runtime, reset_voice_runtime
from app.voice.store import InMemoryVoiceStore


@pytest.fixture(autouse=True)
def _voice_env(monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "voice_provider", "fake")
    monkeypatch.setattr(settings, "twilio_validate_signature", False)
    monkeypatch.setattr(settings, "twilio_from_number", "+15550001111")
    monkeypatch.setattr(settings, "voice_stream_enabled", True)
    monkeypatch.setattr(settings, "voice_store_backend", "memory")
    reset_voice_runtime()
    shop_id = uuid4()
    runtime = get_voice_runtime()
    if isinstance(runtime.store, InMemoryVoiceStore):
        runtime.store.register_shop_number(shop_id, "+15550001111")
    yield shop_id
    reset_voice_runtime()


@pytest.mark.asyncio
async def test_voice_answer_and_gather(_voice_env):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        answer = await client.post(
            "/v1/webhooks/twilio/voice",
            data={
                "CallSid": "CAwebhook1",
                "From": "+15551230000",
                "To": "+15550001111",
                "CallStatus": "ringing",
            },
        )
        assert answer.status_code == 200
        assert "Gather" in answer.text
        assert "Say" in answer.text
        # Blocking <Record> would make subsequent Say/Gather unreachable (silent calls).
        assert "<Record" not in answer.text

        gather = await client.post(
            "/v1/webhooks/twilio/voice/gather",
            data={
                "CallSid": "CAwebhook1",
                "SpeechResult": "Please book an appointment",
                "Confidence": "0.92",
            },
        )
        assert gather.status_code == 200
        assert "Response" in gather.text
        # Must not double-prefix the public base URL in Gather action
        assert "/voice/v1/webhooks/" not in gather.text

        status = await client.post(
            "/v1/webhooks/twilio/voice/status",
            data={"CallSid": "CAwebhook1", "CallStatus": "completed"},
        )
        assert status.status_code == 200

    runtime = get_voice_runtime()
    assert runtime.monitor.snapshot()["calls_started"] >= 1
    assert runtime.monitor.snapshot()["calls_completed"] >= 1
    call = await runtime.store.get_call_by_sid("CAwebhook1")
    assert call is not None
    assert call.ended_at is not None
    assert call.status == "completed"


@pytest.mark.asyncio
async def test_status_callback_marks_remote_hangup(_voice_env):
    """Remote hang-up via status webhook must leave the call non-live immediately."""
    shop_id = _voice_env
    runtime = get_voice_runtime()
    from app.voice.models import InboundCallEvent

    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAhangup1",
            from_number="+15551238888",
            to_number="+15550001111",
        ),
    )
    live_before = await runtime.store.list_live_calls(shop_id)
    assert any(c.twilio_call_sid == "CAhangup1" for c in live_before)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/webhooks/twilio/voice/status",
            data={"CallSid": "CAhangup1", "CallStatus": "completed"},
        )
    assert res.status_code == 200

    call = await runtime.store.get_call_by_sid("CAhangup1")
    assert call is not None
    assert call.ended_at is not None
    assert call.status == "completed"
    live_after = await runtime.store.list_live_calls(shop_id)
    assert not any(c.twilio_call_sid == "CAhangup1" for c in live_after)


@pytest.mark.asyncio
async def test_status_callback_idempotent(_voice_env):
    shop_id = _voice_env
    runtime = get_voice_runtime()
    from app.voice.models import InboundCallEvent

    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAidemp1",
            from_number="+15551237777",
            to_number="+15550001111",
        ),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(2):
            res = await client.post(
                "/v1/webhooks/twilio/voice/status",
                data={"CallSid": "CAidemp1", "CallStatus": "completed"},
            )
            assert res.status_code == 200
    assert runtime.monitor.snapshot()["calls_completed"] == 1


@pytest.mark.asyncio
async def test_gather_recovers_missing_call(_voice_env):
    """If store was wiped (reload) mid-call, gather must still return TwiML (not 404)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/webhooks/twilio/voice/gather",
            data={
                "CallSid": "CAorphaned1",
                "From": "+15551230000",
                "To": "+15550001111",
                "SpeechResult": "I need an oil change",
                "Confidence": "0.9",
            },
        )
    assert res.status_code == 200
    assert "Response" in res.text
    assert "Gather" in res.text or "Say" in res.text or "Hangup" in res.text
    runtime = get_voice_runtime()
    assert await runtime.store.get_call_by_sid("CAorphaned1") is not None


@pytest.mark.asyncio
async def test_voice_health(_voice_env):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/webhooks/twilio/voice/health")
    assert res.status_code == 200
    body = res.json()
    assert body["voice_enabled"] is True
    assert "metrics" in body


@pytest.mark.asyncio
async def test_recording_callback(_voice_env):
    transport = ASGITransport(app=app)
    runtime = get_voice_runtime()
    shop_id = _voice_env
    from app.voice.models import InboundCallEvent

    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CArecwebhook",
            from_number="+15559990000",
            to_number="+15550001111",
        ),
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/webhooks/twilio/voice/recording",
            data={
                "CallSid": "CArecwebhook",
                "RecordingSid": "RE123",
                "RecordingUrl": "https://api.twilio.com/RE123",
                "RecordingDuration": "15",
            },
        )
    assert res.status_code == 200
    call = await runtime.store.get_call_by_sid("CArecwebhook")
    assert call is not None
    assert call.recording_sid == "RE123"
