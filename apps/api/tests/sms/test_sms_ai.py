"""SMS AI unit tests — no Postgres required."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.sms.factory import build_sms_runtime
from app.sms.memory import ConversationTurn, InMemoryConversationMemory
from app.sms.models import InboundSms
from app.sms.queue import InMemoryMessageQueue
from app.sms.reply import ContextualReplyGenerator
from app.sms.runtime import reset_sms_runtime
from app.sms.store import InMemorySmsStore, normalize_phone
from app.sms.twilio.provider import FakeSmsProvider, validate_twilio_signature
from app.agents.orchestrator import PipelineResult
from app.agents.base.agent import AgentContext, AgentResult
from app.agents.intent.models import CustomerIntent, IntentResult


@pytest.fixture(autouse=True)
def _reset_runtime():
    reset_sms_runtime()
    yield
    reset_sms_runtime()


@pytest.fixture(autouse=True)
def _stub_sms_quota(monkeypatch: pytest.MonkeyPatch):
    """Unit tests use ephemeral shop UUIDs; skip DB-backed quota metering."""

    async def _noop_consume(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.saas.quotas.QuotaService.consume", _noop_consume)


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def runtime(shop_id):
    store = InMemorySmsStore()
    store.register_shop_number(shop_id, "+15550001111")
    provider = FakeSmsProvider()
    queue = InMemoryMessageQueue(max_attempts=3)
    return build_sms_runtime(store=store, provider=provider, queue=queue)


@pytest.mark.asyncio
async def test_normalize_phone():
    assert normalize_phone("555-123-4567") == "+15551234567"
    assert normalize_phone("+1 (555) 123-4567") == "+15551234567"


@pytest.mark.asyncio
async def test_twilio_signature_validation():
    token = "test_token"
    url = "https://example.com/v1/webhooks/twilio/sms"
    params = {"From": "+15551212", "Body": "hi", "To": "+1555000"}
    # Build expected the same way
    import base64
    import hashlib
    import hmac

    s = url + "".join(k + params[k] for k in sorted(params))
    sig = base64.b64encode(
        hmac.new(token.encode(), s.encode(), hashlib.sha1).digest()
    ).decode()
    assert validate_twilio_signature(
        auth_token=token, url=url, params=params, signature=sig
    )
    assert not validate_twilio_signature(
        auth_token=token, url=url, params=params, signature="bad"
    )


@pytest.mark.asyncio
async def test_conversation_memory_concurrent_keys(shop_id):
    memory = InMemoryConversationMemory()
    phone_a = "+15551110001"
    phone_b = "+15551110002"
    await memory.append(
        shop_id=shop_id,
        customer_phone=phone_a,
        turn=ConversationTurn(role="customer", content="A1"),
    )
    await memory.append(
        shop_id=shop_id,
        customer_phone=phone_b,
        turn=ConversationTurn(role="customer", content="B1"),
    )
    a = await memory.load(shop_id=shop_id, customer_phone=phone_a)
    b = await memory.load(shop_id=shop_id, customer_phone=phone_b)
    assert len(a.turns) == 1 and a.turns[0].content == "A1"
    assert len(b.turns) == 1 and b.turns[0].content == "B1"


@pytest.mark.asyncio
async def test_queue_retry_then_dead():
    queue = InMemoryMessageQueue(max_attempts=2)
    shop = uuid4()
    await queue.enqueue(shop_id=shop, payload={"type": "inbound_sms", "x": 1})

    async def boom(_job):
        raise RuntimeError("fail")

    assert await queue.process_one(boom)  # attempt 1 -> requeue
    assert await queue.process_one(boom)  # attempt 2 -> dead
    assert len(queue.dead_letter) == 1
    assert queue.stats["dead"] == 1


@pytest.mark.asyncio
async def test_book_appointment_sms_flow(runtime, shop_id):
    result = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number="+15559876543",
            to_number="+15550001111",
            body="Please book an appointment for me this week",
            message_sid="SMtest001",
        ),
    )
    assert result.conversation.customer_phone == "+15559876543"
    assert result.inbound.direction == "inbound"
    assert result.outbound is not None
    assert result.reply.body
    assert result.pipeline.stages["intent"].data.intent.value == "book_appointment"
    # Initial book request asks when they want to come — does not volunteer openings.
    assert result.pipeline.stages["scheduling"].data.action == "list_slots"
    assert result.pipeline.stages["scheduling"].data.message == "ask_preferred_time"
    body = result.reply.body.lower()
    assert "what service" in body or "day and time" in body or "time" in body
    assert "i've got" not in body
    assert len(runtime.provider.sent) == 1
    assert runtime.monitor.snapshot()["inbound_received"] == 1
    assert runtime.monitor.snapshot()["outbound_sent"] == 1

    # Memory retained
    mem = await runtime.memory.load(
        shop_id=shop_id, customer_phone="+15559876543"
    )
    assert len(mem.turns) >= 2


@pytest.mark.asyncio
async def test_availability_question_lists_slots(runtime, shop_id):
    result = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number="+15559876544",
            to_number="+15550001111",
            body="What times are available this week?",
            message_sid="SMtestAvail",
        ),
    )
    assert result.pipeline.stages["intent"].data.intent.value == "check_availability"
    assert result.pipeline.stages["scheduling"].data.action == "list_slots"
    assert len(result.pipeline.stages["scheduling"].data.available_slots) >= 2
    body = result.reply.body.lower()
    assert "i've got" in body or "at" in body
    assert "reply yes" in body or "yes" in body or "different time" in body


@pytest.mark.asyncio
async def test_oil_change_asks_time_then_preferred_time_books(runtime, shop_id):
    phone = "+15559876555"
    ask = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body="I need an oil change appointment",
            message_sid="SMoilOffer",
        ),
    )
    assert ask.pipeline.stages["intent"].data.entities.get("requested_service") == "Oil Change"
    assert ask.pipeline.stages["scheduling"].data.message == "ask_preferred_time"
    assert "time" in ask.reply.body.lower()
    assert "i've got" not in ask.reply.body.lower()

    mem = await runtime.memory.load(shop_id=shop_id, customer_phone=phone)
    assert mem.pending_service == "Oil Change"
    assert not mem.slots_offered

    # Discover openings only when the customer asks.
    avail = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body="What times are available?",
            message_sid="SMoilAvail",
        ),
    )
    slots = avail.pipeline.stages["scheduling"].data.available_slots
    assert slots
    first_start = slots[0].start
    assert "i've got" in avail.reply.body.lower() or "at" in avail.reply.body.lower()

    day = first_start.strftime("%A")
    clock = first_start.strftime("%I:%M %p").lstrip("0")
    pending = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body=f"{day} at {clock}",
            message_sid="SMoilTime",
        ),
    )
    # New phone numbers are unnamed until we ask.
    assert "name" in pending.reply.body.lower()
    assert "go ahead and book" not in pending.reply.body.lower()

    named = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body="Alex",
            message_sid="SMoilName",
        ),
    )
    assert (
        "book" in named.reply.body.lower()
        or "shall i book" in named.reply.body.lower()
        or "should i book" in named.reply.body.lower()
    )
    assert "Alex" in named.reply.body
    assert "go ahead" not in named.reply.body.lower()
    assert "going" not in named.reply.body.lower()

    confirm = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body="YES",
            message_sid="SMoilYes",
        ),
    )
    sched = confirm.pipeline.stages["scheduling"].data
    assert sched.action == "book"
    assert sched.success
    assert sched.appointment is not None
    assert sched.appointment.start == first_start
    assert "oil change" in confirm.reply.body.lower()
    assert "booked" in confirm.reply.body.lower()

    mem_after = await runtime.memory.load(shop_id=shop_id, customer_phone=phone)
    assert mem_after.appointment_id == str(sched.appointment.id)
    assert not mem_after.slots_offered


@pytest.mark.asyncio
async def test_soft_book_offer_then_yes_asks_for_time(runtime, shop_id):
    """Maintenance soft confirm → yes should ask for a day/time, not re-ask service."""
    phone = "+15559876557"
    offer = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body="oil change",
            message_sid="SMsoftOffer",
        ),
    )
    assert offer.pipeline.stages["intent"].data.intent.value == "maintenance_question"
    assert offer.pipeline.stages["intent"].data.entities.get("requested_service") == "Oil Change"
    assert "want me to book" in offer.reply.body.lower()

    mem = await runtime.memory.load(shop_id=shop_id, customer_phone=phone)
    assert mem.pending_service == "Oil Change"
    assert mem.pending_action == "book"
    assert not mem.slots_offered

    yes = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body="yes",
            message_sid="SMsoftYes",
        ),
    )
    body = yes.reply.body.lower()
    assert "what service" not in body
    assert yes.pipeline.stages["intent"].data.intent.value == "book_appointment"
    assert yes.pipeline.stages["scheduling"].data.message == "ask_preferred_time"
    assert "time" in body
    assert "i've got" not in body
    mem_after = await runtime.memory.load(shop_id=shop_id, customer_phone=phone)
    assert mem_after.pending_service == "Oil Change"


@pytest.mark.asyncio
async def test_oil_change_then_preferred_time_needs_confirm(runtime, shop_id):
    phone = "+15559876556"
    ask = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body="I need an oil change",
            message_sid="SMoilTime1",
        ),
    )
    assert ask.pipeline.stages["scheduling"].data.message == "ask_preferred_time"
    assert not ask.pipeline.stages["scheduling"].data.available_slots

    avail = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body="What times are available this week?",
            message_sid="SMoilTimeAvail",
        ),
    )
    slots = avail.pipeline.stages["scheduling"].data.available_slots
    assert len(slots) >= 2
    chosen = slots[1].start
    # Ask for that weekday + clock so preferred binds to the offered opening.
    day = chosen.strftime("%A")
    clock = chosen.strftime("%I:%M %p").lstrip("0")
    pending = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body=f"{day} at {clock}",
            message_sid="SMoilTime2",
        ),
    )
    assert pending.pipeline.stages["scheduling"].data.action == "list_slots"
    assert "name" in pending.reply.body.lower()

    named = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body="my name is Sam",
            message_sid="SMoilTimeName",
        ),
    )
    assert "book" in named.reply.body.lower() or "should i book" in named.reply.body.lower()
    assert "go ahead" not in named.reply.body.lower()
    assert "going" not in named.reply.body.lower()

    confirm = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number=phone,
            to_number="+15550001111",
            body="yes",
            message_sid="SMoilTime3",
        ),
    )
    sched = confirm.pipeline.stages["scheduling"].data
    assert sched.action == "book"
    assert sched.appointment is not None
    assert sched.appointment.start == chosen


@pytest.mark.asyncio
async def test_multiple_simultaneous_conversations(runtime, shop_id):
    phones = [f"+1555000{i:04d}" for i in range(5)]
    for phone in phones:
        await runtime.service.process_inbound(
            shop_id=shop_id,
            inbound=InboundSms(
                from_number=phone,
                to_number="+15550001111",
                body="How much does a brake job cost?",
            ),
        )
    convs = await runtime.store.list_conversations(shop_id)
    assert len(convs) == 5
    assert runtime.monitor.snapshot()["inbound_received"] == 5


@pytest.mark.asyncio
async def test_emergency_escalates_and_owner_summary(runtime, shop_id):
    result = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number="+15557770001",
            to_number="+15550001111",
            body="Emergency! My car is smoking and I'm stranded",
        ),
    )
    assert result.pipeline.escalate
    assert result.conversation.escalate
    assert result.owner_summary
    assert runtime.monitor.snapshot()["escalations"] >= 1


@pytest.mark.asyncio
async def test_human_takeover_skips_ai_reply(runtime, shop_id):
    first = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number="+15556660001",
            to_number="+15550001111",
            body="Hello",
        ),
    )
    await runtime.service.set_human_takeover(
        shop_id=shop_id, conversation_id=first.conversation.id, enabled=True
    )
    before = len(runtime.provider.sent)
    second = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number="+15556660001",
            to_number="+15550001111",
            body="Still waiting",
        ),
    )
    assert second.outbound is None
    assert second.reply.send is False
    assert len(runtime.provider.sent) == before


@pytest.mark.asyncio
async def test_delete_conversation_removes_thread_and_messages(runtime, shop_id):
    result = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number="+15556667777",
            to_number="+15550001111",
            body="Oil change please",
        ),
    )
    conv_id = result.conversation.id
    assert await runtime.store.get_conversation(shop_id, conv_id) is not None
    assert len(await runtime.store.list_messages(shop_id, conv_id)) >= 1

    await runtime.service.delete_conversation(shop_id=shop_id, conversation_id=conv_id)

    assert await runtime.store.get_conversation(shop_id, conv_id) is None
    assert await runtime.store.list_messages(shop_id, conv_id) == []
    remaining = await runtime.store.list_conversations(shop_id)
    assert all(c.id != conv_id for c in remaining)

    # Same phone can start a fresh thread after delete
    again = await runtime.service.process_inbound(
        shop_id=shop_id,
        inbound=InboundSms(
            from_number="+15556667777",
            to_number="+15550001111",
            body="Hello again",
        ),
    )
    assert again.conversation.id != conv_id


@pytest.mark.asyncio
async def test_delete_conversation_not_found(runtime, shop_id):
    with pytest.raises(ValueError, match="Conversation not found"):
        await runtime.service.delete_conversation(shop_id=shop_id, conversation_id=uuid4())


@pytest.mark.asyncio
async def test_enqueue_and_process_job(runtime, shop_id):
    job = await runtime.service.enqueue_inbound(
        InboundSms(
            from_number="+15554440001",
            to_number="+15550001111",
            body="Cancel my appointment please",
        ),
        shop_id=shop_id,
    )
    result = await runtime.service.process_job(job)
    assert result is not None
    assert result.pipeline.stages["intent"].data.intent.value == "cancel_appointment"


@pytest.mark.asyncio
async def test_reply_generator_book_template():
    gen = ContextualReplyGenerator()
    shop = uuid4()
    intent = IntentResult(intent=CustomerIntent.BOOK_APPOINTMENT, confidence=0.9)

    class Appt:
        start = __import__("datetime").datetime(2026, 8, 1, 15, 0, tzinfo=__import__("datetime").timezone.utc)
        id = uuid4()

    class Sched:
        success = True
        action = "book"
        appointment = Appt()
        available_slots = []

    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=AgentContext(shop_id=shop),
        stages={
            "intent": AgentResult.ok(intent),
            "scheduling": AgentResult.ok(Sched()),
        },
    )
    from app.sms.memory import ConversationMemorySnapshot

    draft = gen.generate(
        pipeline=pipeline,
        memory=ConversationMemorySnapshot(shop_id=shop, customer_phone="+1", conversation_id=None),
        customer_name="Alex",
    )
    assert "Alex" in draft.body
    assert "booked" in draft.body.lower()


@pytest.mark.asyncio
async def test_reply_does_not_confirm_outside_hours_preferred_time():
    """Openings exist, but an out-of-hours preferred clock must not be confirmed."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.agents.scheduling.models import SchedulingResult, TimeSlot

    gen = ContextualReplyGenerator()
    shop = uuid4()
    la = ZoneInfo("America/Los_Angeles")
    preferred = datetime(2026, 8, 10, 20, 0, tzinfo=la)  # 8pm — outside typical hours
    intent = IntentResult(
        intent=CustomerIntent.BOOK_APPOINTMENT,
        confidence=0.9,
        entities={
            "requested_service": "Oil Change",
            "preferred_start": preferred.isoformat(),
            "time_precision": "clock",
        },
    )
    sched = SchedulingResult(
        action="list_slots",
        success=True,
        available_slots=[
            TimeSlot(
                start=datetime(2026, 8, 10, 10, 0, tzinfo=la),
                end=datetime(2026, 8, 10, 11, 0, tzinfo=la),
                available=True,
            )
        ],
        message="1 slots available",
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
    from app.sms.memory import ConversationMemorySnapshot

    draft = gen.generate(
        pipeline=pipeline,
        memory=ConversationMemorySnapshot(
            shop_id=shop, customer_phone="+1", conversation_id=None
        ),
        customer_name="Alex",
    )
    body = draft.body.lower()
    assert "8:00 pm" not in body
    assert "go ahead and book" not in body
    assert "booked" not in body


@pytest.mark.asyncio
async def test_reply_generator_book_asks_service_when_missing():
    """Booking desire without a service should ask which service — not re-ask purpose."""
    gen = ContextualReplyGenerator()
    shop = uuid4()
    intent = IntentResult(intent=CustomerIntent.BOOK_APPOINTMENT, confidence=0.9)
    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=AgentContext(shop_id=shop),
        stages={"intent": AgentResult.ok(intent)},
    )
    from app.sms.memory import ConversationMemorySnapshot
    from app.sms.models import ConversationTurn

    memory = ConversationMemorySnapshot(
        shop_id=shop,
        customer_phone="+1",
        conversation_id=None,
        turns=[
            ConversationTurn(
                role="assistant",
                content="Hello, this is the shop. what can I help you with?",
            ),
            ConversationTurn(role="customer", content="I want to make a reservation"),
        ],
    )
    draft = gen.generate(pipeline=pipeline, memory=memory, customer_name="Alex")
    body = draft.body.lower()
    assert "service" in body
    assert "what can i help you with" not in body


