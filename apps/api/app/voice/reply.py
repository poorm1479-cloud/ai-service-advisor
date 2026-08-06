"""Spoken reply drafting for phone conversations."""

from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass

from app.agents.counselor import persona as counselor
from app.agents.intent.models import CustomerIntent
from app.agents.orchestrator import PipelineResult
from app.voice.memory import CallMemorySnapshot


@dataclass(slots=True)
class VoiceReplyDraft:
    text: str
    follow_up_question: str | None = None
    escalate_to_human: bool = False
    end_call: bool = False
    reason: str | None = None


def _parse_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt
        except ValueError:
            return None
    return None


class VoiceReplyGenerator:
    """Short, speakable replies grounded in agent outputs + call memory."""

    def greeting(
        self,
        *,
        customer_name: str | None = None,
        shop_name: str | None = None,
    ) -> VoiceReplyDraft:
        return VoiceReplyDraft(
            text=counselor.greeting(
                shop_name=shop_name,
                customer_name=counselor.spoken_first_name(customer_name) or None,
            ),
            follow_up_question=counselor.ask_purpose(),
        )

    def generate(
        self,
        *,
        pipeline: PipelineResult,
        memory: CallMemorySnapshot,
        customer_name: str | None = None,
        shop_name: str | None = None,
    ) -> VoiceReplyDraft:
        # Speak only real names — never CRM placeholders / false extractions (e.g. Going).
        name = counselor.spoken_first_name(customer_name) or None
        # Address by name only on the first AI turn (opening); later turns skip it.
        is_first_reply = not any(t.role == "assistant" for t in memory.turns)
        address_name = name if is_first_reply else None
        _ = shop_name  # reserved for future persona injection in mid-call turns
        meta = pipeline.context.metadata or {}
        snapshot = meta.get("customer_snapshot") or {}

        if pipeline.escalate:
            who = f"{address_name}, hang tight — " if address_name else "Hang tight — "
            return VoiceReplyDraft(
                text=(
                    f"{who}I'm grabbing someone from the shop who can help. "
                    "Stay with me one sec."
                ),
                escalate_to_human=True,
                reason=(
                    pipeline.supervisor.escalation_reason
                    if pipeline.supervisor
                    else "escalation"
                ),
            )

        intent_stage = pipeline.stages.get("intent")
        intent = intent_stage.data.intent if intent_stage and intent_stage.data else None
        entities = (
            intent_stage.data.entities
            if intent_stage and intent_stage.data
            else {}
        )
        service_name = (
            entities.get("requested_service")
            or entities.get("service")
            or memory.pending_service
        )
        scheduling = pipeline.stages.get("scheduling")
        sched = scheduling.data if scheduling else None
        revenue = pipeline.stages.get("revenue")
        rev = revenue.data if revenue else None
        if sched and getattr(sched, "appointment", None):
            service_name = getattr(sched.appointment, "service_name", None) or service_name
        decision = getattr(sched, "decision", None) if sched else None
        if decision is not None:
            service_name = getattr(decision, "service_name", None) or service_name

        candidates = list(entities.get("service_candidates") or [])
        if entities.get("service_needs_disambiguation") and candidates:
            return VoiceReplyDraft(
                text=counselor.offer_service_candidates(
                    candidates, customer_name=address_name
                ),
                follow_up_question="Which service?",
            )

        last_customer = next(
            (
                t.text
                for t in reversed(memory.turns)
                if t.role in {"caller", "customer", "user"}
            ),
            "",
        )

        # Already booked this turn — confirm before asking for missing fields.
        if (
            intent == CustomerIntent.BOOK_APPOINTMENT
            and sched
            and sched.success
            and sched.appointment
        ):
            return VoiceReplyDraft(
                text=counselor.summarize_done(
                    action="book",
                    customer_name=address_name,
                    service_name=service_name,
                    when=sched.appointment.start,
                ),
                end_call=True,
            )

        needs_name = counselor.needs_customer_name(
            customer_name or snapshot.get("name")
        )

        # Booking without a service → ask which service first (before day/time).
        # Time-change phrasing must not fall into this (keep existing service).
        if (
            intent == CustomerIntent.BOOK_APPOINTMENT
            and not service_name
            and not counselor.looks_like_reschedule_desire(last_customer)
        ):
            return VoiceReplyDraft(
                text=counselor.ask_service(customer_name=address_name),
                follow_up_question="What service do you need?",
            )

        # Misclassified BOOK that is actually a time change → ask for new time.
        if (
            intent == CustomerIntent.BOOK_APPOINTMENT
            and not service_name
            and counselor.looks_like_reschedule_desire(last_customer)
        ):
            return VoiceReplyDraft(
                text=counselor.summarize_reschedule_confirm(
                    customer_name=address_name,
                    service_name=service_name,
                    when=None,
                ),
                follow_up_question="New day and time?",
            )

        # Customer answered the open purpose question with a booking desire.
        # Skip for reschedule/cancel — those keep the existing service and ask for time.
        if (
            not service_name
            and intent
            not in {
                CustomerIntent.RESCHEDULE,
                CustomerIntent.CANCEL_APPOINTMENT,
            }
            and counselor.looks_like_booking_desire(last_customer)
            and (
                counselor.is_purpose_question(memory.pending_question)
                or intent
                in {
                    CustomerIntent.OTHER,
                    CustomerIntent.NEW_CUSTOMER,
                    CustomerIntent.RETURNING_CUSTOMER,
                }
            )
        ):
            return VoiceReplyDraft(
                text=counselor.ask_service(customer_name=address_name),
                follow_up_question="What service do you need?",
            )

        # Vague ("anytime"), day-only ("Friday"), or part-of-day ("morning") —
        # ask for a concrete clock time; only list openings on availability asks.
        # Reschedule/cancel keep their own paths (acknowledge change, ask new time).
        if (
            intent
            not in {
                CustomerIntent.RESCHEDULE,
                CustomerIntent.CANCEL_APPOINTMENT,
            }
            and (entities.get("vague_time") or entities.get("needs_time"))
        ):
            if intent == CustomerIntent.CHECK_AVAILABILITY and sched and sched.available_slots:
                ranges = [
                    (slot.start, getattr(slot, "end", None))
                    for slot in sched.available_slots[:3]
                ]
                return VoiceReplyDraft(
                    text=counselor.offer_slots_spoken(
                        ranges,
                        customer_name=address_name,
                        service_name=service_name,
                    ),
                    follow_up_question="Which time works?",
                )
            return VoiceReplyDraft(
                text=counselor.ask_time(
                    customer_name=address_name, service_name=service_name
                ),
                follow_up_question="Preferred day and time?",
            )

        if intent in {
            CustomerIntent.CHECK_AVAILABILITY,
            CustomerIntent.BOOK_APPOINTMENT,
        }:
            sched_meta = (getattr(sched, "metadata", None) or {}) if sched else {}
            sched_message = getattr(sched, "message", None) if sched else None
            if (
                sched_message == "preferred_time_unavailable"
                or sched_meta.get("preferred_time_unavailable")
            ):
                preferred = _parse_dt(entities.get("preferred_start")) or _parse_dt(
                    sched_meta.get("preferred_start")
                )
                return VoiceReplyDraft(
                    text=counselor.time_unavailable(
                        preferred, customer_name=address_name
                    ),
                    follow_up_question="What other day or time works?",
                )
            pending_when = _parse_dt(
                sched_meta.get("pending_slot_start")
            ) or _parse_dt(getattr(decision, "recommended_slot_start", None))
            # New / unnamed customers: ask for a name before the final confirm.
            if (
                intent == CustomerIntent.BOOK_APPOINTMENT
                and service_name
                and pending_when
                and needs_name
                and (
                    sched_message
                    in {
                        "awaiting_booking_confirmation",
                        "awaiting_customer_name",
                    }
                    or sched_meta.get("awaiting_confirmation")
                    or sched_meta.get("awaiting_customer_name")
                )
            ):
                ask = counselor.ask_name()
                return VoiceReplyDraft(
                    text=ask,
                    follow_up_question=ask,
                )
            # Only confirm a slot scheduling actually held — never echo a raw
            # preferred clock time just because other openings exist.
            if (
                intent == CustomerIntent.BOOK_APPOINTMENT
                and service_name
                and pending_when
                and sched
                and (
                    sched_message == "awaiting_booking_confirmation"
                    or sched_meta.get("awaiting_confirmation")
                )
                and not needs_name
            ):
                return VoiceReplyDraft(
                    text=counselor.summarize_booking_confirm(
                        customer_name=address_name,
                        service_name=service_name,
                        when=pending_when,
                    ),
                    follow_up_question="Should I book that?",
                )
            if intent == CustomerIntent.CHECK_AVAILABILITY:
                if sched and sched.available_slots:
                    ranges = [
                        (slot.start, getattr(slot, "end", None))
                        for slot in sched.available_slots[:3]
                    ]
                    return VoiceReplyDraft(
                        text=counselor.offer_slots_spoken(
                            ranges,
                            customer_name=address_name,
                            service_name=service_name,
                        ),
                        follow_up_question="Which time works?",
                    )
                who = f"{address_name}, " if address_name else ""
                return VoiceReplyDraft(
                    text=(
                        f"{who}I'm not seeing openings in the next week. "
                        "Want me to look at another day?"
                    ),
                    follow_up_question="Another day?",
                )
            return VoiceReplyDraft(
                text=counselor.ask_time(
                    customer_name=address_name, service_name=service_name
                ),
                follow_up_question="Preferred day and time?",
            )

        if intent == CustomerIntent.RESCHEDULE:
            if sched and sched.success and sched.appointment:
                return VoiceReplyDraft(
                    text=counselor.summarize_done(
                        action="reschedule",
                        customer_name=address_name,
                        service_name=service_name,
                        when=sched.appointment.start,
                    ),
                    end_call=True,
                )
            sched_meta = (getattr(sched, "metadata", None) or {}) if sched else {}
            sched_message = getattr(sched, "message", None) if sched else None
            if (
                sched_message == "preferred_time_unavailable"
                or sched_meta.get("preferred_time_unavailable")
            ):
                preferred = _parse_dt(entities.get("preferred_start")) or _parse_dt(
                    sched_meta.get("preferred_start")
                )
                return VoiceReplyDraft(
                    text=counselor.time_unavailable(
                        preferred, customer_name=address_name
                    ),
                    follow_up_question="What other day or time works?",
                )
            pending_when = _parse_dt(
                sched_meta.get("pending_slot_start")
            ) or _parse_dt(getattr(decision, "recommended_slot_start", None))
            has_preference = bool(
                entities.get("preferred_start")
                or entities.get("prefer_earliest")
                or entities.get("prefer_latest")
            )
            customer_chose_clock = (
                has_preference and entities.get("time_precision") == "clock"
            )
            if pending_when and customer_chose_clock and service_name:
                return VoiceReplyDraft(
                    text=counselor.summarize_reschedule_confirm(
                        customer_name=address_name,
                        service_name=service_name,
                        when=pending_when,
                    ),
                    follow_up_question="Should I move it?",
                )
            if sched and sched.available_slots and has_preference:
                ranges = [
                    (slot.start, getattr(slot, "end", None))
                    for slot in sched.available_slots[:3]
                ]
                spoken = counselor.offer_slots_spoken(
                    ranges, customer_name=address_name, service_name=service_name
                )
                return VoiceReplyDraft(
                    text=spoken.replace("I've got", "no problem — I've got").replace(
                        "Want the first one, or a different time?",
                        "Which works, or another day?",
                    ),
                    follow_up_question="Which new time?",
                )
            return VoiceReplyDraft(
                text=counselor.summarize_reschedule_confirm(
                    customer_name=address_name,
                    service_name=service_name,
                    when=None,
                ),
                follow_up_question="New day and time?",
            )

        if intent == CustomerIntent.CANCEL_APPOINTMENT:
            if sched and sched.success and sched.appointment:
                return VoiceReplyDraft(
                    text=counselor.summarize_done(
                        action="cancel",
                        customer_name=address_name,
                        service_name=service_name,
                    ),
                    end_call=True,
                )
            return VoiceReplyDraft(
                text=counselor.summarize_cancel_confirm(
                    customer_name=address_name,
                    service_name=service_name,
                ),
                follow_up_question="Confirm cancellation?",
            )

        if intent == CustomerIntent.ASK_REPAIR_STATUS:
            who = f"{address_name}, " if address_name else ""
            return VoiceReplyDraft(
                text=(
                    f"{who}let me check on that. "
                    "Someone from the shop will get you the details shortly. "
                    "Do you have a repair order number handy?"
                ),
                follow_up_question="Repair order number?",
            )

        if intent == CustomerIntent.PRICE_QUESTION:
            return VoiceReplyDraft(
                text=counselor.ask_service(customer_name=address_name),
                follow_up_question="Which service?",
            )

        if intent == CustomerIntent.MAINTENANCE_QUESTION:
            tip = "oil changes every five thousand miles"
            if rev and rev.maintenance_reminders:
                tip = rev.maintenance_reminders[0].get("service", tip).replace("_", " ")
            who = f"{address_name}, " if address_name else ""
            return VoiceReplyDraft(
                text=(
                    f"{who}we usually recommend {tip}. "
                    "Want me to get you on the schedule?"
                ),
                follow_up_question="Book a maintenance visit?",
            )

        text_blob = " ".join(t.text.lower() for t in memory.turns[-3:])
        if "approve" in text_blob or "estimate" in text_blob:
            who = f"{address_name}, " if address_name else ""
            return VoiceReplyDraft(
                text=(
                    f"{who}got it — I've noted your estimate decision. "
                    "We'll update the shop. Anything else?"
                )
            )

        if intent == CustomerIntent.EMERGENCY:
            who = f"{address_name}, " if address_name else ""
            return VoiceReplyDraft(
                text=(
                    f"{who}I'm sorry you're dealing with that. "
                    "I'm getting the shop on the line right now — stay with me."
                ),
                escalate_to_human=True,
                reason="emergency",
            )

        if intent == CustomerIntent.COMPLAINT:
            who = f"{address_name}, " if address_name else ""
            return VoiceReplyDraft(
                text=(
                    f"{who}I'm really sorry about that. "
                    "Let me get an owner for you — one moment."
                ),
                escalate_to_human=True,
                reason="complaint",
            )

        if memory.pending_question and intent == CustomerIntent.OTHER:
            who = f"{address_name}, " if address_name else ""
            if counselor.is_purpose_question(memory.pending_question):
                if counselor.looks_like_reschedule_desire(last_customer):
                    return VoiceReplyDraft(
                        text=counselor.summarize_reschedule_confirm(
                            customer_name=address_name,
                            service_name=service_name,
                            when=None,
                        ),
                        follow_up_question="New day and time?",
                    )
                if counselor.looks_like_booking_desire(last_customer):
                    return VoiceReplyDraft(
                        text=counselor.ask_service(customer_name=address_name),
                        follow_up_question="What service do you need?",
                    )
                return VoiceReplyDraft(
                    text=(
                        f"{who}got it — need to book, change, or cancel? "
                        "Just tell me which."
                    ),
                    follow_up_question="Need to book, change, or cancel?",
                )
            return VoiceReplyDraft(
                text=f"{who}got it. {memory.pending_question}",
                follow_up_question=memory.pending_question,
            )

        if counselor.looks_like_reschedule_desire(last_customer):
            return VoiceReplyDraft(
                text=counselor.summarize_reschedule_confirm(
                    customer_name=address_name,
                    service_name=service_name,
                    when=None,
                ),
                follow_up_question="New day and time?",
            )

        if counselor.looks_like_booking_desire(last_customer) and not service_name:
            return VoiceReplyDraft(
                text=counselor.ask_service(customer_name=address_name),
                follow_up_question="What service do you need?",
            )

        who = f"{address_name}, " if address_name else ""
        return VoiceReplyDraft(
            text=(
                f"{who}no worries — what do you need? "
                "Booking, a change, or a cancel — just tell me."
            ),
            follow_up_question="What do you need?",
        )

    def farewell(self) -> VoiceReplyDraft:
        return VoiceReplyDraft(
            text="Alright, thanks for calling — take care.",
            end_call=True,
        )
