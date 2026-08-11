"""Voice AI service  -  Twilio Voice → speech pipeline → agents → TTS → CRM."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.agents.base.agent import AgentContext
from app.agents.communication.models import RawInboundMessage
from app.agents.factory import AgentRuntime
from app.agents.orchestrator import PipelineResult
from app.domain.entities import CommunicationHistory
from app.domain.enums import CommunicationChannel, CommunicationDirection
from app.domain.repositories import UnitOfWork
from app.sms.queue import MessageQueuePort
from app.sms.store import normalize_phone
from app.voice.enums import VoiceCallStatus, VoiceTurnRole
from app.voice.memory import CallMemoryPort
from app.voice.models import InboundCallEvent, SpeechInput, VoiceCall, VoiceTurn
from app.voice.monitoring import VoiceMonitor
from app.voice.reply import VoiceReplyDraft, VoiceReplyGenerator
from app.voice.speech import SpeechPipeline
from app.voice.store import VoiceStorePort
from app.voice.twilio.provider import VoiceProviderPort
from app.voice.twilio.streams import MediaStreamHub

logger = logging.getLogger("asa.voice.service")


@dataclass(slots=True)
class VoiceTurnResult:
    call: VoiceCall
    caller_turn: VoiceTurn | None
    assistant_turn: VoiceTurn | None
    reply: VoiceReplyDraft
    spoken_text: str
    pipeline: PipelineResult | None
    twiml: str
    owner_notified: bool = False


class VoiceAiService:
    """Answers every inbound phone call with interruptible, context-aware AI."""

    def __init__(
        self,
        *,
        agents: AgentRuntime,
        store: VoiceStorePort,
        memory: CallMemoryPort,
        provider: VoiceProviderPort,
        speech: SpeechPipeline,
        queue: MessageQueuePort,
        monitor: VoiceMonitor,
        streams: MediaStreamHub,
        reply_generator: VoiceReplyGenerator | None = None,
        shop_number_map: dict[str, UUID] | None = None,
        gather_action_path: str = "/v1/webhooks/twilio/voice/gather",
        stream_ws_path: str = "/v1/webhooks/twilio/voice/stream",
        public_base_url: str = "",
        stream_enabled: bool = True,
        uow_factory: Any | None = None,
        owner_notifier: Any | None = None,
    ) -> None:
        self._agents = agents
        self._store = store
        self._memory = memory
        self._provider = provider
        self._speech = speech
        self._queue = queue
        self._monitor = monitor
        self._streams = streams
        self._reply = reply_generator or VoiceReplyGenerator()
        self._shop_number_map = {
            normalize_phone(k): v for k, v in (shop_number_map or {}).items()
        }
        self._gather_action_path = gather_action_path
        self._stream_ws_path = stream_ws_path
        self._public_base_url = public_base_url.rstrip("/")
        self._stream_enabled = stream_enabled
        self._uow_factory = uow_factory
        self._owner_notifier = owner_notifier
        self._owner_notifications: list[dict[str, Any]] = []

    async def resolve_shop_id(self, to_number: str) -> UUID | None:
        phone = normalize_phone(to_number)
        if phone in self._shop_number_map:
            return self._shop_number_map[phone]
        return await self._store.find_shop_id_by_voice_number(phone)

    async def ensure_call_for_sid(
        self,
        *,
        call_sid: str,
        from_number: str,
        to_number: str,
    ) -> VoiceCall | None:
        """Return an existing call or create one if memory was lost mid-call.

        In-memory store is wiped on API reload; Twilio Gather still POSTs the
        CallSid — recover so we return TwiML instead of hanging up with 404.

        Always resolve shop from the To-number and bind FORCE RLS before SID
        lookup (non-superuser role cannot bypass row security).
        """
        if not call_sid:
            return None
        shop_id = await self.resolve_shop_id(to_number)
        if shop_id is None and len(self._shop_number_map) == 1:
            shop_id = next(iter(self._shop_number_map.values()))
        if shop_id is None:
            return None

        existing = await self._store.get_call_by_sid(call_sid, shop_id=shop_id)
        if existing:
            return existing

        if not from_number:
            return None

        now = datetime.now(timezone.utc)
        call = VoiceCall(
            id=uuid4(),
            shop_id=shop_id,
            caller_phone=normalize_phone(from_number),
            called_phone=normalize_phone(to_number) if to_number else "",
            status=VoiceCallStatus.IN_PROGRESS.value,
            twilio_call_sid=call_sid,
            started_at=now,
            created_at=now,
        )
        try:
            await self._store.create_call(call)
        except Exception:  # noqa: BLE001 — unique SID race: re-read
            logger.exception(
                "voice.call.recover_create_failed sid=%s — retrying get", call_sid
            )
            recovered = await self._store.get_call_by_sid(call_sid, shop_id=shop_id)
            if recovered is not None:
                return recovered
            raise
        self._monitor.record_call_started()
        logger.warning(
            "voice.call.recovered sid=%s shop_id=%s (store miss before gather)",
            call_sid,
            shop_id,
        )
        return call

    def _action_url(self, path: str) -> str:
        if self._public_base_url:
            return f"{self._public_base_url}{path}"
        return path

    def _stream_url(self) -> str | None:
        if not self._stream_enabled:
            return None
        base = self._public_base_url or "wss://localhost"
        if base.startswith("https://"):
            base = "wss://" + base[len("https://") :]
        elif base.startswith("http://"):
            base = "ws://" + base[len("http://") :]
        return f"{base}{self._stream_ws_path}"

    async def answer_call(
        self, *, shop_id: UUID, event: InboundCallEvent
    ) -> VoiceTurnResult:
        from app.saas.quota_context import shop_ai_scope

        with shop_ai_scope(shop_id):
            return await self._answer_call_inner(shop_id=shop_id, event=event)

    async def _answer_call_inner(
        self, *, shop_id: UUID, event: InboundCallEvent
    ) -> VoiceTurnResult:
        now = datetime.now(timezone.utc)
        # Always shop-scoped — unscoped SID reads fail under FORCE RLS (not superuser).
        existing = await self._store.get_call_by_sid(event.call_sid, shop_id=shop_id)
        if existing:
            call = existing
        else:
            call = VoiceCall(
                id=uuid4(),
                shop_id=shop_id,
                caller_phone=normalize_phone(event.from_number),
                called_phone=normalize_phone(event.to_number),
                status=VoiceCallStatus.IN_PROGRESS.value,
                twilio_call_sid=event.call_sid,
                started_at=now,
                created_at=now,
            )
            await self._store.create_call(call)
            self._monitor.record_call_started()

        await self._memory.load(
            shop_id=shop_id, call_id=call.id, caller_phone=call.caller_phone
        )

        if await self._store.is_shop_ai_paused(shop_id):
            # Stop Voice AI processing only — no agent/TTS pipeline.
            notice = (
                "Thanks for calling. Our phone assistant is paused right now. "
                "Please try again later."
            )
            twiml = self._provider.build_hangup_twiml(say_text=notice)
            live = await self._store.list_live_calls(shop_id)
            self._monitor.set_live_calls(len(live))
            draft = VoiceReplyDraft(text=notice, end_call=True, reason="ai_paused")
            return VoiceTurnResult(
                call=call,
                caller_turn=None,
                assistant_turn=None,
                reply=draft,
                spoken_text=notice,
                pipeline=None,
                twiml=twiml,
            )

        from app.agents.counselor.shop_name import resolve_shop_name

        shop_name = await resolve_shop_name(shop_id)
        draft = self._reply.greeting(shop_name=shop_name)
        from app.agents.counselor.persona import sanitize_spoken_reply

        draft.text = sanitize_spoken_reply(draft.text)
        # Twilio <Say> uses text; skip network TTS on the critical path.
        spoken = await self._speech.speak(text=draft.text, synthesize=False)
        assistant_turn = await self._persist_turn(
            call,
            role=VoiceTurnRole.ASSISTANT.value,
            text=spoken.text,
        )
        await self._memory.append(shop_id=shop_id, call_id=call.id, turn=assistant_turn)
        if draft.follow_up_question:
            await self._memory.update_state(
                shop_id=shop_id,
                call_id=call.id,
                pending_question=draft.follow_up_question,
            )

        twiml = self._provider.build_answer_twiml(
            say_text=spoken.text,
            action_url=self._action_url(self._gather_action_path),
            stream_ws_url=self._stream_url(),
            record=True,
            stream_parameters={
                "shop_id": str(shop_id),
                "to_number": call.called_phone or "",
                "call_id": str(call.id),
            },
        )
        live = await self._store.list_live_calls(shop_id)
        self._monitor.set_live_calls(len(live))

        return VoiceTurnResult(
            call=call,
            caller_turn=None,
            assistant_turn=assistant_turn,
            reply=draft,
            spoken_text=spoken.text,
            pipeline=None,
            twiml=twiml,
        )

    async def handle_speech(
        self, *, shop_id: UUID, speech: SpeechInput
    ) -> VoiceTurnResult:
        from app.saas.quota_context import shop_ai_scope

        with shop_ai_scope(shop_id):
            return await self._handle_speech_inner(shop_id=shop_id, speech=speech)

    async def _handle_speech_inner(
        self, *, shop_id: UUID, speech: SpeechInput
    ) -> VoiceTurnResult:
        import time

        t0 = time.perf_counter()
        call = await self._store.get_call_by_sid(speech.call_sid, shop_id=shop_id)
        if call is None:
            raise ValueError("Call not found for speech input")
        if call.shop_id != shop_id:
            raise ValueError("Shop mismatch for call")

        self._monitor.record_turn()
        now = datetime.now(timezone.utc)

        if speech.interrupted:
            await self._memory.mark_interrupted(shop_id=shop_id, call_id=call.id)
            self._monitor.record_interrupt()

        text = (speech.speech_result or "").strip()
        if not text:
            # Silence timeout — keep listening without hanging up or cluttering the line.
            empties = int((call.metadata or {}).get("empty_gathers") or 0) + 1
            call.metadata = {**(call.metadata or {}), "empty_gathers": empties}
            await self._store.update_call(call)
            if empties >= 2:
                draft = VoiceReplyDraft(
                    text="I'm still here whenever you're ready.",
                    follow_up_question="Go ahead when you're ready.",
                )
                spoken = await self._speech.speak(text=draft.text, synthesize=False)
                assistant_turn = await self._persist_turn(
                    call, role=VoiceTurnRole.ASSISTANT.value, text=spoken.text
                )
                say = spoken.text
            else:
                draft = VoiceReplyDraft(text="", follow_up_question=None)
                assistant_turn = None
                spoken = None
                say = ""
            twiml = self._provider.build_gather_twiml(
                say_text=say,
                action_url=self._action_url(self._gather_action_path),
                barge_in=True,
            )
            return VoiceTurnResult(
                call=call,
                caller_turn=None,
                assistant_turn=assistant_turn,
                reply=draft,
                spoken_text=(spoken.text if spoken else ""),
                pipeline=None,
                twiml=twiml,
            )

        caller_turn = await self._persist_turn(
            call,
            role=VoiceTurnRole.CALLER.value,
            text=text,
            interrupted=speech.interrupted,
        )
        await self._memory.append(shop_id=shop_id, call_id=call.id, turn=caller_turn)
        memory = await self._memory.load(
            shop_id=shop_id, call_id=call.id, caller_phone=call.caller_phone
        )

        if call.human_takeover:
            draft = VoiceReplyDraft(
                text="Someone from the shop is jumping on  -  hang tight one sec.",
                escalate_to_human=True,
                reason="human_takeover",
            )
            twiml = self._provider.build_dial_human_twiml(say_text=draft.text)
            return VoiceTurnResult(
                call=call,
                caller_turn=caller_turn,
                assistant_turn=None,
                reply=draft,
                spoken_text=draft.text,
                pipeline=None,
                twiml=twiml,
            )

        if await self._store.is_shop_ai_paused(shop_id):
            # Caller speech may be recorded above; skip agent/TTS reply.
            notice = (
                "Our phone assistant is paused right now. "
                "Please try again later. Goodbye."
            )
            twiml = self._provider.build_hangup_twiml(say_text=notice)
            draft = VoiceReplyDraft(text=notice, end_call=True, reason="ai_paused")
            return VoiceTurnResult(
                call=call,
                caller_turn=caller_turn,
                assistant_turn=None,
                reply=draft,
                spoken_text=notice,
                pipeline=None,
                twiml=twiml,
            )

        # Reset silence counter on any real speech so mid-call pauses stay quiet.
        if (call.metadata or {}).get("empty_gathers"):
            call.metadata = {**(call.metadata or {}), "empty_gathers": 0}
            await self._store.update_call(call)

        from app.agents.counselor import persona as counselor

        # End when the caller wraps up — or declines the open "anything else?" offer.
        last_assistant = next(
            (
                t.text
                for t in reversed(memory.turns)
                if t.role in {"assistant", "ai", "bot"}
            ),
            None,
        )
        wants_out = counselor.wants_to_end_after_offer(
            text,
            pending_question=memory.pending_question,
            last_assistant_text=last_assistant,
        )
        if wants_out:
            draft = self._reply.farewell()
            spoken = await self._speech.speak(text=draft.text, synthesize=False)
            assistant_turn = await self._persist_turn(
                call, role=VoiceTurnRole.ASSISTANT.value, text=spoken.text
            )
            # Close immediately; summary/extraction off critical path (TwiML must return fast).
            await self.complete_call(
                shop_id=shop_id, call_id=call.id, finalize_in_background=True
            )
            twiml = self._provider.build_hangup_twiml(say_text=spoken.text)
            return VoiceTurnResult(
                call=call,
                caller_turn=caller_turn,
                assistant_turn=assistant_turn,
                reply=draft,
                spoken_text=spoken.text,
                pipeline=None,
                twiml=twiml,
            )

        booking_meta: dict = {}
        if memory.appointment_id:
            booking_meta["appointment_id"] = memory.appointment_id
        if memory.active_visit_start:
            booking_meta["active_visit_start"] = memory.active_visit_start
        if memory.slots_offered:
            booking_meta["slots_offered"] = list(memory.slots_offered)
        if memory.pending_service:
            booking_meta["pending_service"] = memory.pending_service
        if memory.pending_service_id:
            booking_meta["pending_service_id"] = memory.pending_service_id
        if memory.pending_duration_minutes is not None:
            booking_meta["pending_duration_minutes"] = memory.pending_duration_minutes
        if getattr(memory, "pending_service_price", None):
            booking_meta["pending_service_price"] = memory.pending_service_price
        if memory.pending_cancel:
            booking_meta["pending_cancel"] = True
        if memory.pending_action:
            booking_meta["pending_action"] = memory.pending_action
        if memory.pending_question:
            booking_meta["pending_question"] = memory.pending_question
        if memory.pending_preferred_start:
            booking_meta["pending_preferred_start"] = memory.pending_preferred_start
        if memory.pending_preferred_end:
            booking_meta["pending_preferred_end"] = memory.pending_preferred_end
        if memory.pending_time_precision:
            booking_meta["pending_time_precision"] = memory.pending_time_precision
        if memory.pending_needs_date:
            booking_meta["pending_needs_date"] = True
        if memory.pending_needs_time:
            booking_meta["pending_needs_time"] = True

        from app.agents.counselor.shop_name import resolve_shop_name

        # Overlap shop lookup with the agent pipeline (turn latency).
        shop_name_task = asyncio.create_task(resolve_shop_name(shop_id))
        try:
            pipeline = await self._agents.orchestrator.handle_incoming(
                shop_id=shop_id,
                message=RawInboundMessage(
                    channel="phone",
                    content=text,
                    sender_identifier=call.caller_phone,
                    metadata={
                        "call_sid": call.twilio_call_sid,
                        "call_id": str(call.id),
                        "conversation_id": str(call.id),
                        "memory_turns": len(memory.turns),
                        "interrupted": speech.interrupted,
                        **booking_meta,
                    },
                ),
                customer_id=call.customer_id,
                conversation_id=call.id,
            )
        except Exception:
            shop_name_task.cancel()
            raise
        shop_name = await shop_name_task

        intent_val = None
        intent_stage = pipeline.stages.get("intent")
        if intent_stage and intent_stage.data:
            intent_val = intent_stage.data.intent.value
            caller_turn.intent = intent_val

        if pipeline.context.customer_id and not call.customer_id:
            call.customer_id = pipeline.context.customer_id

        customer_name = None
        cust_stage = pipeline.stages.get("customer")
        if cust_stage and cust_stage.data and cust_stage.data.customer:
            customer_name = cust_stage.data.customer.name

        draft = self._reply.generate(
            pipeline=pipeline,
            memory=memory,
            customer_name=customer_name,
            shop_name=shop_name,
        )
        from app.agents.counselor.persona import sanitize_spoken_reply

        draft.text = sanitize_spoken_reply(draft.text)
        spoken = await self._speech.speak(text=draft.text, synthesize=False)
        assistant_turn = await self._persist_turn(
            call,
            role=VoiceTurnRole.ASSISTANT.value,
            text=spoken.text,
            intent=intent_val,
        )
        await self._memory.append(shop_id=shop_id, call_id=call.id, turn=assistant_turn)

        # CRM is not on the Twilio reply critical path.
        self._schedule_crm(
            shop_id=shop_id,
            customer_id=call.customer_id,
            message=f"[call] customer: {text}",
            direction=CommunicationDirection.INCOMING,
        )
        self._schedule_crm(
            shop_id=shop_id,
            customer_id=call.customer_id,
            message=f"[call] assistant: {spoken.text}",
            direction=CommunicationDirection.OUTGOING,
        )

        owner_notified = False
        if draft.escalate_to_human or pipeline.escalate:
            call.escalate = True
            call.status = VoiceCallStatus.ESCALATED.value
            call.escalation_reason = draft.reason or (
                pipeline.supervisor.escalation_reason if pipeline.supervisor else None
            )
            self._monitor.record_escalation(call.escalation_reason)
            owner_notified = await self._notify_owner(call, pipeline)
            twiml = self._provider.build_dial_human_twiml(say_text=spoken.text)
        elif draft.end_call:
            await self.complete_call(
                shop_id=shop_id, call_id=call.id, finalize_in_background=True
            )
            twiml = self._provider.build_hangup_twiml(say_text=spoken.text)
        else:
            call.status = VoiceCallStatus.IN_PROGRESS.value
            twiml = self._provider.build_gather_twiml(
                say_text=spoken.text,
                action_url=self._action_url(self._gather_action_path),
                barge_in=True,
            )

        if draft.follow_up_question:
            await self._memory.update_state(
                shop_id=shop_id,
                call_id=call.id,
                pending_question=draft.follow_up_question,
            )

        sched = pipeline.stages.get("scheduling")
        if sched and sched.data:
            if sched.data.success and sched.data.appointment:
                appt = sched.data.appointment
                visit_start = ""
                if getattr(appt, "start", None) is not None:
                    try:
                        visit_start = appt.start.isoformat()
                    except Exception:  # noqa: BLE001
                        visit_start = str(appt.start)
                await self._memory.update_state(
                    shop_id=shop_id,
                    call_id=call.id,
                    appointment_id=str(appt.id),
                    active_visit_start=visit_start,
                    clear_pending_booking=True,
                )
            elif sched.data.message == "awaiting_cancel_confirmation" or (
                (getattr(sched.data, "metadata", None) or {}).get("action") == "cancel"
                and not (getattr(sched.data, "metadata", None) or {}).get(
                    "no_appointment"
                )
                and not sched.data.success
            ):
                # Pin the appointment being cancelled so YES confirms the right visit.
                hold_cancel_id: str | None = None
                decision = getattr(sched.data, "decision", None)
                if decision is not None and getattr(decision, "appointment_id", None):
                    hold_cancel_id = str(decision.appointment_id)
                if not hold_cancel_id:
                    hold_cancel_id = memory.appointment_id
                await self._memory.update_state(
                    shop_id=shop_id,
                    call_id=call.id,
                    appointment_id=hold_cancel_id,
                    pending_cancel=True,
                    pending_action="cancel",
                )
            elif (
                sched.data.message
                in {
                    "ask_preferred_time",
                    "preferred_time_unavailable",
                    "awaiting_booking_confirmation",
                    "awaiting_reschedule_confirmation",
                    "awaiting_customer_name",
                }
                or (getattr(sched.data, "metadata", None) or {}).get("ask_preferred_time")
                or (getattr(sched.data, "metadata", None) or {}).get(
                    "preferred_time_unavailable"
                )
                or (getattr(sched.data, "metadata", None) or {}).get(
                    "awaiting_confirmation"
                )
                or (
                    sched.data.action == "list_slots"
                    and sched.data.available_slots
                )
            ):
                intent_entities: dict[str, Any] = {}
                if intent_stage and intent_stage.data:
                    intent_entities = dict(intent_stage.data.entities or {})
                service_name = (
                    intent_entities.get("requested_service")
                    or intent_entities.get("service")
                    or memory.pending_service
                )
                service_id = intent_entities.get("service_id") or memory.pending_service_id
                duration = intent_entities.get("duration_minutes")
                if duration is None:
                    duration = memory.pending_duration_minutes
                service_price = intent_entities.get("service_price") or getattr(
                    memory, "pending_service_price", None
                )
                decision = getattr(sched.data, "decision", None)
                hold_appointment_id: str | None = None
                if decision is not None:
                    service_name = getattr(decision, "service_name", None) or service_name
                    if getattr(decision, "service_id", None):
                        service_id = str(decision.service_id)
                    if getattr(decision, "duration_minutes", None):
                        duration = decision.duration_minutes
                    if getattr(decision, "estimated_revenue", None) is not None:
                        service_price = str(decision.estimated_revenue)
                    if getattr(decision, "appointment_id", None):
                        hold_appointment_id = str(decision.appointment_id)
                if not hold_appointment_id:
                    hold_appointment_id = memory.appointment_id
                sched_meta = getattr(sched.data, "metadata", None) or {}
                pending_start = sched_meta.get("pending_slot_start")
                pending_end = sched_meta.get("pending_slot_end")
                if pending_start:
                    offered = [{"start": pending_start, "end": pending_end or pending_start}]
                elif sched.data.available_slots:
                    offered = [
                        {"start": slot.start.isoformat(), "end": slot.end.isoformat()}
                        for slot in sched.data.available_slots[:8]
                    ]
                else:
                    offered = []
                pending_action = str(sched_meta.get("action") or "")
                # Live reschedule intent must not inherit a stale "book" hold.
                # Keep an in-progress reschedule through availability Q&A too.
                if intent_val == "reschedule":
                    pending_action = "reschedule"
                elif (
                    memory.pending_action == "reschedule"
                    and intent_val
                    in {
                        "check_availability",
                        "book_appointment",
                        "other",
                        "maintenance_question",
                    }
                ):
                    pending_action = "reschedule"
                elif pending_action not in {"book", "reschedule"}:
                    pending_action = "book"
                # Only bind appointment_id on reschedule holds — persisting a
                # prior booking id into a new book hold poisons BOOK→RESCHEDULE.
                memory_appointment_id = (
                    hold_appointment_id if pending_action == "reschedule" else None
                )
                if pending_action == "reschedule" and not memory_appointment_id:
                    memory_appointment_id = memory.appointment_id
                pref_start = intent_entities.get("preferred_start")
                pref_end = intent_entities.get("preferred_end")
                pref_precision = intent_entities.get("time_precision")
                needs_date = bool(intent_entities.get("needs_date"))
                needs_time = bool(intent_entities.get("needs_time"))
                # Incomplete: day-only / time-only still collecting the other half.
                incomplete = needs_date or needs_time or pref_precision in {
                    "day",
                    "part_of_day",
                    "time_only",
                }
                # After a full clock pick, stash the still-usable half so the
                # customer only re-answers what failed (date vs time).
                keep_clock = (
                    not incomplete
                    and pref_precision == "clock"
                    and bool(pref_start)
                )
                unavailable = bool(
                    sched_meta.get("preferred_time_unavailable")
                    or sched.data.message == "preferred_time_unavailable"
                )
                aspect = str(sched_meta.get("unavailable_aspect") or "both")
                if aspect not in {"date", "time", "both"}:
                    aspect = "both"
                closed_day = bool(sched_meta.get("closed_day"))
                if (
                    unavailable
                    and aspect == "date"
                    and not keep_clock
                    and (
                        closed_day
                        or pref_precision in {"day", "part_of_day"}
                    )
                ):
                    # Soft day on a closed/full day — do not keep asking for a clock.
                    stash_start = ""
                    stash_end = ""
                    stash_prec = ""
                    stash_needs_date = False
                    stash_needs_time = False
                elif incomplete and pref_start:
                    stash_start = str(pref_start)
                    stash_end = str(pref_end) if pref_end else ""
                    stash_prec = str(pref_precision) if pref_precision else ""
                    stash_needs_date = needs_date
                    stash_needs_time = needs_time
                elif keep_clock and unavailable and aspect == "time":
                    # Day still open — keep day, re-ask clock only.
                    stash_start = str(pref_start)
                    stash_end = str(pref_end) if pref_end else ""
                    stash_prec = "day"
                    stash_needs_date = False
                    stash_needs_time = True
                elif keep_clock and unavailable:
                    # Date closed/full — keep hour only; must re-ask day (not day+time).
                    stash_start = str(pref_start)
                    stash_end = str(pref_end) if pref_end else ""
                    stash_prec = "time_only"
                    stash_needs_date = True
                    stash_needs_time = False
                else:
                    # Held slot / clear path — do not demote a confirmed clock to
                    # time_only or the next turn re-asks day and time.
                    stash_start = ""
                    stash_end = ""
                    stash_prec = ""
                    stash_needs_date = False
                    stash_needs_time = False
                await self._memory.update_state(
                    shop_id=shop_id,
                    call_id=call.id,
                    appointment_id=memory_appointment_id,
                    slots_offered=offered,
                    pending_service=service_name or "",
                    pending_service_id=str(service_id) if service_id else "",
                    pending_duration_minutes=int(duration) if duration else 0,
                    pending_service_price=str(service_price) if service_price else "",
                    pending_cancel=False,
                    pending_action=pending_action,
                    pending_preferred_start=stash_start,
                    pending_preferred_end=stash_end,
                    pending_time_precision=stash_prec,
                    pending_needs_date=stash_needs_date,
                    pending_needs_time=stash_needs_time,
                )

        # Soft book offer ("Want me to book a visit?") — persist the offered
        # service so a following "yes" asks for a time, not the service again.
        if intent_val in {"maintenance_question", "price_question"}:
            intent_entities: dict[str, Any] = {}
            if intent_stage and intent_stage.data:
                intent_entities = dict(intent_stage.data.entities or {})
            soft_service = (
                intent_entities.get("requested_service")
                or intent_entities.get("service")
            )
            if soft_service:
                soft_id = intent_entities.get("service_id")
                soft_duration = intent_entities.get("duration_minutes")
                soft_price = intent_entities.get("service_price")
                await self._memory.update_state(
                    shop_id=shop_id,
                    call_id=call.id,
                    slots_offered=[],
                    pending_service=str(soft_service),
                    pending_service_id=str(soft_id) if soft_id else "",
                    pending_duration_minutes=int(soft_duration) if soft_duration else 0,
                    pending_service_price=str(soft_price) if soft_price else "",
                    pending_cancel=False,
                    pending_action="book",
                )

        call.last_intent = intent_val
        call.owner_summary = pipeline.owner_summary
        await self._store.update_call(call)

        live = await self._store.list_live_calls(shop_id)
        self._monitor.set_live_calls(len(live))

        logger.info(
            "voice.turn call=%s intent=%s escalate=%s latency_ms=%.0f",
            call.id,
            intent_val,
            call.escalate,
            (time.perf_counter() - t0) * 1000,
        )

        return VoiceTurnResult(
            call=call,
            caller_turn=caller_turn,
            assistant_turn=assistant_turn,
            reply=draft,
            spoken_text=spoken.text,
            pipeline=pipeline,
            twiml=twiml,
            owner_notified=owner_notified,
        )

    _TERMINAL_STATUSES = frozenset(
        {
            VoiceCallStatus.COMPLETED.value,
            VoiceCallStatus.FAILED.value,
            VoiceCallStatus.NO_ANSWER.value,
            "no-answer",
            "busy",
            "canceled",
            "cancelled",
        }
    )

    @classmethod
    def _map_twilio_terminal_status(cls, call_status: str | None) -> str | None:
        """Map Twilio CallStatus → stored status. None → default completed."""
        if not call_status:
            return None
        raw = call_status.strip().lower()
        mapping = {
            "completed": VoiceCallStatus.COMPLETED.value,
            "busy": "busy",
            "no-answer": "no-answer",
            "no_answer": "no-answer",
            "failed": VoiceCallStatus.FAILED.value,
            "canceled": "canceled",
            "cancelled": "canceled",
        }
        return mapping.get(raw)

    async def complete_call(
        self,
        *,
        shop_id: UUID,
        call_id: UUID,
        recording_sid: str | None = None,
        recording_url: str | None = None,
        recording_duration_sec: int | None = None,
        final_status: str | None = None,
        finalize_in_background: bool = False,
    ) -> VoiceCall:
        """Mark a call ended and persist summary work.

        Hang-ups must close the row immediately so Conversations leaves Live.
        Heavy summary / repair extraction can run off the path that must return
        TwiML / webhook 200 quickly (``finalize_in_background=True``).
        """
        from app.saas.quota_context import shop_ai_scope

        with shop_ai_scope(shop_id):
            call = await self._store.get_call(shop_id, call_id)
            if call is None:
                raise ValueError("Call not found")

            if recording_sid:
                call.recording_sid = recording_sid
            if recording_url:
                call.recording_url = recording_url
            if recording_duration_sec is not None:
                call.recording_duration_sec = recording_duration_sec

            already_ended = bool(call.ended_at) and (
                call.status in self._TERMINAL_STATUSES
                or call.status == VoiceCallStatus.ESCALATED.value
            )
            first_close = not already_ended

            if first_close:
                call.ended_at = datetime.now(timezone.utc)
                mapped = self._map_twilio_terminal_status(final_status)
                if mapped:
                    call.status = mapped
                elif call.status not in {
                    VoiceCallStatus.ESCALATED.value,
                    VoiceCallStatus.FAILED.value,
                }:
                    call.status = VoiceCallStatus.COMPLETED.value
                await self._store.update_call(call)
                live = await self._store.list_live_calls(shop_id)
                self._monitor.set_live_calls(len(live))
                self._monitor.record_call_completed()
            elif not (recording_sid or recording_url or recording_duration_sec is not None):
                return call
            else:
                await self._store.update_call(call)

            if finalize_in_background and first_close:
                self._schedule_finalize(shop_id=shop_id, call_id=call_id, first_close=True)
                return call

            return await self._finalize_completed_call(
                shop_id=shop_id,
                call_id=call_id,
                first_close=first_close,
            )

    def _schedule_finalize(
        self, *, shop_id: UUID, call_id: UUID, first_close: bool
    ) -> None:
        async def _run() -> None:
            try:
                await self._finalize_completed_call(
                    shop_id=shop_id, call_id=call_id, first_close=first_close
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "voice.complete_call.background_finalize_failed call=%s", call_id
                )

        try:
            asyncio.get_running_loop().create_task(_run())
        except RuntimeError:
            logger.warning(
                "voice.complete_call.no_loop call=%s — skipping background finalize",
                call_id,
            )

    async def _finalize_completed_call(
        self,
        *,
        shop_id: UUID,
        call_id: UUID,
        first_close: bool,
    ) -> VoiceCall:
        from app.saas.quota_context import shop_ai_scope
        from app.saas.usage_tracking import (
            record_voice_usage,
            voice_duration_seconds,
        )

        with shop_ai_scope(shop_id):
            call = await self._store.get_call(shop_id, call_id)
            if call is None:
                raise ValueError("Call not found")

            memory = await self._memory.load(
                shop_id=shop_id, call_id=call.id, caller_phone=call.caller_phone
            )
            transcript = memory.as_transcript()
            # Persist path may outlive process-local memory (API reload) — rehydrate from DB turns.
            if not (transcript or "").strip():
                turns = await self._store.list_turns(shop_id, call.id)
                if turns:
                    lines = [
                        f"{'Caller' if t.role == 'caller' else 'Assistant'}: {t.text}"
                        for t in turns
                        if (t.text or "").strip()
                    ]
                    transcript = "\n".join(lines)
            call.transcript = transcript

            if transcript.strip() and not call.repair_notes:
                try:
                    notes = await self._speech.extract_repair_notes(transcript=transcript)
                    call.repair_notes = {
                        "service": notes.service,
                        "condition": notes.condition,
                        "recommendation": notes.recommendation,
                        "mileage": notes.mileage,
                    }
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "voice.complete_call.repair_notes_failed call=%s", call.id
                    )

            if not call.call_summary:
                call.call_summary = self._build_call_summary(call, transcript)
            if not call.owner_summary:
                call.owner_summary = call.call_summary

            duration_sec = voice_duration_seconds(
                recording_duration_sec=call.recording_duration_sec,
                started_at=call.started_at,
                ended_at=call.ended_at,
            )
            already = int((call.metadata or {}).get("usage_voice_recorded_sec") or 0)
            delta = duration_sec - already
            if delta > 0:
                try:
                    await record_voice_usage(shop_id, delta)
                    call.metadata = {
                        **(call.metadata or {}),
                        "usage_voice_recorded_sec": duration_sec,
                    }
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "voice.complete_call.usage_failed call=%s", call.id
                    )

            await self._store.update_call(call)

            if first_close:
                try:
                    await self._persist_crm(
                        shop_id=shop_id,
                        customer_id=call.customer_id,
                        message=f"[call summary] {call.call_summary}",
                        direction=CommunicationDirection.OUTGOING,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "voice.complete_call.crm_failed call=%s", call.id
                    )

            live = await self._store.list_live_calls(shop_id)
            self._monitor.set_live_calls(len(live))
            return call

    async def complete_call_by_sid(
        self,
        *,
        call_sid: str,
        final_status: str | None = None,
        to_number: str | None = None,
        shop_id: UUID | None = None,
    ) -> VoiceCall | None:
        """Close a live call from Twilio hang-up signals (status / media stream stop)."""
        if not call_sid:
            return None
        resolved_shop = shop_id
        if resolved_shop is None and to_number:
            resolved_shop = await self.resolve_shop_id(to_number)
        call = None
        if resolved_shop is not None:
            call = await self._store.get_call_by_sid(call_sid, shop_id=resolved_shop)
        if call is None:
            # Stream-stop / misconfigured status may omit To — non-fatal miss.
            call = await self._store.get_call_by_sid(call_sid)
        if call is None:
            logger.warning("voice.complete_by_sid.miss sid=%s", call_sid)
            return None
        if call.ended_at and call.status in self._TERMINAL_STATUSES:
            return call
        return await self.complete_call(
            shop_id=call.shop_id,
            call_id=call.id,
            final_status=final_status,
            finalize_in_background=True,
        )

    def _schedule_crm(
        self,
        *,
        shop_id: UUID,
        customer_id: UUID | None,
        message: str,
        direction: CommunicationDirection,
    ) -> None:
        if customer_id is None or self._uow_factory is None:
            return

        async def _run() -> None:
            await self._persist_crm(
                shop_id=shop_id,
                customer_id=customer_id,
                message=message,
                direction=direction,
            )

        try:
            asyncio.get_running_loop().create_task(_run())
        except RuntimeError:
            pass

    async def set_human_takeover(
        self, *, shop_id: UUID, call_id: UUID, enabled: bool
    ) -> VoiceCall:
        call = await self._store.get_call(shop_id, call_id)
        if call is None:
            raise ValueError("Call not found")
        call.human_takeover = enabled
        if enabled:
            call.status = VoiceCallStatus.ESCALATED.value
            await self._notify_owner(call, None)
        await self._store.update_call(call)
        return call

    async def delete_call(self, *, shop_id: UUID, call_id: UUID) -> None:
        call = await self._store.get_call(shop_id, call_id)
        if call is None:
            raise ValueError("Call not found")
        deleted = await self._store.delete_call(shop_id, call_id)
        if not deleted:
            raise ValueError("Call not found")
        live = await self._store.list_live_calls(shop_id)
        self._monitor.set_live_calls(len(live))

    async def store_recording_metadata(
        self,
        *,
        call_sid: str,
        recording_sid: str,
        recording_url: str,
        duration_sec: int | None = None,
    ) -> VoiceCall | None:
        from app.saas.usage_tracking import record_voice_usage, voice_duration_seconds

        call = await self._store.get_call_by_sid(call_sid)
        if call is None:
            return None
        call.recording_sid = recording_sid
        call.recording_url = recording_url
        call.recording_duration_sec = duration_sec
        meta = dict(call.metadata or {})
        meta["recording"] = {
            "sid": recording_sid,
            "url": recording_url,
            "duration_sec": duration_sec,
        }
        duration = voice_duration_seconds(
            recording_duration_sec=duration_sec,
            started_at=call.started_at,
            ended_at=call.ended_at,
        )
        already = int(meta.get("usage_voice_recorded_sec") or 0)
        delta = duration - already
        if delta > 0:
            await record_voice_usage(call.shop_id, delta)
            meta["usage_voice_recorded_sec"] = duration
        call.metadata = meta
        return await self._store.update_call(call)

    def _build_call_summary(self, call: VoiceCall, transcript: str) -> str:
        parts = [
            f"Call with {call.caller_phone}.",
            f"Status: {call.status}.",
        ]
        if call.last_intent:
            parts.append(f"Last intent: {call.last_intent}.")
        if call.escalate:
            parts.append(f"Escalated: {call.escalation_reason or 'yes'}.")
        if call.repair_notes:
            parts.append(
                "Repair notes: "
                f"{call.repair_notes.get('service')}  -  {call.repair_notes.get('condition')}."
            )
        turn_count = transcript.count("\n") + 1 if transcript else 0
        parts.append(f"Turns: {turn_count}.")
        return " ".join(parts)

    async def _persist_turn(
        self,
        call: VoiceCall,
        *,
        role: str,
        text: str,
        intent: str | None = None,
        interrupted: bool = False,
    ) -> VoiceTurn:
        turn = VoiceTurn(
            id=uuid4(),
            call_id=call.id,
            shop_id=call.shop_id,
            role=role,
            text=text,
            intent=intent,
            interrupted=interrupted,
            created_at=datetime.now(timezone.utc),
        )
        return await self._store.add_turn(turn)

    async def _persist_crm(
        self,
        *,
        shop_id: UUID,
        customer_id: UUID | None,
        message: str,
        direction: CommunicationDirection,
    ) -> None:
        if customer_id is None or self._uow_factory is None:
            return
        try:
            uow: UnitOfWork = self._uow_factory()
            await uow.bind_shop(shop_id)
            await uow.communications.add(
                CommunicationHistory(
                    id=uuid4(),
                    shop_id=shop_id,
                    customer_id=customer_id,
                    channel=CommunicationChannel.PHONE,
                    message=message,
                    direction=direction,
                )
            )
            await uow.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice.crm_persist_failed: %s", exc)

    async def _notify_owner(
        self, call: VoiceCall, pipeline: PipelineResult | None
    ) -> bool:
        payload = {
            "call_id": str(call.id),
            "caller_phone": call.caller_phone,
            "reason": call.escalation_reason,
            "owner_summary": call.owner_summary
            or (pipeline.owner_summary if pipeline else None),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self._owner_notifications.append(payload)
        self._monitor.record_owner_notification()
        if self._owner_notifier:
            try:
                await self._owner_notifier(payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning("voice.owner_notify_failed: %s", exc)
                return False
        logger.info("voice.owner_notified call=%s reason=%s", call.id, call.escalation_reason)
        return True
