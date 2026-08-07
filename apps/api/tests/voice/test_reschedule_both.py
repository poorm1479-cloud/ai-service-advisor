"""Voice: change service type and appointment time together."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.factory import build_agent_runtime
from app.agents.scheduling.catalog_port import InMemoryServiceCatalog
from app.sms.queue import InMemoryMessageQueue
from app.voice.factory import build_voice_runtime
from app.voice.models import InboundCallEvent, SpeechInput
from app.voice.runtime import reset_voice_runtime
from app.voice.store import InMemoryVoiceStore
from app.voice.twilio.provider import FakeVoiceProvider, VoiceTwilioSettings
from app.voice.twilio.streams import MediaStreamHub
from app.workflows.factory import get_workflow_runtime


@pytest.fixture(autouse=True)
def _reset():
    reset_voice_runtime()
    yield
    reset_voice_runtime()


@pytest.fixture(autouse=True)
def _stub_ai_quota(monkeypatch: pytest.MonkeyPatch):
    async def _noop_consume(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.saas.quotas.QuotaService.consume", _noop_consume)


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def runtime(shop_id):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(shop_id)
    agents = build_agent_runtime(
        scheduling_store=get_workflow_runtime().coordinator.resolve_scheduling_agent_store(),
        service_catalog=catalog,
    )
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
        agents=agents,
        store=store,
        provider=provider,
        queue=InMemoryMessageQueue(),
        streams=MediaStreamHub(),
    )


async def _book_oil(runtime, shop_id, call_sid, phone):
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
    second = slots[3].start if len(slots) > 3 else slots[-1].start
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
    return appt, second


@pytest.mark.asyncio
async def test_change_service_and_time_one_shot(runtime, shop_id):
    appt, second = await _book_oil(runtime, shop_id, "CAbothA", "+15559870111")
    day2 = second.strftime("%A")
    clock2 = second.strftime("%I:%M %p").lstrip("0")
    utter = (
        f"Change the service type to brake repair and move it to {day2} at {clock2}"
    )
    r = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid="CAbothA", speech_result=utter),
    )
    intent = r.pipeline.stages["intent"].data
    sched = r.pipeline.stages["scheduling"].data
    assert intent.intent.value == "reschedule"
    assert intent.entities.get("requested_service") == "Brake Repair"
    assert intent.entities.get("preferred_start")
    assert sched.message == "awaiting_reschedule_confirmation"
    assert sched.decision is not None
    assert "brake" in (sched.decision.service_name or "").lower()

    done = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid="CAbothA", speech_result="yes please"),
    )
    ds = done.pipeline.stages["scheduling"].data
    assert ds.success and ds.appointment is not None
    assert ds.appointment.start == second
    assert "brake" in (getattr(ds.appointment, "service_name", None) or "").lower()
    assert ds.appointment.service_id != appt.service_id


@pytest.mark.asyncio
async def test_change_service_and_time_two_turns(runtime, shop_id):
    appt, second = await _book_oil(runtime, shop_id, "CAbothB", "+15559870222")
    ask = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAbothB",
            speech_result="I want to change both the service type and the appointment time",
        ),
    )
    assert ask.pipeline.stages["scheduling"].data.message != "no_appointment_to_reschedule"
    assert "not seeing" not in (ask.spoken_text or "").lower()
    spoken = (ask.spoken_text or "").lower()
    assert "service" in spoken or "instead" in spoken
    assert "day" in spoken or "time" in spoken

    day2 = second.strftime("%A")
    clock2 = second.strftime("%I:%M %p").lstrip("0")
    hold = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAbothB",
            speech_result=f"Brake repair {day2} at {clock2}",
        ),
    )
    intent = hold.pipeline.stages["intent"].data
    sched = hold.pipeline.stages["scheduling"].data
    assert intent.intent.value == "reschedule"
    assert intent.entities.get("requested_service") == "Brake Repair"
    assert sched.message == "awaiting_reschedule_confirmation"

    done = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid="CAbothB", speech_result="yes"),
    )
    ds = done.pipeline.stages["scheduling"].data
    assert ds.success and ds.appointment is not None
    assert ds.appointment.start == second
    assert "brake" in (getattr(ds.appointment, "service_name", None) or "").lower()
    assert ds.appointment.service_id != appt.service_id


@pytest.mark.asyncio
async def test_change_service_only_then_time(runtime, shop_id):
    """Service swap first, then new clock — both must land on the move."""
    appt, second = await _book_oil(runtime, shop_id, "CAbothC", "+15559870333")
    swap = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAbothC",
            speech_result="Please change the service type to brake repair",
        ),
    )
    assert swap.pipeline.stages["scheduling"].data.message != "no_appointment_to_reschedule"
    assert "not seeing" not in (swap.spoken_text or "").lower()

    day2 = second.strftime("%A")
    clock2 = second.strftime("%I:%M %p").lstrip("0")
    hold = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAbothC",
            speech_result=f"{day2} at {clock2}",
        ),
    )
    intent = hold.pipeline.stages["intent"].data
    sched = hold.pipeline.stages["scheduling"].data
    assert intent.intent.value == "reschedule"
    assert "brake" in (
        intent.entities.get("requested_service")
        or getattr(sched.decision, "service_name", None)
        or ""
    ).lower()
    assert sched.message == "awaiting_reschedule_confirmation"

    done = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(call_sid="CAbothC", speech_result="yes please"),
    )
    ds = done.pipeline.stages["scheduling"].data
    assert ds.success and ds.appointment is not None
    assert ds.appointment.start == second
    assert "brake" in (getattr(ds.appointment, "service_name", None) or "").lower()
    assert ds.appointment.service_id != appt.service_id


@pytest.mark.asyncio
async def test_bare_change_both_is_reschedule_ask(runtime, shop_id):
    await _book_oil(runtime, shop_id, "CAbothD", "+15559870444")
    r = await runtime.service.handle_speech(
        shop_id=shop_id,
        speech=SpeechInput(
            call_sid="CAbothD",
            speech_result="Change both the service type and the time",
        ),
    )
    assert r.pipeline.stages["intent"].data.intent.value == "reschedule"
    assert "not seeing" not in (r.spoken_text or "").lower()
    spoken = (r.spoken_text or "").lower()
    assert "service" in spoken
    assert "day" in spoken or "time" in spoken
