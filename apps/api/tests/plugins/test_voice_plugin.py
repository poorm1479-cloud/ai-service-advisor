"""Phase 15 — Production Voice AI plugin tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.plugins.framework.plugin import IPlugin
from app.plugins.voice.events import (
    CallCompletedEvent,
    ConversationStartedEvent,
    HumanEscalationEvent,
    IncomingCallEvent,
    VoiceMessageEvent,
)
from app.plugins.voice.factory import reset_voice_plugin


@pytest.fixture(autouse=True)
def _reset():
    reset_voice_plugin()
    reset_plugin_runtime()
    yield
    reset_voice_plugin()
    reset_plugin_runtime()


@pytest.mark.asyncio
async def test_voice_registers_capabilities():
    runtime = ensure_default_plugins()
    plugin = runtime.plugins.lookup("voice")
    assert isinstance(plugin, IPlugin)
    caps = set(plugin.supported_capabilities())
    for name in (
        Capability.RECEIVE_CALL.value,
        Capability.CREATE_VOICE_SESSION.value,
        Capability.SPEECH_TO_TEXT.value,
        Capability.TEXT_TO_SPEECH.value,
        Capability.TRANSFER_TO_HUMAN.value,
        Capability.END_CALL.value,
        Capability.RECORD_CONVERSATION.value,
    ):
        assert name in caps


@pytest.mark.asyncio
async def test_call_lifecycle_events_and_metrics():
    ensure_default_plugins()
    shop_id = uuid4()
    ctx = PluginContext.for_shop(shop_id)

    received = await invoke_capability(
        Capability.RECEIVE_CALL.value,
        context=ctx,
        shop_id=shop_id,
        from_number="+15551234567",
        to_number="+15557654321",
    )
    assert received["created"] is True
    assert isinstance(received["event"], IncomingCallEvent)
    assert received["business_actions_executed"] is False

    session = await invoke_capability(
        Capability.CREATE_VOICE_SESSION.value,
        context=ctx,
        shop_id=shop_id,
        call_sid=received["call_sid"],
        from_number="+15551234567",
        to_number="+15557654321",
    )
    assert session["conversation_started"] is True
    assert isinstance(session["event"], ConversationStartedEvent)
    session_id = session["session_id"]

    stt = await invoke_capability(
        Capability.SPEECH_TO_TEXT.value,
        context=ctx,
        shop_id=shop_id,
        session_id=session_id,
        text_hint="My brakes are squeaking",
    )
    assert "brakes" in stt["text"].lower()
    assert stt["business_actions_executed"] is False

    tts = await invoke_capability(
        Capability.TEXT_TO_SPEECH.value,
        context=ctx,
        shop_id=shop_id,
        session_id=session_id,
        call_sid=received["call_sid"],
        text="I can help schedule a brake inspection.",
    )
    assert tts.get("audio_url")
    assert tts["business_actions_executed"] is False

    recorded = await invoke_capability(
        Capability.RECORD_CONVERSATION.value,
        context=ctx,
        shop_id=shop_id,
        session_id=session_id,
        recording_url="https://recordings.example/call.mp3",
    )
    assert "brakes" in recorded["transcript"].lower()
    assert recorded["business_actions_executed"] is False

    ended = await invoke_capability(
        Capability.END_CALL.value,
        context=ctx,
        shop_id=shop_id,
        session_id=session_id,
        resolved_by_ai=True,
        appointment_converted=True,
        satisfaction=4.5,
    )
    assert ended["ok"] is True
    assert isinstance(ended["event"], CallCompletedEvent)
    assert ended["business_actions_executed"] is False

    plugin = ensure_default_plugins().plugins.lookup("voice")
    metrics = plugin.metrics.snapshot()
    assert metrics["call_volume"] >= 1
    assert metrics["calls_completed"] >= 1
    assert metrics["ai_resolution_rate"] > 0
    assert metrics["appointment_conversion_rate"] > 0
    assert metrics["customer_satisfaction"] == 4.5


@pytest.mark.asyncio
async def test_transfer_to_human_emits_escalation_without_business_actions():
    ensure_default_plugins()
    shop_id = uuid4()
    session = await invoke_capability(
        Capability.CREATE_VOICE_SESSION.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        from_number="+15550001111",
    )
    transferred = await invoke_capability(
        Capability.TRANSFER_TO_HUMAN.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        session_id=session["session_id"],
        reason="angry_customer",
    )
    assert transferred["transferred"] is True
    assert transferred["business_actions_executed"] is False
    assert isinstance(transferred["event"], HumanEscalationEvent)

    plugin = ensure_default_plugins().plugins.lookup("voice")
    assert plugin.metrics.snapshot()["human_transfer_rate"] >= 0


@pytest.mark.asyncio
async def test_stt_can_request_advisor_decisions_without_applying():
    ensure_default_plugins()
    shop_id = uuid4()
    session = await invoke_capability(
        Capability.CREATE_VOICE_SESSION.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        from_number="+15550002222",
    )
    stt = await invoke_capability(
        Capability.SPEECH_TO_TEXT.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        session_id=session["session_id"],
        text_hint="Need oil change appointment please",
        request_advice=True,
    )
    assert "advisor" in stt
    assert stt["advisor"]["applied"] is False
    assert stt["advisor"]["business_actions_executed"] is False
    # Decisions may be present; Voice must not apply them
    assert "customer_created" not in stt
    assert "appointment_booked" not in stt


@pytest.mark.asyncio
async def test_voice_message_events_on_turns():
    ensure_default_plugins()
    shop_id = uuid4()
    session = await invoke_capability(
        Capability.CREATE_VOICE_SESSION.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        from_number="+15550003333",
    )
    plugin = ensure_default_plugins().plugins.lookup("voice")
    before = len(plugin.sessions.events)
    await invoke_capability(
        Capability.SPEECH_TO_TEXT.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        session_id=session["session_id"],
        text_hint="Hello",
    )
    events = plugin.sessions.events[before:]
    assert any(isinstance(e, VoiceMessageEvent) for e in events)


@pytest.mark.asyncio
async def test_existing_plugins_still_registered():
    runtime = ensure_default_plugins()
    for pid in (
        "crm",
        "scheduling",
        "conversation",
        "revenue",
        "advisor",
        "inspection",
        "inventory",
        "voice",
    ):
        assert runtime.plugins.lookup(pid)