@pytest.mark.asyncio
async def test_reply_generator_other_after_purpose_asks_service():
    """Even if intent is OTHER, booking answer to purpose ask must not loop."""
    gen = ContextualReplyGenerator()
    shop = uuid4()
    intent = IntentResult(intent=CustomerIntent.OTHER, confidence=0.4)
    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=AgentContext(shop_id=shop),
        stages={"intent": AgentResult.ok(intent)},
    )
    from app.sms.memory import ConversationMemorySnapshot
    from app.sms.models import ConversationTurn

    memory = ConversationMemorySnapshot(
        shop_id=shop,
        customer_phone="+1",
        conversation_id=None,
        turns=[
            ConversationTurn(
                role="assistant",
                content="Hello, this is the shop. what can I help you with?",
            ),
            ConversationTurn(role="customer", content="I want to make a reservation"),
        ],
        pending_question="what can I help you with?",
    )
    draft = gen.generate(pipeline=pipeline, memory=memory, customer_name="Alex")
    body = draft.body.lower()
    assert "service" in body
    assert "what can i help you with" not in body


@pytest.mark.asyncio
async def test_reply_generator_book_with_day_still_asks_service_first():
    """Day preference must not skip the service question."""
    gen = ContextualReplyGenerator()
    shop = uuid4()
    intent = IntentResult(
        intent=CustomerIntent.BOOK_APPOINTMENT,
        confidence=0.9,
        entities={"needs_time": True, "preferred_start": "2026-08-07T08:00:00-07:00"},
    )
    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=AgentContext(shop_id=shop),
        stages={"intent": AgentResult.ok(intent)},
    )
    from app.sms.memory import ConversationMemorySnapshot
    from app.sms.models import ConversationTurn

    memory = ConversationMemorySnapshot(
        shop_id=shop,
        customer_phone="+1",
        conversation_id=None,
        turns=[
            ConversationTurn(role="customer", content="Book me for Friday"),
        ],
    )
    draft = gen.generate(pipeline=pipeline, memory=memory, customer_name="Alex")
    assert "service" in draft.body.lower()
    assert "day and time" not in draft.body.lower()


