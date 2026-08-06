"""Voice AI unit tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.voice.factory import build_voice_runtime
from app.voice.models import InboundCallEvent, SpeechInput
from app.voice.runtime import reset_voice_runtime
from app.voice.store import InMemoryVoiceStore
from app.voice.twilio.provider import FakeVoiceProvider, VoiceTwilioSettings
from app.voice.twilio.streams import MediaStreamHub
from app.sms.queue import InMemoryMessageQueue


@pytest.fixture(autouse=True)
def _reset():
    reset_voice_runtime()
    yield
    reset_voice_runtime()


@pytest.fixture(autouse=True)
def _stub_ai_quota(monkeypatch: pytest.MonkeyPatch):
    """Unit tests use ephemeral shop UUIDs; skip DB-backed plan quota metering."""

    async def _noop_consume(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.saas.quotas.QuotaService.consume", _noop_consume)


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def runtime(shop_id):
    store = InMemoryVoiceStore()
    store.register_shop_number(shop_id, "+15550001111")
    provider = FakeVoiceProvider(
        VoiceTwilioSettings(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15550001111",
            validate_signature=False,
            barge_in=True,
        )
    )
    return build_voice_runtime(
        store=store,
        provider=provider,
        queue=InMemoryMessageQueue(),
        streams=MediaStreamHub(),
    )


@pytest.mark.asyncio
async def test_answer_and_book_appointment(runtime, shop_id):
    answered = await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAtest001",
            from_number="+15559870001",
            to_number="+15550001111",
        ),
    )
    assert answered.call.status == "in_progress"
    assert "Gather" in answered.twiml
    assert 'bargeIn="true"' in answered.twiml
    assert answered.assistant_turn is not None

    turn = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAtest001",
            speech_result="I need to book an appointment for an oil change",
        ),
    )
    assert turn.pipeline is not None
    assert turn.pipeline.stages["intent"].data.intent.value == "book_appointment"
    # Ask when they want to come — do not volunteer openings.
    assert turn.pipeline.stages["scheduling"].data.action == "list_slots"
    assert turn.pipeline.stages["scheduling"].data.message == "ask_preferred_time"
    assert turn.spoken_text
    assert "time" in turn.spoken_text.lower()
    assert "i've got" not in turn.spoken_text.lower()
    assert "Gather" in turn.twiml or "Dial" in turn.twiml

    completed = await runtime.service.complete_call(shop_id=shop_id, call_id=answered.call.id)
    assert completed.status == "completed"
    assert completed.transcript
    assert completed.call_summary
    assert completed.repair_notes is not None
    assert runtime.monitor.snapshot()["calls_started"] == 1
    assert runtime.monitor.snapshot()["calls_completed"] == 1


@pytest.mark.asyncio
async def test_voice_scopes_billing_quota_during_ai(runtime, shop_id, monkeypatch):
    """Plan-quota context (ai_calls / billing) must match the call's shop."""
    from app.saas.quota_context import get_quota_shop_id
    from app.saas.usage_tracking import get_usage_shop_id

    seen: dict[str, object] = {}

    original_speak = runtime.speech.speak

    async def _speak_tracking(**kwargs):
        seen["quota_shop"] = get_quota_shop_id()
        seen["usage_shop"] = get_usage_shop_id()
        return await original_speak(**kwargs)

    monkeypatch.setattr(runtime.speech, "speak", _speak_tracking)

    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAbill1",
            from_number="+15559870002",
            to_number="+15550001111",
        ),
    )
    assert seen.get("quota_shop") == shop_id
    assert seen.get("usage_shop") == shop_id

    await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAbill1",
            speech_result="I need an oil change tomorrow morning",
        ),
    )
    assert seen.get("quota_shop") == shop_id
    assert seen.get("usage_shop") == shop_id


@pytest.mark.asyncio
async def test_interrupt_and_memory(runtime, shop_id):
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAint1",
            from_number="+15551110001",
            to_number="+15550001111",
        ),
    )
    await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAint1",
            speech_result="How much for brakes?",
            interrupted=True,
        ),
    )
    call = await runtime.store.get_call_by_sid("CAint1")
    mem = await runtime.memory.load(
        shop_id=shop_id, call_id=call.id, caller_phone=call.caller_phone
    )
    assert any(t.interrupted for t in mem.turns if t.role == "caller")
    assert runtime.monitor.snapshot()["interrupts"] >= 1


