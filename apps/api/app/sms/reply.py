"""Contextual SMS reply generation from agent pipeline + conversation memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.agents.counselor import persona as counselor
from app.agents.orchestrator import PipelineResult
from app.agents.intent.models import CustomerIntent
from app.sms.memory import ConversationMemorySnapshot


@dataclass(slots=True)
class ReplyDraft:
    body: str
    follow_up_question: str | None = None
    send: bool = True
    reason: str | None = None


def _format_appt_when(iso_start: str | None) -> str | None:
    if not iso_start:
        return None
    try:
        from zoneinfo import ZoneInfo

        shop_tz = ZoneInfo("America/Los_Angeles")
        dt = datetime.fromisoformat(iso_start.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=shop_tz)
        else:
            dt = dt.astimezone(shop_tz)
        # Keep a concrete calendar cue for SMS (weekday + month day).
        return dt.strftime("%a %b %d at %I:%M %p").replace(" 0", " ")
    except (ValueError, TypeError):
        return None


def _parse_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _next_appointment_bit(upcoming: list[dict]) -> str:
    if not upcoming:
        return ""
    appt = upcoming[0]
    when = _format_appt_when(appt.get("start"))
    service = appt.get("service_name")
    if when and service:
        return f" your {service} is on {when}."
    if when:
        return f" you've got an appointment on {when}."
    return ""


class ContextualReplyGenerator:
    """Heuristic reply templates grounded in agent outputs + memory (LLM-swappable)."""

    def generate(
        self,
        *,
        pipeline: PipelineResult,
        memory: ConversationMemorySnapshot,
        customer_name: str | None = None,
        shop_name: str | None = None,
    ) -> ReplyDraft:
        meta = pipeline.context.metadata or {}
        snapshot = meta.get("customer_snapshot") or {}
        upcoming = list(meta.get("upcoming_appointments") or [])
        # Speak only real names — never CRM placeholders / false extractions (e.g. Going).
        name = counselor.spoken_first_name(
            customer_name or snapshot.get("name")
        ) or None
        schedule_bit = _next_appointment_bit(upcoming)
        # Shop intro + name only on the first AI reply; later turns skip both.
        is_first_reply = not any(t.role == "assistant" for t in memory.turns)
        address_name = name if is_first_reply else None
        if is_first_reply:
            greeting = counselor.first_reply_prefix(
                shop_name=shop_name, customer_name=address_name
            )
        else:
            greeting = ""

        if pipeline.escalate:
            reason = (
                pipeline.supervisor.escalation_reason
                if pipeline.supervisor
                else "needs human help"
            )
            return ReplyDraft(
                body=(
                    f"{greeting}thanks for reaching out — someone from the shop "
                    "will text you back shortly."
                ),
                send=True,
                reason=f"escalated: {reason}",
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
            or getattr(memory, "pending_service", None)
        )
        service_price = entities.get("service_price")
        scheduling = pipeline.stages.get("scheduling")
        sched_data = scheduling.data if scheduling else None
        decision = getattr(sched_data, "decision", None) if sched_data else None
        if sched_data and getattr(sched_data, "appointment", None):
            service_name = (
                getattr(sched_data.appointment, "service_name", None) or service_name
            )
        if decision is not None:
            service_name = getattr(decision, "service_name", None) or service_name

        candidates = list(entities.get("service_candidates") or [])
        if entities.get("service_needs_disambiguation") and candidates:
            return ReplyDraft(
                body=counselor.offer_service_candidates(
                    candidates, customer_name=address_name
                ),
                follow_up_question="Which service?",
            )

        last_customer = next(
            (
                t.content
                for t in reversed(memory.turns)
                if t.role in {"customer", "user"}
            ),
            "",
        )

        # Already booked this turn — confirm before asking for missing fields.
        if (
            intent == CustomerIntent.BOOK_APPOINTMENT
            and sched_data
            and sched_data.success
            and sched_data.appointment
        ):
            return ReplyDraft(
                body=counselor.summarize_done(
                    action="book",
                    customer_name=address_name,
                    service_name=service_name,
                    when=sched_data.appointment.start,
                ),
            )

        needs_name = counselor.needs_customer_name(customer_name or snapshot.get("name"))

        # Booking without a service → ask which service first (before day/time).
        # Time-change phrasing must not fall into this (keep existing service).
        if (
            intent == CustomerIntent.BOOK_APPOINTMENT
            and not service_name
            and not counselor.looks_like_reschedule_desire(last_customer)
        ):
            ask = counselor.ask_service(
                customer_name=None
            )
            body = f"{greeting}{ask}" if is_first_reply else ask
            return ReplyDraft(
                body=body,
                follow_up_question="What service do you need?",
            )

        # Misclassified BOOK that is actually a time change → ask for new time.
        if (
            intent == CustomerIntent.BOOK_APPOINTMENT
            and not service_name
            and counselor.looks_like_reschedule_desire(last_customer)
        ):
            if upcoming:
                service_name = upcoming[0].get("service_name") or service_name
            existing = schedule_bit.strip()
            if existing:
                return ReplyDraft(
                    body=(
                        f"{greeting}no problem, we can change it. "
                        f"{existing} What new day/time works?"
                    ),
                    follow_up_question="New preferred day/time?",
                )
            return ReplyDraft(
                body=counselor.summarize_reschedule_confirm(
                    customer_name=address_name,
                    service_name=service_name,
                    when=None,
                ),
                follow_up_question="New preferred day/time?",
            )

        # Customer answered the open "what can I help with?" with a booking desire.
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
            ask = counselor.ask_service(
                customer_name=None
            )
            body = f"{greeting}{ask}" if is_first_reply else ask
            return ReplyDraft(
                body=body,
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
            if intent == CustomerIntent.CHECK_AVAILABILITY and sched_data and sched_data.available_slots:
                ranges = [
                    (slot.start, getattr(slot, "end", None))
                    for slot in sched_data.available_slots[:4]
                ]
                body = counselor.offer_slots_spoken(
                    ranges,
                    customer_name=address_name,
                    service_name=service_name,
                    limit=4,
                )
                body = body.replace(
                    "Want the first one, or a different time?",
                    "Want the first one? Reply yes — or tell me a better day/time.",
                )
                return ReplyDraft(
                    body=body,
                    follow_up_question="Preferred day/time for your appointment?",
                )
            return ReplyDraft(
                body=counselor.ask_time(
                    customer_name=address_name, service_name=service_name
                ),
                follow_up_question="Preferred day/time for your appointment?",
            )

        if memory.pending_question and intent == CustomerIntent.OTHER:
            # Never re-ask the same open purpose question after the customer answered.
            if counselor.is_purpose_question(memory.pending_question):
                if counselor.looks_like_reschedule_desire(last_customer):
                    if not service_name and upcoming:
                        service_name = upcoming[0].get("service_name") or service_name
                    existing = schedule_bit.strip()
                    if existing:
                        return ReplyDraft(
                            body=(
                                f"{greeting}no problem, we can change it. "
                                f"{existing} What new day/time works?"
                            ),
                            follow_up_question="New preferred day/time?",
                        )
                    return ReplyDraft(
                        body=counselor.summarize_reschedule_confirm(
                            customer_name=address_name,
                            service_name=service_name,
                            when=None,
                        ),
                        follow_up_question="New preferred day/time?",
                    )
                if counselor.looks_like_booking_desire(last_customer):
                    return ReplyDraft(
                        body=counselor.ask_service(
                            customer_name=address_name
                        ),
                        follow_up_question="What service do you need?",
                    )
                return ReplyDraft(
                    body=(
                        f"{greeting}got it — need to book, change, or cancel? "
                        "Just tell me which."
                    ),
                    follow_up_question="Need to book, change, or cancel?",
                )
            return ReplyDraft(
                body=f"{greeting}got it. {memory.pending_question}",
                follow_up_question=memory.pending_question,
            )

        if intent in {
            CustomerIntent.CHECK_AVAILABILITY,
            CustomerIntent.BOOK_APPOINTMENT,
        }:
            sched_meta = (getattr(sched_data, "metadata", None) or {}) if sched_data else {}
            sched_message = getattr(sched_data, "message", None) if sched_data else None
            if (
                sched_message == "preferred_time_unavailable"
                or sched_meta.get("preferred_time_unavailable")
            ):
                preferred = _parse_dt(entities.get("preferred_start")) or _parse_dt(
                    sched_meta.get("preferred_start")
                )
                return ReplyDraft(
                    body=counselor.time_unavailable(
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
                body = f"{greeting}{ask}" if is_first_reply else ask
                return ReplyDraft(
                    body=body,
                    follow_up_question=ask,
                )
            # Only confirm a slot scheduling actually held — never echo a raw
            # preferred clock time just because other openings exist (that can
            # be outside business hours).
            if (
                intent == CustomerIntent.BOOK_APPOINTMENT
                and service_name
                and pending_when
                and sched_data
                and (
                    sched_message == "awaiting_booking_confirmation"
                    or sched_meta.get("awaiting_confirmation")
                )
                and not needs_name
            ):
                return ReplyDraft(
                    body=counselor.summarize_booking_confirm(
                        customer_name=address_name,
                        service_name=service_name,
                        when=pending_when,
                    ),
                    follow_up_question="Should I book that?",
                )
            # Availability ask → list openings. Booking → ask when they want to come.
            if intent == CustomerIntent.CHECK_AVAILABILITY:
                if sched_data and sched_data.available_slots:
                    ranges = [
                        (slot.start, getattr(slot, "end", None))
                        for slot in sched_data.available_slots[:4]
                    ]
                    body = counselor.offer_slots_spoken(
                        ranges,
                        customer_name=address_name,
                        service_name=service_name,
                        limit=4,
                    )
                    body = body.replace(
                        "Want the first one, or a different time?",
                        "Want the first one? Reply yes — or tell me a better day/time.",
                    )
                    return ReplyDraft(
                        body=body,
                        follow_up_question="Preferred day/time for your appointment?",
                    )
                if schedule_bit:
                    return ReplyDraft(
                        body=(
                            f"{greeting}{schedule_bit.strip()} "
                            f"Want a different time"
                            f"{' for ' + service_name if service_name else ''}, or keep that one?"
                        ),
                        follow_up_question="Keep existing appointment or pick a new time?",
                    )
                return ReplyDraft(
                    body=(
                        f"{greeting}I'm not seeing openings"
                        f"{' for ' + service_name if service_name else ''} in the next week. "
                        "Want me to check another day?"
                    ),
                    follow_up_question="Different day range?",
                )
            return ReplyDraft(
                body=counselor.ask_time(
                    customer_name=address_name, service_name=service_name
                ),
                follow_up_question="What day and time work best?",
            )

        if intent == CustomerIntent.RESCHEDULE:
            if not service_name and upcoming:
                service_name = upcoming[0].get("service_name") or service_name
            if sched_data and sched_data.success and sched_data.appointment:
                return ReplyDraft(
                    body=counselor.summarize_done(
                        action="reschedule",
                        customer_name=address_name,
                        service_name=service_name,
                        when=sched_data.appointment.start,
                    )
                )
            sched_meta = (getattr(sched_data, "metadata", None) or {}) if sched_data else {}
            sched_message = getattr(sched_data, "message", None) if sched_data else None
            if (
                sched_message == "preferred_time_unavailable"
                or sched_meta.get("preferred_time_unavailable")
            ):
                preferred = _parse_dt(entities.get("preferred_start")) or _parse_dt(
                    sched_meta.get("preferred_start")
                )
                return ReplyDraft(
                    body=counselor.time_unavailable(
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
            # Only confirm a slot the customer actually picked — never invent one.
            if pending_when and customer_chose_clock:
                return ReplyDraft(
                    body=counselor.summarize_reschedule_confirm(
                        customer_name=address_name,
                        service_name=service_name,
                        when=pending_when,
                    ),
                    follow_up_question="Should I move it?",
                )
            # Soft day / earliest preference → list openings. Bare "change time" → ask.
            if sched_data and sched_data.available_slots and has_preference:
                ranges = [
                    (slot.start, getattr(slot, "end", None))
                    for slot in sched_data.available_slots[:4]
                ]
                body = counselor.offer_slots_spoken(
                    ranges,
                    customer_name=address_name,
                    service_name=service_name,
                    limit=4,
                )
                return ReplyDraft(
                    body=f"No problem, we can change it. {body}",
                    follow_up_question="New preferred day/time?",
                )
            existing = schedule_bit.strip()
            if existing:
                return ReplyDraft(
                    body=(
                        f"{greeting}no problem, we can change it. "
                        f"{existing} What new day/time works?"
                    ),
                    follow_up_question="New preferred day/time?",
                )
            return ReplyDraft(
                body=counselor.summarize_reschedule_confirm(
                    customer_name=address_name,
                    service_name=service_name,
                    when=None,
                ),
                follow_up_question="New preferred day/time?",
            )

        if intent == CustomerIntent.CANCEL_APPOINTMENT:
            if sched_data and sched_data.success and sched_data.appointment:
                return ReplyDraft(
                    body=counselor.summarize_done(
                        action="cancel",
                        customer_name=address_name,
                        service_name=service_name,
                    )
                )
            existing = schedule_bit.strip()
            when = None
            svc = service_name
            if upcoming:
                when = _format_appt_when(upcoming[0].get("start"))
                svc = upcoming[0].get("service_name") or svc
            body = counselor.summarize_cancel_confirm(
                customer_name=address_name,
                service_name=svc,
                when=when,
            )
            if existing and not when:
                body = f"{greeting}{existing} {body}"
            return ReplyDraft(
                body=body,
                follow_up_question="Confirm cancellation?",
            )

        if intent == CustomerIntent.ASK_REPAIR_STATUS:
            status_hint = schedule_bit.strip()
            if status_hint:
                return ReplyDraft(
                    body=(
                        f"{greeting}{status_hint} "
                        "I'm checking on your vehicle — "
                        "someone from the shop will text you an update shortly."
                    ),
                    follow_up_question="RO number or vehicle (year/make/model)?",
                )
            return ReplyDraft(
                body=(
                    f"{greeting}I'm checking on your vehicle. "
                    "Someone from the shop will text an update shortly — "
                    "or send your RO number / year-make-model and I'll dig in faster."
                ),
                follow_up_question="RO number or vehicle (year/make/model)?",
            )

        if intent == CustomerIntent.PRICE_QUESTION:
            if service_name and service_price is not None:
                return ReplyDraft(
                    body=(
                        f"{greeting}{service_name} usually runs about ${service_price}. "
                        "Want me to book that?"
                    ),
                    follow_up_question="Book this service?",
                )
            if service_name:
                return ReplyDraft(
                    body=(
                        f"{greeting}for {service_name}, a service advisor will confirm "
                        "the exact quote. Want me to get you on the schedule in the meantime?"
                    ),
                    follow_up_question="Book this service?",
                )
            return ReplyDraft(
                body=counselor.ask_service(customer_name=address_name),
                follow_up_question="Which service do you need priced?",
            )

        if intent == CustomerIntent.MAINTENANCE_QUESTION:
            if service_name:
                return ReplyDraft(
                    body=f"{greeting}yep, we do {service_name}. Want me to book a visit?",
                    follow_up_question=f"Book {service_name}?",
                )
            return ReplyDraft(
                body=(
                    f"{greeting}we usually recommend oil changes every 5,000 miles "
                    "and brake checks around 20,000. Want me to book a visit?"
                ),
                follow_up_question="Book a maintenance appointment?",
            )

        if intent == CustomerIntent.EMERGENCY:
            return ReplyDraft(
                body=(
                    f"{greeting}sorry you're dealing with this — we've flagged it as urgent "
                    "and someone from the shop will reach out ASAP. "
                    "If you're in danger, call emergency services."
                ),
                reason="emergency",
            )

        if intent == CustomerIntent.COMPLAINT:
            return ReplyDraft(
                body=(
                    f"{greeting}I'm really sorry about that. "
                    "An owner/manager has been looped in and will follow up personally."
                ),
                reason="complaint",
            )

        if intent == CustomerIntent.NEW_CUSTOMER:
            shop = (shop_name or "").strip()
            if counselor.looks_like_booking_desire(last_customer):
                ask = counselor.ask_service(
                    customer_name=None
                )
                body = f"{greeting}{ask}" if is_first_reply else ask
                return ReplyDraft(
                    body=body,
                    follow_up_question="What service do you need?",
                )
            if is_first_reply and shop:
                body = (
                    f"{greeting}{counselor.ask_purpose()} "
                    "I can help book, change, or cancel."
                )
            elif shop:
                body = f"{greeting}welcome to {shop}. What can we help with today?"
            else:
                body = f"{greeting}welcome — glad you found us. What can we help with today?"
            return ReplyDraft(
                body=body,
                follow_up_question=counselor.ask_purpose()
                if is_first_reply
                else "What can we help with today?",
            )

        if schedule_bit:
            return ReplyDraft(
                body=(
                    f"{greeting}{schedule_bit.strip()} "
                    "What's up — need to change that, check on something, or something else?"
                ),
                follow_up_question="What do you need?",
            )
        if counselor.looks_like_reschedule_desire(last_customer):
            return ReplyDraft(
                body=counselor.summarize_reschedule_confirm(
                    customer_name=address_name,
                    service_name=service_name,
                    when=None,
                ),
                follow_up_question="New preferred day/time?",
            )
        if counselor.looks_like_booking_desire(last_customer):
            ask = counselor.ask_service(
                customer_name=None
            )
            body = f"{greeting}{ask}" if is_first_reply else ask
            return ReplyDraft(
                body=body,
                follow_up_question="What service do you need?",
            )
        if is_first_reply:
            return ReplyDraft(
                body=(
                    f"{greeting}{counselor.ask_purpose()} "
                    "Need to book, change, or cancel — just tell me."
                ),
                follow_up_question=counselor.ask_purpose(),
            )
        return ReplyDraft(
            body=(
                f"{greeting}{counselor.ask_purpose()} "
                "Need to book, change, or cancel — just tell me."
            ),
            follow_up_question="What do you need?",
        )