@pytest.mark.asyncio
async def test_reply_generator_reschedule_after_purpose_does_not_ask_service():
    """Answering 'what can I help with?' with a time-change must not ask for service."""
    gen = ContextualReplyGenerator()
    shop = uuid4()
    intent = IntentResult(intent=CustomerIntent.RESCHEDULE, confidence=0.9)
    ctx = AgentContext(
        shop_id=shop,
        metadata={
            "upcoming_appointments": [
                {
                    "id": str(uuid4()),
                    "start": "2026-08-10T15:00:00+00:00",
                    "status": "booked",
                    "service_name": "Oil Change",
                }
            ],
        },
    )
    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=ctx,
        stages={"intent": AgentResult.ok(intent)},
    )
    from app.sms.memory import ConversationMemorySnapshot
    from app.sms.models import ConversationTurn

    memory = ConversationMemorySnapshot(
        shop_id=shop,
        customer_phone="+1",
        conversation_id=None,
        turns=[
            ConversationTurn(
                role="customer", content="Can I change my appointment time?"
            ),
        ],
        pending_question="what can I help you with?",
    )
    draft = gen.generate(pipeline=pipeline, memory=memory, customer_name="Alex")
    body = draft.body.lower()
    assert "what service" not in body
    assert "change" in body or "move" in body or "day" in body or "time" in body
    # Must not invent a random confirmation time the customer never chose.
    assert "want me to do that" not in body
    assert "should i book" not in body


