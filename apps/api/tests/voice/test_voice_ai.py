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
async def test_voice_day_then_time_pinpoint_before_confirm(runtime, shop_id):
    """Date-only → ask time; time follow-up merges to a full preferred slot."""
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAdaytime1",
            from_number="+15559870011",
            to_number="+15550001111",
        ),
    )
    day_turn = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAdaytime1",
            speech_result="I need an oil change on Friday",
        ),
    )
    assert day_turn.spoken_text
    spoken_day = day_turn.spoken_text.lower()
    assert "time" in spoken_day
    assert "i've got" not in spoken_day
    # Should acknowledge the day and only ask for time
    assert "day and time" not in spoken_day
    intent1 = day_turn.pipeline.stages["intent"].data.entities
    assert intent1.get("needs_time") is True

    mem = await runtime.memory.load(
        shop_id=shop_id,
        call_id=day_turn.call.id,
        caller_phone="+15559870011",
    )
    assert mem.pending_needs_time is True
    assert mem.pending_preferred_start

    time_turn = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAdaytime1",
            speech_result="3pm",
        ),
    )
    intent2 = time_turn.pipeline.stages["intent"].data.entities
    assert intent2.get("needs_time") is not True
    assert intent2.get("needs_date") is not True
    assert intent2.get("time_precision") == "clock"
    preferred = intent2.get("preferred_start")
    assert preferred
    from datetime import datetime

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

    dt = datetime.fromisoformat(str(preferred).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        local = dt.replace(tzinfo=DEFAULT_SHOP_TZ)
    else:
        local = dt.astimezone(DEFAULT_SHOP_TZ)
    assert local.weekday() == 4  # Friday
    assert local.hour == 15
    spoken = (time_turn.spoken_text or "").lower()
    # Should not ask for more date/time half; either confirm, name, or unavailable
    assert "what day works" not in spoken
    assert "what time works" not in spoken


@pytest.mark.asyncio
async def test_voice_time_then_day_pinpoint_before_confirm(runtime, shop_id):
    """Time-only → ask day; day follow-up merges to a full preferred slot."""
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAtimeday1",
            from_number="+15559870012",
            to_number="+15550001111",
        ),
    )
    await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAtimeday1",
            speech_result="I need an oil change",
        ),
    )
    time_turn = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAtimeday1",
            speech_result="2pm",
        ),
    )
    spoken_time = (time_turn.spoken_text or "").lower()
    assert "day" in spoken_time
    assert "day and time" not in spoken_time
    intent1 = time_turn.pipeline.stages["intent"].data.entities
    assert intent1.get("needs_date") is True

    day_turn = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAtimeday1",
            speech_result="Friday",
        ),
    )
    intent2 = day_turn.pipeline.stages["intent"].data.entities
    assert intent2.get("needs_date") is not True
    assert intent2.get("needs_time") is not True
    assert intent2.get("time_precision") == "clock"
    spoken = (day_turn.spoken_text or "").lower()
    assert "what day works" not in spoken
    assert "what time works" not in spoken


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
    # Soft-delete: row remains so dashboard "AI calls handled" does not shrink.
    kept = runtime.store.calls.get(call_id)
    assert kept is not None
    assert kept.deleted_at is not None
    assert call_id in runtime.store.turns  # transcript retained for audit/metrics


@pytest.mark.asyncio
async def test_empty_speech_keeps_line_open_silently(runtime, shop_id):
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAsilent1",
            from_number="+15556660001",
            to_number="+15550001111",
        ),
    )
    first = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid="CAsilent1", speech_result=""),
    )
    assert "Gather" in first.twiml
    assert "Hangup" not in first.twiml
    assert "<Say" not in first.twiml  # silent re-listen

    second = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid="CAsilent1", speech_result=""),
    )
    assert "Gather" in second.twiml
    assert "still here" in second.spoken_text.lower()


@pytest.mark.asyncio
async def test_caller_farewell_hangs_up(runtime, shop_id):
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAbye1",
            from_number="+15556660002",
            to_number="+15550001111",
        ),
    )
    mid = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAbye1",
            speech_result="I need to book an appointment for an oil change",
        ),
    )
    assert "Hangup" not in mid.twiml
    assert mid.call.status == "in_progress"

    result = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid="CAbye1", speech_result="that's all"),
    )
    assert "Hangup" in result.twiml
    assert result.reply.end_call is True
    call = await runtime.store.get_call_by_sid("CAbye1")
    assert call is not None
    assert call.status == "completed"


