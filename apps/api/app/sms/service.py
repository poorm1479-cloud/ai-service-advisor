"""SMS AI service — Twilio ingress → agent framework → contextual reply → CRM."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.agents.base.agent import AgentContext
from app.agents.communication.models import RawInboundMessage
from app.agents.factory import AgentRuntime
from app.agents.orchestrator import PipelineResult
from app.domain.enums import CommunicationChannel, CommunicationDirection
from app.domain.entities import CommunicationHistory
from app.domain.repositories import UnitOfWork
from app.sms.enums import SmsConversationStatus, SmsMessageDirection
from app.sms.memory import ConversationMemoryPort, ConversationTurn
from app.sms.models import InboundSms, OutboundSms, SmsConversation, SmsJob, SmsMessage
from app.sms.monitoring import SmsMonitor
from app.sms.queue import MessageQueuePort
from app.sms.reply import ContextualReplyGenerator, ReplyDraft
from app.sms.store import SmsStorePort, normalize_phone
from app.sms.twilio.provider import SmsProviderPort

logger = logging.getLogger("asa.sms.service")


@dataclass(slots=True)
class SmsProcessResult:
    conversation: SmsConversation
    inbound: SmsMessage
    outbound: SmsMessage | None
    reply: ReplyDraft
    pipeline: PipelineResult
    owner_summary: str | None


class SmsAiService:
    """Production SMS brain — concurrent conversations, memory, escalation, CRM."""

    def __init__(
        self,
        *,
        agents: AgentRuntime,
        store: SmsStorePort,
        memory: ConversationMemoryPort,
        provider: SmsProviderPort,
        queue: MessageQueuePort,
        monitor: SmsMonitor,
        reply_generator: ContextualReplyGenerator | None = None,
        default_from_number: str = "",
        shop_number_map: dict[str, UUID] | None = None,
        uow_factory: Any | None = None,
    ) -> None:
        self._agents = agents
        self._store = store
        self._memory = memory
        self._provider = provider
        self._queue = queue
        self._monitor = monitor
        self._reply = reply_generator or ContextualReplyGenerator()
        self._from_number = default_from_number
        self._shop_number_map = {
            normalize_phone(k): v for k, v in (shop_number_map or {}).items()
        }
        self._uow_factory = uow_factory

    async def resolve_shop_id(self, to_number: str) -> UUID | None:
        phone = normalize_phone(to_number)
        if phone in self._shop_number_map:
            return self._shop_number_map[phone]
        return await self._store.find_shop_id_by_sms_number(phone)

    async def enqueue_inbound(self, inbound: InboundSms, *, shop_id: UUID | None = None) -> SmsJob:
        resolved = shop_id or await self.resolve_shop_id(inbound.to_number)
        return await self._queue.enqueue(
            shop_id=resolved,
            payload={
                "type": "inbound_sms",
                "from": inbound.from_number,
                "to": inbound.to_number,
                "body": inbound.body,
                "message_sid": inbound.message_sid,
                "account_sid": inbound.account_sid,
            },
        )

    async def process_job(self, job: SmsJob) -> SmsProcessResult | None:
        if job.payload.get("type") != "inbound_sms":
            return None
        shop_id = job.shop_id
        if shop_id is None:
            shop_id = await self.resolve_shop_id(str(job.payload.get("to", "")))
        if shop_id is None:
            raise ValueError("Unable to resolve shop for inbound SMS")
        inbound = InboundSms(
            from_number=str(job.payload["from"]),
            to_number=str(job.payload["to"]),
            body=str(job.payload.get("body", "")),
            message_sid=job.payload.get("message_sid"),
            account_sid=job.payload.get("account_sid"),
        )
        return await self.process_inbound(shop_id=shop_id, inbound=inbound)

    async def process_inbound(
        self, *, shop_id: UUID, inbound: InboundSms
    ) -> SmsProcessResult:
        self._monitor.record_inbound()
        phone = normalize_phone(inbound.from_number)
        now = datetime.now(timezone.utc)

        # Idempotency: Twilio retries with the same MessageSid must not re-run AI.
        if inbound.message_sid:
            existing = await self._store.find_message_by_twilio_sid(
                inbound.message_sid, shop_id=shop_id
            )
            if existing is None:
                existing = await self._store.find_message_by_twilio_sid(
                    inbound.message_sid
                )
            if existing is not None:
                conversation = await self._store.get_conversation(shop_id, existing.conversation_id)
                if conversation is None:
                    conversation = await self._store.get_or_create_conversation(
                        shop_id=shop_id, customer_phone=phone
                    )
                draft = ReplyDraft(body="", send=False, reason="duplicate_sid")
                empty_pipeline = PipelineResult(
                    correlation_id=str(uuid4()),
                    success=True,
                    escalate=False,
                    context=AgentContext(shop_id=shop_id, customer_id=conversation.customer_id),
                )
                return SmsProcessResult(
                    conversation=conversation,
                    inbound=existing,
                    outbound=None,
                    reply=draft,
                    pipeline=empty_pipeline,
                    owner_summary=conversation.owner_summary or "Duplicate webhook ignored.",
                )

        conversation = await self._store.get_or_create_conversation(
            shop_id=shop_id,
            customer_phone=phone,
        )

        shop_ai_paused = await self._store.is_shop_ai_paused(shop_id)

        # Human takeover / shop AI pause — record inbound only, no AI reply
        if conversation.human_takeover or shop_ai_paused:
            inbound_msg = await self._persist_inbound(
                conversation, inbound, now, intent=None
            )
            await self._memory.append(
                shop_id=shop_id,
                customer_phone=phone,
                conversation_id=conversation.id,
                turn=ConversationTurn(role="customer", content=inbound.body, at=now),
            )
            conversation.reply_preview = None
            if shop_ai_paused and not conversation.human_takeover:
                conversation.owner_summary = (
                    conversation.owner_summary
                    or "Shop AI paused — inbound recorded, no auto-reply."
                )
                reason = "ai_paused"
            else:
                conversation.owner_summary = (
                    conversation.owner_summary
                    or "Human takeover active — AI replies paused."
                )
                reason = "human_takeover"
            await self._store.update_conversation(conversation)
            draft = ReplyDraft(body="", send=False, reason=reason)
            empty_pipeline = PipelineResult(
                correlation_id=str(uuid4()),
                success=True,
                escalate=False,
                context=AgentContext(shop_id=shop_id, customer_id=conversation.customer_id),
            )
            return SmsProcessResult(
                conversation=conversation,
                inbound=inbound_msg,
                outbound=None,
                reply=draft,
                pipeline=empty_pipeline,
                owner_summary=conversation.owner_summary,
            )

        memory = await self._memory.load(
            shop_id=shop_id,
            customer_phone=phone,
            conversation_id=conversation.id,
        )

        # Enrich message with memory for intent (optional prefix)
        content = inbound.body
        if memory.turns:
            # Agents still see the latest message; memory used for reply context
            pass

        booking_meta: dict[str, Any] = {}
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

        pipeline = await self._agents.orchestrator.handle_incoming(
            shop_id=shop_id,
            message=RawInboundMessage(
                channel="sms",
                content=content,
                sender_identifier=phone,
                metadata={
                    "twilio_sid": inbound.message_sid,
                    "to": inbound.to_number,
                    "memory_turns": len(memory.turns),
                    "conversation_id": str(conversation.id),
                    "sms_conversation_id": str(conversation.id),
                    **booking_meta,
                },
            ),
            customer_id=conversation.customer_id,
            conversation_id=conversation.id,
        )

        intent_val = None
        intent_stage = pipeline.stages.get("intent")
        if intent_stage and intent_stage.data:
            intent_val = intent_stage.data.intent.value

        if pipeline.context.customer_id and not conversation.customer_id:
            conversation.customer_id = pipeline.context.customer_id

        customer_name = None
        cust_stage = pipeline.stages.get("customer")
        if cust_stage and cust_stage.data and cust_stage.data.customer:
            customer_name = cust_stage.data.customer.name

        await self._memory.append(
            shop_id=shop_id,
            customer_phone=phone,
            conversation_id=conversation.id,
            turn=ConversationTurn(
                role="customer",
                content=inbound.body,
                intent=intent_val,
                at=now,
            ),
        )

        from app.agents.counselor.shop_name import resolve_shop_name

        shop_name = await resolve_shop_name(shop_id)
        draft = self._reply.generate(
            pipeline=pipeline,
            memory=memory,
            customer_name=customer_name,
            shop_name=shop_name,
        )
        from app.agents.counselor.persona import sanitize_spoken_reply

        draft.body = sanitize_spoken_reply(draft.body)

        inbound_msg = await self._persist_inbound(
            conversation, inbound, now, intent=intent_val
        )

        # Scheduling metrics + persist offered service/slots for multi-turn booking
        sched = pipeline.stages.get("scheduling")
        if sched and sched.data:
            if sched.data.success:
                self._monitor.record_appointment(sched.data.action)
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
                    customer_phone=phone,
                    appointment_id=str(appt.id),
                    active_visit_start=visit_start,
                    clear_pending_booking=True,
                    conversation_id=conversation.id,
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
                    customer_phone=phone,
                    appointment_id=hold_cancel_id,
                    pending_cancel=True,
                    pending_action="cancel",
                    conversation_id=conversation.id,
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
                # Prefer catalog fields from the scheduling decision when present.
                decision = getattr(sched.data, "decision", None)
                hold_appointment_id: str | None = None
                if decision is not None:
                    service_name = getattr(decision, "service_name", None) or service_name
                    if getattr(decision, "service_id", None):
                        service_id = str(decision.service_id)
                    if getattr(decision, "duration_minutes", None):
                        duration = decision.duration_minutes
                    if getattr(decision, "appointment_id", None):
                        hold_appointment_id = str(decision.appointment_id)
                if not hold_appointment_id:
                    hold_appointment_id = memory.appointment_id
                sched_meta = getattr(sched.data, "metadata", None) or {}
                pending_start = sched_meta.get("pending_slot_start")
                pending_end = sched_meta.get("pending_slot_end")
                if pending_start:
                    # Narrow to the confirmed candidate so YES books that slot.
                    offered = [{"start": pending_start, "end": pending_end or pending_start}]
                elif sched.data.available_slots:
                    offered = [
                        {
                            "start": slot.start.isoformat(),
                            "end": slot.end.isoformat(),
                        }
                        for slot in sched.data.available_slots[:8]
                    ]
                else:
                    # Asking for a preferred time — keep service, clear prior offers.
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
                    customer_phone=phone,
                    appointment_id=memory_appointment_id,
                    slots_offered=offered,
                    pending_service=service_name or "",
                    pending_service_id=str(service_id) if service_id else "",
                    pending_duration_minutes=int(duration) if duration else 0,
                    pending_cancel=False,
                    pending_action=pending_action,
                    pending_preferred_start=stash_start,
                    pending_preferred_end=stash_end,
                    pending_time_precision=stash_prec,
                    pending_needs_date=stash_needs_date,
                    pending_needs_time=stash_needs_time,
                    conversation_id=conversation.id,
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
                await self._memory.update_state(
                    shop_id=shop_id,
                    customer_phone=phone,
                    slots_offered=[],
                    pending_service=str(soft_service),
                    pending_service_id=str(soft_id) if soft_id else "",
                    pending_duration_minutes=int(soft_duration) if soft_duration else 0,
                    pending_cancel=False,
                    pending_action="book",
                    conversation_id=conversation.id,
                )

        outbound_msg: SmsMessage | None = None
        if (
            draft.send
            and draft.body
            and not conversation.human_takeover
            and not await self._store.is_shop_ai_paused(shop_id)
        ):
            from app.saas.quotas import QuotaService

            await QuotaService().consume(shop_id, "sms", 1)
            sid = await self._provider.send(
                OutboundSms(
                    to_number=phone,
                    from_number=inbound.to_number or self._from_number,
                    body=draft.body,
                    conversation_id=conversation.id,
                )
            )
            from app.saas.usage_tracking import record_sms_usage

            await record_sms_usage(shop_id, count=1)
            self._monitor.record_outbound()
            outbound_msg = await self._store.add_message(
                SmsMessage(
                    id=uuid4(),
                    conversation_id=conversation.id,
                    shop_id=shop_id,
                    direction=SmsMessageDirection.OUTBOUND.value,
                    body=draft.body,
                    twilio_sid=sid,
                    intent=intent_val,
                    created_at=datetime.now(timezone.utc),
                )
            )
            await self._memory.append(
                shop_id=shop_id,
                customer_phone=phone,
                conversation_id=conversation.id,
                turn=ConversationTurn(
                    role="assistant",
                    content=draft.body,
                    intent=intent_val,
                    at=datetime.now(timezone.utc),
                ),
            )
            await self._persist_crm_communication(
                shop_id=shop_id,
                customer_id=conversation.customer_id,
                message=draft.body,
                direction=CommunicationDirection.OUTGOING,
            )

        await self._persist_crm_communication(
            shop_id=shop_id,
            customer_id=conversation.customer_id,
            message=inbound.body,
            direction=CommunicationDirection.INCOMING,
        )

        if draft.follow_up_question:
            await self._memory.update_state(
                shop_id=shop_id,
                customer_phone=phone,
                pending_question=draft.follow_up_question,
                conversation_id=conversation.id,
            )
        else:
            await self._memory.update_state(
                shop_id=shop_id,
                customer_phone=phone,
                pending_question="",
                conversation_id=conversation.id,
            )

        if pipeline.escalate:
            self._monitor.record_escalation(
                pipeline.supervisor.escalation_reason if pipeline.supervisor else None
            )
            conversation.status = SmsConversationStatus.ESCALATED.value
            conversation.escalate = True
            conversation.escalation_reason = (
                pipeline.supervisor.escalation_reason if pipeline.supervisor else draft.reason
            )
        else:
            conversation.status = SmsConversationStatus.WAITING_CUSTOMER.value
            conversation.escalate = False

        conversation.last_intent = intent_val
        conversation.reply_preview = draft.body
        conversation.owner_summary = pipeline.owner_summary
        conversation.last_message_at = datetime.now(timezone.utc)
        await self._store.update_conversation(conversation)

        active = await self._store.list_conversations(
            shop_id, status=SmsConversationStatus.ACTIVE.value
        )
        waiting = await self._store.list_conversations(
            shop_id, status=SmsConversationStatus.WAITING_CUSTOMER.value
        )
        escalated = await self._store.list_conversations(
            shop_id, status=SmsConversationStatus.ESCALATED.value
        )
        self._monitor.set_active_conversations(len(active) + len(waiting) + len(escalated))

        logger.info(
            "sms.processed conversation=%s intent=%s escalate=%s",
            conversation.id,
            intent_val,
            pipeline.escalate,
        )

        return SmsProcessResult(
            conversation=conversation,
            inbound=inbound_msg,
            outbound=outbound_msg,
            reply=draft,
            pipeline=pipeline,
            owner_summary=pipeline.owner_summary,
        )

    async def set_human_takeover(
        self, *, shop_id: UUID, conversation_id: UUID, enabled: bool
    ) -> SmsConversation:
        conv = await self._store.get_conversation(shop_id, conversation_id)
        if conv is None:
            raise ValueError("Conversation not found")
        conv.human_takeover = enabled
        conv.status = (
            SmsConversationStatus.WAITING_HUMAN.value
            if enabled
            else SmsConversationStatus.ACTIVE.value
        )
        if enabled:
            conv.owner_summary = (conv.owner_summary or "") + " | Human takeover enabled"
        return await self._store.update_conversation(conv)

    async def delete_conversation(self, *, shop_id: UUID, conversation_id: UUID) -> None:
        conv = await self._store.get_conversation(shop_id, conversation_id)
        if conv is None:
            raise ValueError("Conversation not found")
        deleted = await self._store.delete_conversation(shop_id, conversation_id)
        if not deleted:
            raise ValueError("Conversation not found")
        await self._memory.clear(shop_id=shop_id, customer_phone=conv.customer_phone)

    async def mirror_outbound(
        self,
        *,
        shop_id: UUID,
        to_phone: str,
        body: str,
        customer_id: UUID | None = None,
        twilio_sid: str | None = None,
        intent: str | None = None,
        owner_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SmsMessage:
        """Record an outbound SMS into the inbox without sending via provider.

        Used when another subsystem (e.g. marketing) already dispatched the message
        and Conversations should reflect it.
        """
        now = datetime.now(timezone.utc)
        conv = await self._store.get_or_create_conversation(
            shop_id=shop_id,
            customer_phone=to_phone,
            customer_id=customer_id,
        )
        msg = await self._store.add_message(
            SmsMessage(
                id=uuid4(),
                conversation_id=conv.id,
                shop_id=shop_id,
                direction=SmsMessageDirection.OUTBOUND.value,
                body=body,
                twilio_sid=twilio_sid,
                intent=intent,
                created_at=now,
                metadata=dict(metadata or {}),
            )
        )
        conv.reply_preview = body
        conv.last_message_at = now
        if intent:
            conv.last_intent = intent
        if owner_summary:
            conv.owner_summary = owner_summary
        if customer_id and not conv.customer_id:
            conv.customer_id = customer_id
        await self._store.update_conversation(conv)
        await self._memory.append(
            shop_id=shop_id,
            customer_phone=conv.customer_phone,
            conversation_id=conv.id,
            turn=ConversationTurn(role="assistant", content=body, intent=intent, at=now),
        )
        await self._persist_crm_communication(
            shop_id=shop_id,
            customer_id=conv.customer_id,
            message=body,
            direction=CommunicationDirection.OUTGOING,
        )
        self._monitor.record_outbound()
        return msg

    async def send_manual_reply(
        self, *, shop_id: UUID, conversation_id: UUID, body: str, from_number: str | None = None
    ) -> SmsMessage:
        conv = await self._store.get_conversation(shop_id, conversation_id)
        if conv is None:
            raise ValueError("Conversation not found")
        from app.saas.quotas import QuotaService

        await QuotaService().consume(shop_id, "sms", 1)
        sid = await self._provider.send(
            OutboundSms(
                to_number=conv.customer_phone,
                from_number=from_number or self._from_number,
                body=body,
                conversation_id=conv.id,
            )
        )
        from app.saas.usage_tracking import record_sms_usage

        await record_sms_usage(shop_id, count=1)
        self._monitor.record_outbound()
        msg = await self._store.add_message(
            SmsMessage(
                id=uuid4(),
                conversation_id=conv.id,
                shop_id=shop_id,
                direction=SmsMessageDirection.OUTBOUND.value,
                body=body,
                twilio_sid=sid,
                created_at=datetime.now(timezone.utc),
            )
        )
        await self._memory.append(
            shop_id=shop_id,
            customer_phone=conv.customer_phone,
            conversation_id=conv.id,
            turn=ConversationTurn(role="assistant", content=body, at=datetime.now(timezone.utc)),
        )
        await self._persist_crm_communication(
            shop_id=shop_id,
            customer_id=conv.customer_id,
            message=body,
            direction=CommunicationDirection.OUTGOING,
        )
        conv.reply_preview = body
        conv.last_message_at = datetime.now(timezone.utc)
        await self._store.update_conversation(conv)
        return msg

    async def _persist_inbound(
        self,
        conversation: SmsConversation,
        inbound: InboundSms,
        now: datetime,
        *,
        intent: str | None,
    ) -> SmsMessage:
        return await self._store.add_message(
            SmsMessage(
                id=uuid4(),
                conversation_id=conversation.id,
                shop_id=conversation.shop_id,
                direction=SmsMessageDirection.INBOUND.value,
                body=inbound.body,
                twilio_sid=inbound.message_sid,
                intent=intent,
                created_at=now,
            )
        )

    async def _persist_crm_communication(
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
                    channel=CommunicationChannel.SMS,
                    message=message,
                    direction=direction,
                )
            )
            await uow.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("sms.crm_persist_failed: %s", exc)