@pytest.mark.asyncio
async def test_reply_generator_appointment_time_change_does_not_ask_service():
    """Noun-style 'appointment time change' must ask for new time, not service."""
    gen = ContextualReplyGenerator()
    shop = uuid4()
    intent = IntentResult(intent=CustomerIntent.RESCHEDULE, confidence=0.9)
    ctx = AgentContext(
        shop_id=shop,
        metadata={
            "upcoming_appointments": [
                {
                    "id": str(uuid4()),
                    "start": "2026-08-10T15:00:00+00:00",
                    "status": "booked",
                    "service_name": "Oil Change",
                }
            ],
        },
    )
    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=ctx,
        stages={"intent": AgentResult.ok(intent)},
    )
    from app.sms.memory import ConversationMemorySnapshot
    from app.sms.models import ConversationTurn

    memory = ConversationMemorySnapshot(
        shop_id=shop,
        customer_phone="+1",
        conversation_id=None,
        turns=[
            ConversationTurn(
                role="customer", content="I need an appointment time change"
            ),
        ],
    )
    draft = gen.generate(
        pipeline=pipeline, memory=memory, customer_name="Alex", shop_name="Shop"
    )
    body = draft.body.lower()
    assert "what service" not in body
    assert "day" in body or "time" in body or "change" in body


