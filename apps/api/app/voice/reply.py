"""Spoken reply drafting for phone conversations."""

from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass

from app.agents.counselor import persona as counselor
from app.agents.intent.models import CustomerIntent
from app.agents.intent.reschedule_text import looks_like_service_type_change
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


def _mentions_time_change_with_service(text: str | None) -> bool:
    """True when utterance asks to change both job and clock (compound move)."""
    if not text:
        return False
    low = text.casefold()
    has_when = any(
        t in low
        for t in (
            " time",
            "time ",
            " date",
            " day",
            "when",
            "timing",
            "schedule",
            "slot",
            "window",
            "hour",
        )
    )
    has_join = any(
        t in low
        for t in (
            " and ",
            "&",
            " both",
            "both ",
            " plus ",
            " as well",
            " also",
            " along with",
            " together with",
            " too",
            "not just",
            "not only",
        )
    )
    # "new service and new time" / dual different without "and" already covered
    has_dual_new = (
        any(x in low for x in ("new service", "different service", "another service", "different job"))
        and any(x in low for x in ("new time", "different time", "another time", "new day", "different day"))
    )
    has_whole = any(
        x in low
        for x in (
            "whole appointment",
            "entire appointment",
            "full appointment",
            "whole booking",
            "entire booking",
            "change it all",
            "change everything",
        )
    )
    return (has_when and has_join) or has_dual_new or has_whole