@pytest.mark.asyncio
async def test_soft_no_after_anything_else_ends_call(runtime, shop_id):
    """After an open offer, declining must farewell — never re-ask for more work."""
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAbye2",
            from_number="+15556660003",
            to_number="+15550001111",
        ),
    )
    call = await runtime.store.get_call_by_sid("CAbye2")
    assert call is not None
    await runtime.memory.update_state(
        shop_id=shop_id,
        call_id=call.id,
        pending_question="Anything else I can help with?",
    )
    # Seed assistant offer into turns so last-assistant fallback also works.
    from app.voice.enums import VoiceTurnRole
    from app.voice.models import VoiceTurn
    from uuid import uuid4
    from datetime import datetime, timezone

    offer = VoiceTurn(
        id=uuid4(),
        call_id=call.id,
        shop_id=shop_id,
        role=VoiceTurnRole.ASSISTANT.value,
        text="You're booked for an oil change. Anything else I can help with?",
        created_at=datetime.now(timezone.utc),
    )
    await runtime.memory.append(shop_id=shop_id, call_id=call.id, turn=offer)

    result = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid="CAbye2", speech_result="No, thank you"),
    )
    assert result.reply.end_call is True
    assert "Hangup" in result.twiml
    assert "anything else" not in result.spoken_text.lower()
    assert "take care" in result.spoken_text.lower()
    done = await runtime.store.get_call_by_sid("CAbye2")
    assert done is not None
    assert done.status == "completed"


@pytest.mark.asyncio
async def test_off_topic_speech_redirects_to_vehicle_service(runtime, shop_id):
    """Unrelated chatter should kindly steer back to shop/vehicle service topics."""
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAofftopic1",
            from_number="+15556660004",
            to_number="+15550001111",
        ),
    )
    result = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAofftopic1",
            speech_result="What's the weather like today? Tell me a joke.",
        ),
    )
    text = (result.spoken_text or "").lower()
    assert "vehicle" in text or "shop" in text or "service" in text
    assert "book" in text or "cancel" in text
    assert "joke" not in text
    assert "weather" not in text
    assert result.reply.end_call is not True


@pytest.mark.asyncio
async def test_speech_pipeline_tts(runtime):
    spoken = await runtime.speech.speak(text="Hello from the shop")
    assert spoken.text == "Hello from the shop"
    assert spoken.barge_in is True
    assert spoken.synthesis.audio_bytes


def test_voice_reply_unavailable_asks_only_broken_half():
    """preferred_time_unavailable should re-ask only date or only time."""
    from datetime import datetime
    from uuid import uuid4
    from zoneinfo import ZoneInfo

    from app.agents.base.agent import AgentContext, AgentResult
    from app.agents.intent.models import CustomerIntent, IntentResult
    from app.agents.orchestrator import PipelineResult
    from app.agents.scheduling.models import SchedulingResult
    from app.voice.memory import CallMemorySnapshot
    from app.voice.reply import VoiceReplyGenerator

    gen = VoiceReplyGenerator()
    shop = uuid4()
    la = ZoneInfo("America/Los_Angeles")
    preferred = datetime(2026, 8, 10, 15, 0, tzinfo=la)

    def _draft(aspect: str, *, time_precision: str = "clock", closed_day: bool = False):
        intent = IntentResult(
            intent=CustomerIntent.BOOK_APPOINTMENT,
            confidence=0.9,
            entities={
                "requested_service": "Oil Change",
                "preferred_start": preferred.isoformat(),
                "time_precision": time_precision,
                "needs_time": time_precision == "day",
            },
        )
        sched = SchedulingResult(
            action="list_slots",
            success=False,
            available_slots=[],
            message="preferred_time_unavailable",
            metadata={
                "preferred_time_unavailable": True,
                "unavailable_aspect": aspect,
                "closed_day": closed_day,
                "preferred_start": preferred.isoformat(),
            },
        )
        pipeline = PipelineResult(
            correlation_id="c",
            success=True,
            escalate=False,
            context=AgentContext(shop_id=shop),
            stages={
                "intent": AgentResult.ok(intent),
                "scheduling": AgentResult.ok(sched),
            },
        )
        return gen.generate(
            pipeline=pipeline,
            memory=CallMemorySnapshot(
                shop_id=shop, call_id=uuid4(), caller_phone="+1"
            ),
            customer_name="Alex",
        )

    date_draft = _draft("date")
    assert "other day" in date_draft.text.lower()
    assert "day or time" not in date_draft.text.lower()
    assert "day" in (date_draft.follow_up_question or "").lower()

    time_draft = _draft("time")
    assert "other time" in time_draft.text.lower()
    assert "day or time" not in time_draft.text.lower()
    assert "time" in (time_draft.follow_up_question or "").lower()

    # Soft day on closed shop day: refuse immediately even when intent needs time.
    closed = _draft("date", time_precision="day", closed_day=True)
    assert "isn't available" in closed.text.lower()
    assert "other day" in closed.text.lower()
    assert "what time" not in closed.text.lower()
    assert "3:00" not in closed.text  # day-only copy omits invented clock