@pytest.mark.asyncio
async def test_reply_generator_book_misclass_time_change_asks_time_not_service():
    """Even if intent is BOOK, time-change phrasing must not ask which service."""
    gen = ContextualReplyGenerator()
    shop = uuid4()
    intent = IntentResult(intent=CustomerIntent.BOOK_APPOINTMENT, confidence=0.86)
    ctx = AgentContext(
        shop_id=shop,
        metadata={
            "upcoming_appointments": [
                {
                    "id": str(uuid4()),
                    "start": "2026-08-10T15:00:00+00:00",
                    "status": "booked",
                    "service_name": "Brake Inspection",
                }
            ],
        },
    )
    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=ctx,
        stages={"intent": AgentResult.ok(intent)},
    )
    from app.sms.memory import ConversationMemorySnapshot
    from app.sms.models import ConversationTurn

    memory = ConversationMemorySnapshot(
        shop_id=shop,
        customer_phone="+1",
        conversation_id=None,
        turns=[
            ConversationTurn(
                role="customer", content="reservation time change please"
            ),
        ],
    )
    draft = gen.generate(
        pipeline=pipeline, memory=memory, customer_name="Alex", shop_name="Shop"
    )
    body = draft.body.lower()
    assert "what service" not in body
    assert "day" in body or "time" in body or "change" in body