@pytest.mark.asyncio
async def test_emergency_escalates_and_notifies_owner(runtime, shop_id):
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAem1",
            from_number="+15552220001",
            to_number="+15550001111",
        ),
    )
    result = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAem1",
            speech_result="This is an emergency — my car is smoking and I'm stranded",
        ),
    )
    assert result.call.escalate
    assert result.owner_notified
    assert "Dial" in result.twiml
    assert runtime.monitor.snapshot()["escalations"] >= 1
    assert runtime.monitor.snapshot()["owner_notifications"] >= 1


@pytest.mark.asyncio
async def test_multiple_simultaneous_calls(runtime, shop_id):
    for i in range(3):
        sid = f"CAmulti{i}"
        await runtime.service.answer_call(
            shop_id=shop_id,
            event=InboundCallEvent(
                call_sid=sid,
                from_number=f"+1555333000{i}",
                to_number="+15550001111",
            ),
        )
        await runtime.service.handle_speech(
            shop_id=shop_id,
            speech=SpeechInput(call_sid=sid, speech_result="When should I get an oil change?"),
        )
    live = await runtime.store.list_live_calls(shop_id)
    assert len(live) == 3


@pytest.mark.asyncio
async def test_human_takeover(runtime, shop_id):
    answered = await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAtake1",
            from_number="+15554440001",
            to_number="+15550001111",
        ),
    )
    await runtime.service.set_human_takeover(
        shop_id=shop_id, call_id=answered.call.id, enabled=True
    )
    result = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid="CAtake1", speech_result="Hello again"),
    )
    assert result.assistant_turn is None
    assert "Dial" in result.twiml


@pytest.mark.asyncio
async def test_recording_metadata(runtime, shop_id):
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CArec1",
            from_number="+15555550001",
            to_number="+15550001111",
        ),
    )
    call = await runtime.service.store_recording_metadata(
        call_sid="CArec1",
        recording_sid="RExxx",
        recording_url="https://api.twilio.com/recordings/RExxx",
        duration_sec=42,
    )
    assert call is not None
    assert call.recording_sid == "RExxx"
    assert call.recording_duration_sec == 42


@pytest.mark.asyncio
async def test_media_stream_events(runtime):
    hub = runtime.streams
    start = hub.handle_event(
        {
            "event": "start",
            "start": {"callSid": "CAstream1", "streamSid": "MZstream1"},
        }
    )
    assert start is not None and start.event_type == "start"
    media = hub.handle_event(
        {
            "event": "media",
            "streamSid": "MZstream1",
            "media": {"payload": "AAAA", "chunk": "1"},
        }
    )
    assert media is not None
    stop = hub.handle_event({"event": "stop", "streamSid": "MZstream1"})
    assert stop is not None and stop.event_type == "stop"
    assert "MZstream1" not in hub.sessions


@pytest.mark.asyncio
async def test_delete_call_removes_history_and_turns(runtime, shop_id):
    answered = await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAdelete001",
            from_number="+15559871111",
            to_number="+15550001111",
        ),
    )
    call_id = answered.call.id
    await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAdelete001",
            speech_result="What are your hours?",
        ),
    )
    assert len(await runtime.store.list_turns(shop_id, call_id)) >= 1

    await runtime.service.delete_call(shop_id=shop_id, call_id=call_id)

    assert await runtime.store.get_call(shop_id, call_id) is None
    assert await runtime.store.list_turns(shop_id, call_id) == []
    assert all(c.id != call_id for c in await runtime.store.list_calls(shop_id))


@pytest.mark.asyncio
async def test_delete_call_not_found(runtime, shop_id):
    with pytest.raises(ValueError, match="Call not found"):
        await runtime.service.delete_call(shop_id=shop_id, call_id=uuid4())


@pytest.mark.asyncio
async def test_speech_pipeline_tts(runtime):
    spoken = await runtime.speech.speak(text="Hello from the shop")
    assert spoken.text == "Hello from the shop"
    assert spoken.barge_in is True
    assert spoken.synthesis.audio_bytes