def _service_type_or_time_reschedule_draft(
    *,
    last_customer: str,
    address_name: str | None,
    service_name: str | None,
    current_service: str | None = None,
) -> VoiceReplyDraft | None:
    """Service-type swap asks which job; pure time move asks day/time."""
    if looks_like_service_type_change(last_customer):
        if _mentions_time_change_with_service(last_customer):
            who = f"{address_name}, " if address_name else ""
            cur = current_service or service_name
            svc_bit = f" instead of {cur}" if cur else ""
            return VoiceReplyDraft(
                text=(
                    f"{who}sure — which service{svc_bit}, "
                    "and what day and time work for you?"
                ),
                follow_up_question="Which service and new day/time?",
            )
        return VoiceReplyDraft(
            text=counselor.ask_replacement_service(
                customer_name=address_name,
                current_service=current_service or service_name,
            ),
            follow_up_question="Which service instead?",
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

        # Off-topic chatter (weather, jokes, news…) — kindly guide back to service.
        # Run before needs_time / booking paths so leftover date words ("today")
        # do not pull the call into a scheduling flow.
        if (
            counselor.looks_like_off_topic(last_customer)
            and not service_name
            and intent
            not in {
                CustomerIntent.BOOK_APPOINTMENT,
                CustomerIntent.CHECK_AVAILABILITY,
                CustomerIntent.RESCHEDULE,
                CustomerIntent.CANCEL_APPOINTMENT,
                CustomerIntent.ASK_REPAIR_STATUS,
                CustomerIntent.PRICE_QUESTION,
                CustomerIntent.MAINTENANCE_QUESTION,
                CustomerIntent.EMERGENCY,
                CustomerIntent.COMPLAINT,
            }
        ):
            return VoiceReplyDraft(
                text=counselor.redirect_to_service_topic(
                    customer_name=address_name
                ),
                follow_up_question="How can I help with vehicle service?",
            )

        # Already booked this turn — confirm, then keep the line open.
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
                    keep_open=True,
                ),
                follow_up_question="Anything else I can help with?",
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

        # Misclassified BOOK that is actually a reschedule desire.
        if (
            intent == CustomerIntent.BOOK_APPOINTMENT
            and not service_name
            and counselor.looks_like_reschedule_desire(last_customer)
        ):
            draft = _service_type_or_time_reschedule_draft(
                last_customer=last_customer,
                address_name=address_name,
                service_name=service_name,
            )
            if draft is not None:
                return draft

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

        # Preferred day/time rejected by scheduling (closed day, full slot, etc.)
        # must speak before partial needs_time re-asks (e.g. closed Sunday).
        sched_meta_early = (getattr(sched, "metadata", None) or {}) if sched else {}
        sched_message_early = getattr(sched, "message", None) if sched else None
        if (
            intent
            in {
                CustomerIntent.CHECK_AVAILABILITY,
                CustomerIntent.BOOK_APPOINTMENT,
                CustomerIntent.RESCHEDULE,
            }
            and (
                sched_message_early == "preferred_time_unavailable"
                or sched_meta_early.get("preferred_time_unavailable")
            )
        ):
            preferred = _parse_dt(entities.get("preferred_start")) or _parse_dt(
                sched_meta_early.get("preferred_start")
            )
            aspect = str(sched_meta_early.get("unavailable_aspect") or "both")
            if aspect not in {"date", "time", "both"}:
                aspect = "both"
            day_only = aspect == "date" and (
                entities.get("time_precision") in {"day", "part_of_day"}
                or (
                    bool(sched_meta_early.get("closed_day"))
                    and entities.get("time_precision") != "clock"
                )
            )
            follow = (
                "What other day works?"
                if aspect == "date"
                else "What other time works?"
                if aspect == "time"
                else "What other day or time works?"
            )
            return VoiceReplyDraft(
                text=counselor.time_unavailable(
                    preferred,
                    customer_name=address_name,
                    ask=aspect,
                    day_only=day_only,
                ),
                follow_up_question=follow,
            )

        # Partial date/time: day-only → ask clock; time-only → ask day.
        # Reschedule/cancel keep their own paths (acknowledge change, ask new time).
        if (
            intent
            not in {
                CustomerIntent.RESCHEDULE,
                CustomerIntent.CANCEL_APPOINTMENT,
            }
            and (
                entities.get("vague_time")
                or entities.get("needs_time")
                or entities.get("needs_date")
            )
        ):
            preferred_partial = _parse_dt(entities.get("preferred_start"))
            if intent == CustomerIntent.CHECK_AVAILABILITY and sched and sched.available_slots:
                ranges = [
                    (slot.start, getattr(slot, "end", None))
                    for slot in sched.available_slots
                ]
                return VoiceReplyDraft(
                    text=counselor.offer_slots_spoken(
                        ranges,
                        customer_name=address_name,
                        service_name=service_name,
                    ),
                    follow_up_question="Which time works?",
                )
            # Clock/part without a day → only ask for the day.
            if entities.get("needs_date") and not entities.get("needs_time"):
                return VoiceReplyDraft(
                    text=counselor.ask_date(
                        customer_name=address_name,
                        service_name=service_name,
                        known_time=preferred_partial,
                    ),
                    follow_up_question="Preferred day?",
                )
            # Day known, clock missing → only ask for the time.
            known_day = (
                preferred_partial
                if entities.get("time_precision") in {"day", "part_of_day"}
                else None
            )
            return VoiceReplyDraft(
                text=counselor.ask_time(
                    customer_name=address_name,
                    service_name=service_name,
                    known_day=known_day,
                ),
                follow_up_question=(
                    "Preferred time?" if known_day else "Preferred day and time?"
                ),
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
                aspect = str(sched_meta.get("unavailable_aspect") or "both")
                if aspect not in {"date", "time", "both"}:
                    aspect = "both"
                day_only = aspect == "date" and (
                    entities.get("time_precision") in {"day", "part_of_day"}
                    or (
                        bool(sched_meta.get("closed_day"))
                        and entities.get("time_precision") != "clock"
                    )
                )
                follow = (
                    "What other day works?"
                    if aspect == "date"
                    else "What other time works?"
                    if aspect == "time"
                    else "What other day or time works?"
                )
                return VoiceReplyDraft(
                    text=counselor.time_unavailable(
                        preferred,
                        customer_name=address_name,
                        ask=aspect,
                        day_only=day_only,
                    ),
                    follow_up_question=follow,
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
                        # Confirmation is a natural place to use their name (kind + clear).
                        customer_name=name,
                        service_name=service_name,
                        when=pending_when,
                    ),
                    follow_up_question="Shall I book that for you?",
                )
            if intent == CustomerIntent.CHECK_AVAILABILITY:
                if sched and sched.available_slots:
                    ranges = [
                        (slot.start, getattr(slot, "end", None))
                        for slot in sched.available_slots
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
            # Clock already known (time_only / needs_date) — do not re-ask the hour.
            known_clock = _parse_dt(entities.get("preferred_start")) or _parse_dt(
                sched_meta.get("preferred_start")
            )
            if (
                entities.get("time_precision") == "time_only"
                or sched_meta.get("time_precision") == "time_only"
                or entities.get("needs_date")
                or sched_meta.get("needs_date")
            ) and known_clock is not None:
                return VoiceReplyDraft(
                    text=counselor.ask_date(
                        customer_name=address_name,
                        service_name=service_name,
                        known_time=known_clock,
                    ),
                    follow_up_question="Preferred day?",
                )
            return VoiceReplyDraft(
                text=counselor.ask_time(
                    customer_name=address_name, service_name=service_name
                ),
                follow_up_question="Preferred day and time?",
            )

        if intent == CustomerIntent.RESCHEDULE:
            # Prefer known upcoming visit details (cleared after a book in-call).
            upcoming = list(meta.get("upcoming_appointments") or [])
            named_this_turn = bool(
                entities.get("requested_service") or entities.get("service")
            )
            # "Change the service type" without a destination → ask which job,
            # not "what new day/time" (that feels like we ignored them).
            # Ignore stashed preferred_start from a prior turn — type-swap is
            # a new job ask first; day/clock stays until they name a service.
            if (
                looks_like_service_type_change(last_customer)
                and not named_this_turn
                and not entities.get("prefer_earliest")
                and not entities.get("prefer_latest")
            ):
                current = None
                if upcoming:
                    current = upcoming[0].get("service_name")
                # Compound "service and time" — ask for both halves.
                if _mentions_time_change_with_service(last_customer):
                    draft = _service_type_or_time_reschedule_draft(
                        last_customer=last_customer,
                        address_name=address_name,
                        service_name=service_name,
                        current_service=current or service_name,
                    )
                    if draft is not None:
                        return draft
                return VoiceReplyDraft(
                    text=counselor.ask_replacement_service(
                        customer_name=address_name,
                        current_service=current or service_name,
                    ),
                    follow_up_question="Which service instead?",
                )
            if not service_name and upcoming:
                service_name = upcoming[0].get("service_name") or service_name
            if sched and sched.success and sched.appointment:
                return VoiceReplyDraft(
                    text=counselor.summarize_done(
                        action="reschedule",
                        customer_name=address_name,
                        service_name=service_name,
                        when=sched.appointment.start,
                        keep_open=True,
                    ),
                    follow_up_question="Anything else I can help with?",
                )
            sched_meta = (getattr(sched, "metadata", None) or {}) if sched else {}
            sched_message = getattr(sched, "message", None) if sched else None
            if sched_message == "no_appointment_to_reschedule" or sched_meta.get(
                "no_appointment"
            ):
                who = f"{address_name}, " if address_name else ""
                return VoiceReplyDraft(
                    text=(
                        f"{who}I'm not seeing an upcoming appointment to move. "
                        "Would you like to book a visit instead?"
                    ),
                    follow_up_question="Book a visit, or something else?",
                )
            if (
                sched_message == "preferred_time_unavailable"
                or sched_meta.get("preferred_time_unavailable")
            ):
                preferred = _parse_dt(entities.get("preferred_start")) or _parse_dt(
                    sched_meta.get("preferred_start")
                )
                aspect = str(sched_meta.get("unavailable_aspect") or "both")
                if aspect not in {"date", "time", "both"}:
                    aspect = "both"
                follow = (
                    "What other day works?"
                    if aspect == "date"
                    else "What other time works?"
                    if aspect == "time"
                    else "What other day or time works?"
                )
                return VoiceReplyDraft(
                    text=counselor.time_unavailable(
                        preferred, customer_name=address_name, ask=aspect
                    ),
                    follow_up_question=follow,
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
                has_preference
                and entities.get("time_precision") == "clock"
                and not entities.get("needs_date")
                and not entities.get("needs_time")
            )
            # Only confirm a slot the customer actually picked — service name optional.
            if pending_when and customer_chose_clock:
                return VoiceReplyDraft(
                    text=counselor.summarize_reschedule_confirm(
                        customer_name=address_name,
                        service_name=service_name,
                        when=pending_when,
                    ),
                    follow_up_question="Should I move it?",
                )
            # Incomplete answers during reschedule — pin down the missing half.
            preferred_partial = _parse_dt(entities.get("preferred_start"))
            if entities.get("needs_date") and not entities.get("needs_time"):
                return VoiceReplyDraft(
                    text=counselor.ask_date(
                        customer_name=address_name,
                        service_name=service_name,
                        known_time=preferred_partial,
                    ),
                    follow_up_question="Preferred day?",
                )
            if entities.get("needs_time") or entities.get("vague_time"):
                known_day = (
                    preferred_partial
                    if entities.get("time_precision") in {"day", "part_of_day"}
                    else None
                )
                return VoiceReplyDraft(
                    text=counselor.ask_time(
                        customer_name=address_name,
                        service_name=service_name,
                        known_day=known_day,
                    ),
                    follow_up_question=(
                        "Preferred time?" if known_day else "Preferred day and time?"
                    ),
                )
            if sched and sched.available_slots and has_preference:
                ranges = [
                    (slot.start, getattr(slot, "end", None))
                    for slot in sched.available_slots
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
                        keep_open=True,
                    ),
                    follow_up_question="Anything else I can help with?",
                )
            if sched and (
                getattr(sched, "message", None) == "no_appointment_to_cancel"
                or (getattr(sched, "metadata", None) or {}).get("no_appointment")
            ):
                who = f"{address_name}, " if address_name else ""
                return VoiceReplyDraft(
                    text=(
                        f"{who}I'm not seeing an upcoming appointment on the schedule. "
                        "Would you like to book a visit instead?"
                    ),
                    follow_up_question="Book a visit, or something else?",
                )
            # Prefer known upcoming visit details in the confirmation ask.
            upcoming = list(meta.get("upcoming_appointments") or [])
            when = None
            svc = service_name
            if upcoming:
                when = _parse_dt(upcoming[0].get("start"))
                svc = upcoming[0].get("service_name") or svc
            return VoiceReplyDraft(
                text=counselor.summarize_cancel_confirm(
                    customer_name=address_name,
                    service_name=svc,
                    when=when,
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
            who = f"{address_name}, " if address_name else ""
            if rev and rev.maintenance_reminders:
                tip = str(
                    rev.maintenance_reminders[0].get("service") or ""
                ).replace("_", " ").strip()
                if tip:
                    return VoiceReplyDraft(
                        text=(
                            f"{who}for your vehicle, {tip} is coming up. "
                            "Want me to get you on the schedule?"
                        ),
                        follow_up_question="Book a maintenance visit?",
                    )
            if service_name:
                return VoiceReplyDraft(
                    text=(
                        f"{who}yep, we can take care of {service_name}. "
                        "Want me to get you on the schedule?"
                    ),
                    follow_up_question=f"Book {service_name}?",
                )
            return VoiceReplyDraft(
                text=f"{who}want me to get you on the schedule for a visit?",
                follow_up_question="Book a visit?",
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
            # After "anything else?" — never re-ask; farewell on decline / wrap-up.
            if counselor.is_anything_else_question(memory.pending_question):
                if counselor.looks_like_soft_no(last_customer) or counselor.looks_like_farewell(
                    last_customer
                ):
                    return self.farewell()
                if counselor.looks_like_reschedule_desire(last_customer):
                    draft = _service_type_or_time_reschedule_draft(
                        last_customer=last_customer,
                        address_name=address_name,
                        service_name=service_name,
                    )
                    if draft is not None:
                        return draft
                if counselor.looks_like_booking_desire(last_customer):
                    return VoiceReplyDraft(
                        text=counselor.ask_service(customer_name=address_name),
                        follow_up_question="What service do you need?",
                    )
                # Unclear OTHER after the offer — soft close instead of looping the same ask.
                return self.farewell()
            if counselor.is_purpose_question(memory.pending_question):
                if counselor.looks_like_reschedule_desire(last_customer):
                    draft = _service_type_or_time_reschedule_draft(
                        last_customer=last_customer,
                        address_name=address_name,
                        service_name=service_name,
                    )
                    if draft is not None:
                        return draft
                if counselor.looks_like_booking_desire(last_customer):
                    return VoiceReplyDraft(
                        text=counselor.ask_service(customer_name=address_name),
                        follow_up_question="What service do you need?",
                    )
                # Off-topic / unclear after the open purpose ask — guide back to service.
                return VoiceReplyDraft(
                    text=counselor.redirect_to_service_topic(
                        customer_name=address_name
                    ),
                    follow_up_question="How can I help with vehicle service?",
                )
            return VoiceReplyDraft(
                text=f"{who}got it. {memory.pending_question}",
                follow_up_question=memory.pending_question,
            )

        draft = _service_type_or_time_reschedule_draft(
            last_customer=last_customer,
            address_name=address_name,
            service_name=service_name,
        )
        if draft is not None:
            return draft

        if counselor.looks_like_booking_desire(last_customer) and not service_name:
            return VoiceReplyDraft(
                text=counselor.ask_service(customer_name=address_name),
                follow_up_question="What service do you need?",
            )

        # Unrelated / unclear intent with no booking path — kindly stay on service topics.
        return VoiceReplyDraft(
            text=counselor.redirect_to_service_topic(customer_name=address_name),
            follow_up_question="How can I help with vehicle service?",
        )

    def farewell(self) -> VoiceReplyDraft:
        return VoiceReplyDraft(
            text="Thank you so much for calling — take care, and have a great day.",
            end_call=True,
        )