@pytest.mark.asyncio
async def test_reply_generator_reschedule_does_not_invent_slot_confirm():
    """Pending slot without a customer-chosen clock time must not be confirmed."""
    gen = ContextualReplyGenerator()
    shop = uuid4()
    intent = IntentResult(intent=CustomerIntent.RESCHEDULE, confidence=0.9)

    class Sched:
        success = False
        action = "list_slots"
        appointment = None
        available_slots = []
        message = "awaiting_reschedule_confirmation"
        metadata = {
            "awaiting_confirmation": True,
            "action": "reschedule",
            "pending_slot_start": "2026-08-12T14:00:00+00:00",
        }
        decision = type(
            "D",
            (),
            {
                "recommended_slot_start": __import__("datetime").datetime(
                    2026,
                    8,
                    12,
                    14,
                    0,
                    tzinfo=__import__("datetime").timezone.utc,
                ),
                "service_name": "Oil Change",
            },
        )()

    ctx = AgentContext(
        shop_id=shop,
        metadata={
            "upcoming_appointments": [
                {
                    "id": str(uuid4()),
                    "start": "2026-08-10T15:00:00+00:00",
                    "status": "booked",
                    "service_name": "Oil Change",
                }
            ],
        },
    )
    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=ctx,
        stages={
            "intent": AgentResult.ok(intent),
            "scheduling": AgentResult.ok(Sched()),
        },
    )
    from app.sms.memory import ConversationMemorySnapshot
    from app.sms.models import ConversationTurn

    draft = gen.generate(
        pipeline=pipeline,
        memory=ConversationMemorySnapshot(
            shop_id=shop,
            customer_phone="+1",
            conversation_id=None,
            turns=[
                ConversationTurn(
                    role="customer", content="Can I change my appointment time?"
                )
            ],
        ),
        customer_name="Alex",
    )
    body = draft.body.lower()
    assert "want me to do that" not in body
    assert "wednesday" not in body
    assert "new" in body or "day" in body or "time" in body