@pytest.mark.asyncio
async def test_voice_cancel_confirms_with_yes_please(runtime, shop_id):
    """Book → cancel → yes please must actually cancel (not re-ask forever)."""
    phone = "+15559870123"
    call_sid = "CAcancel1"
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid=call_sid,
            from_number=phone,
            to_number="+15550001111",
        ),
    )
    await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid=call_sid, speech_result="I need an oil change appointment"
        ),
    )
    avail = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result="What times are available?"),
    )
    first = avail.pipeline.stages["scheduling"].data.available_slots[0].start
    day = first.strftime("%A")
    clock = first.strftime("%I:%M %p").lstrip("0")
    await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result=f"{day} at {clock}"),
    )
    await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result="Alex"),
    )
    booked = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result="yes"),
    )
    appt = booked.pipeline.stages["scheduling"].data.appointment
    assert appt is not None

    ask = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result="Cancel my appointment"),
    )
    assert ask.pipeline.stages["scheduling"].data.message == "awaiting_cancel_confirmation"
    assert "confirm" in (ask.spoken_text or "").lower()
    assert ask.pipeline.escalate is False

    done = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result="yes please"),
    )
    sched = done.pipeline.stages["scheduling"].data
    assert sched.success is True
    assert sched.appointment is not None
    assert sched.appointment.status == "cancelled"
    assert "cancelled" in (done.spoken_text or "").lower()
    assert done.pipeline.escalate is False

    stored = await runtime.agents.scheduling.store.get(shop_id, appt.id)
    assert stored is not None
    assert stored.status == "cancelled"


@pytest.mark.asyncio
async def test_voice_cancel_without_appointment_does_not_escalate(runtime, shop_id):
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAcancel0",
            from_number="+15559870999",
            to_number="+15550001111",
        ),
    )
    result = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAcancel0",
            speech_result="Cancel my appointment please",
        ),
    )
    assert result.pipeline is not None
    assert result.pipeline.escalate is False
    sched = result.pipeline.stages["scheduling"].data
    assert sched.message == "no_appointment_to_cancel"
    text = (result.spoken_text or "").lower()
    assert "not seeing" in text or "no" in text
    assert "grabbing someone" not in text


@pytest.mark.asyncio
async def test_voice_reschedule_confirms_without_service_name(runtime, shop_id):
    """After booking, pending service is cleared — still confirm a spoken clock move."""
    phone = "+15559870456"
    call_sid = "CAresched1"
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid=call_sid,
            from_number=phone,
            to_number="+15550001111",
        ),
    )
    await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid=call_sid, speech_result="I need an oil change appointment"
        ),
    )
    avail = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result="What times are available?"),
    )
    slots = avail.pipeline.stages["scheduling"].data.available_slots
    first = slots[0].start
    second = slots[1].start if len(slots) > 1 else slots[0].start
    day = first.strftime("%A")
    clock = first.strftime("%I:%M %p").lstrip("0")
    await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result=f"{day} at {clock}"),
    )
    await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result="Alex"),
    )
    booked = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result="yes"),
    )
    appt = booked.pipeline.stages["scheduling"].data.appointment
    assert appt is not None

    ask = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid=call_sid, speech_result="I want to change my appointment"
        ),
    )
    assert ask.pipeline.stages["scheduling"].data.message == "ask_preferred_time"
    assert "day" in (ask.spoken_text or "").lower() or "time" in (
        ask.spoken_text or ""
    ).lower()

    day2 = second.strftime("%A")
    clock2 = second.strftime("%I:%M %p").lstrip("0")
    hold = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result=f"{day2} at {clock2}"),
    )
    assert (
        hold.pipeline.stages["scheduling"].data.message
        == "awaiting_reschedule_confirmation"
    )
    # Must ask to confirm the move — not re-list random openings.
    spoken = (hold.spoken_text or "").lower()
    assert "shall i" in spoken or "move" in spoken or "confirm" in spoken
    assert "i've got a few openings" not in spoken

    done = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid=call_sid, speech_result="yes please"),
    )
    sched = done.pipeline.stages["scheduling"].data
    assert sched.success is True
    assert sched.appointment is not None
    assert "moved" in (done.spoken_text or "").lower() or "all set" in (
        done.spoken_text or ""
    ).lower()
    old = await runtime.agents.scheduling.store.get(shop_id, appt.id)
    assert old is not None
    assert old.status == "rescheduled"


@pytest.mark.asyncio
async def test_voice_reschedule_without_appointment_is_soft(runtime, shop_id):
    await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid="CAres0",
            from_number="+15551110999",
            to_number="+15550001111",
        ),
    )
    result = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAres0",
            speech_result="Can I change my appointment time?",
        ),
    )
    assert result.pipeline is not None
    assert result.pipeline.escalate is False
    assert (
        result.pipeline.stages["scheduling"].data.message
        == "no_appointment_to_reschedule"
    )
    text = (result.spoken_text or "").lower()
    assert "not seeing" in text
    assert "grabbing someone" not in text