@pytest.mark.asyncio
async def test_reply_generator_reschedule_affirms_change():
    gen = ContextualReplyGenerator()
    shop = uuid4()
    intent = IntentResult(
        intent=CustomerIntent.RESCHEDULE,
        confidence=0.9,
        entities={
            "preferred_start": "2026-08-12T14:00:00+00:00",
            "time_precision": "day",
        },
    )

    class Slot:
        start = __import__("datetime").datetime(
            2026, 8, 12, 14, 0, tzinfo=__import__("datetime").timezone.utc
        )

    class Sched:
        success = False
        action = "reschedule"
        appointment = None
        available_slots = [Slot()]

    ctx = AgentContext(
        shop_id=shop,
        metadata={
            "upcoming_appointments": [
                {
                    "id": str(uuid4()),
                    "start": "2026-08-10T15:00:00+00:00",
                    "status": "booked",
                    "service_name": "Oil Change",
                }
            ],
        },
    )
    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=ctx,
        stages={
            "intent": AgentResult.ok(intent),
            "scheduling": AgentResult.ok(Sched()),
        },
    )
    from app.sms.memory import ConversationMemorySnapshot

    draft = gen.generate(
        pipeline=pipeline,
        memory=ConversationMemorySnapshot(
            shop_id=shop, customer_phone="+1", conversation_id=None
        ),
        customer_name="Sam",
    )
    assert "change" in draft.body.lower()
    assert "Oil Change" in draft.body
    assert "got" in draft.body.lower() or "at" in draft.body.lower()


@pytest.mark.asyncio
async def test_reply_generator_references_customer_and_schedule():
    gen = ContextualReplyGenerator()
    shop = uuid4()
    intent = IntentResult(intent=CustomerIntent.OTHER, confidence=0.5)
    ctx = AgentContext(
        shop_id=shop,
        metadata={
            "customer_snapshot": {
                "id": str(uuid4()),
                "name": "Jordan Lee",
                "phone": "+15551212",
                "is_new": False,
            },
            "upcoming_appointments": [
                {
                    "id": str(uuid4()),
                    "start": "2026-08-10T15:00:00+00:00",
                    "status": "booked",
                    "service_name": "Oil Change",
                }
            ],
        },
    )
    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=ctx,
        stages={"intent": AgentResult.ok(intent)},
    )
    from app.sms.memory import ConversationMemorySnapshot
    from app.sms.models import ConversationTurn

    draft = gen.generate(
        pipeline=pipeline,
        memory=ConversationMemorySnapshot(shop_id=shop, customer_phone="+1", conversation_id=None),
        shop_name="Main Street Auto",
    )
    assert "Jordan" in draft.body
    assert "Oil Change" in draft.body
    assert "Aug 10" in draft.body
    assert "your oil change is on" in draft.body.lower() or "you've got" in draft.body.lower()
    assert draft.body.startswith("Hello Jordan, this is Main Street Auto")

    follow_up = gen.generate(
        pipeline=pipeline,
        memory=ConversationMemorySnapshot(
            shop_id=shop,
            customer_phone="+1",
            conversation_id=None,
            turns=[
                ConversationTurn(role="customer", content="hi"),
                ConversationTurn(role="assistant", content="Hello Jordan, this is Main Street Auto."),
                ConversationTurn(role="customer", content="ok"),
            ],
        ),
        shop_name="Main Street Auto",
    )
    assert not follow_up.body.startswith("Jordan")
    assert not follow_up.body.startswith("Hello")
    assert "Oil Change" in follow_up.body

@pytest.mark.asyncio
async def test_reply_asks_name_before_booking_new_customer():
    """Unknown / new customers must give a name before the final confirm."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.agents.scheduling.models import SchedulingResult

    gen = ContextualReplyGenerator()
    shop = uuid4()
    la = ZoneInfo("America/Los_Angeles")
    when = datetime(2026, 8, 10, 10, 0, tzinfo=la)
    intent = IntentResult(
        intent=CustomerIntent.BOOK_APPOINTMENT,
        confidence=0.9,
        entities={"requested_service": "Oil Change"},
    )
    sched = SchedulingResult(
        action="list_slots",
        success=True,
        available_slots=[],
        message="awaiting_customer_name",
        metadata={
            "awaiting_customer_name": True,
            "awaiting_confirmation": True,
            "action": "book",
            "pending_slot_start": when.isoformat(),
            "pending_slot_end": when.isoformat(),
        },
    )
    ctx = AgentContext(
        shop_id=shop,
        metadata={
            "customer_snapshot": {
                "id": str(uuid4()),
                "name": "Unknown Customer",
                "phone": "+15551212",
                "is_new": True,
            }
        },
    )
    pipeline = PipelineResult(
        correlation_id="c",
        success=True,
        escalate=False,
        context=ctx,
        stages={
            "intent": AgentResult.ok(intent),
            "scheduling": AgentResult.ok(sched),
        },
    )
    from app.sms.memory import ConversationMemorySnapshot
    from app.sms.models import ConversationTurn

    draft = gen.generate(
        pipeline=pipeline,
        memory=ConversationMemorySnapshot(
            shop_id=shop,
            customer_phone="+1",
            conversation_id=None,
            turns=[
                ConversationTurn(role="assistant", content="Hello, this is the shop."),
                ConversationTurn(role="customer", content="Oil change Friday at 10"),
            ],
        ),
        customer_name="Unknown Customer",
    )
    body = draft.body.lower()
    assert "name" in body
    assert "go ahead and book" not in body
    assert "booked" not in body


@pytest.mark.asyncio
async def test_resolve_shop_from_map(runtime, shop_id):
    resolved = await runtime.service.resolve_shop_id("+15550001111")
    assert resolved == shop_id
