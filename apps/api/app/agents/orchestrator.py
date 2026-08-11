"""Pipeline orchestrator — AI Decision Layer + Workflow execution.

Flow: Conversation → AI decisions → Workflow DecisionExecutor → Business modules.
AI agents never mutate CRM / Scheduling / Marketing; Workflow applies Decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.base.logging import get_agent_logger, log_extra
from app.agents.bus.protocol import EventBus
from app.agents.communication.models import RawInboundMessage
from app.agents.communication.service import CommunicationAgent
from app.agents.crm.models import CrmUpdateRequest
from app.agents.crm.service import CrmAgent
from app.agents.customer.models import CustomerResolveRequest
from app.agents.customer.service import CustomerAgent
from app.agents.decisions.bridge import collect_decision, ports_from_agents
from app.agents.decisions.types import (
    Decision,
    EscalationDecision,
    SummaryDecision,
)
from app.agents.events.definitions import (
    AgentEventType,
    CommunicationNormalizedEvent,
    CrmUpdatedEvent,
    CustomerResolvedEvent,
    EscalationRequestedEvent,
    IncomingMessageEvent,
    IntentDetectedEvent,
    OwnerSummaryEvent,
    PipelineCompletedEvent,
    RevenueInsightsEvent,
    SchedulingResultEvent,
    SupervisorDecisionEvent,
    VehicleResolvedEvent,
)
from app.agents.events.envelope import EventEnvelope
from app.agents.intent.service import IntentAgent
from app.agents.marketing.models import MarketingActionType, MarketingRequest
from app.agents.marketing.service import MarketingAgent
from app.agents.revenue.models import RevenueAnalysisRequest
from app.agents.revenue.service import RevenueAgent
from app.agents.scheduling.models import SchedulingAction, SchedulingRequest
from app.agents.scheduling.service import SchedulingAgent
from app.agents.supervisor.models import AgentStageOutput, SupervisorReviewRequest
from app.agents.supervisor.service import SupervisorAgent
from app.agents.vehicle.models import VehicleResolveRequest
from app.agents.vehicle.service import VehicleAgent
from app.workflows.decision_executor import DecisionPorts


@dataclass(slots=True)
class PipelineResult:
    correlation_id: str
    success: bool
    escalate: bool
    context: AgentContext
    stages: dict[str, AgentResult[Any]] = field(default_factory=dict)
    supervisor: Any = None
    owner_summary: str | None = None
    decisions: list[Any] = field(default_factory=list)
    execution: Any | None = None


class AgentOrchestrator:
    """Coordinates specialized agents via sequential flow + Workflow execution."""

    FLOW = (
        "communication",
        "intent",
        "customer",
        "vehicle",
        "scheduling",
        "crm",
        "revenue",
        "supervisor",
    )

    # Real-time channels must reply ~1–2s; skip heavy/async-friendly stages.
    _VOICE_FAST_CHANNELS = frozenset({"phone", "voice", "call"})

    def __init__(
        self,
        *,
        bus: EventBus,
        communication: CommunicationAgent,
        intent: IntentAgent,
        customer: CustomerAgent,
        vehicle: VehicleAgent,
        scheduling: SchedulingAgent,
        crm: CrmAgent,
        revenue: RevenueAgent,
        marketing: MarketingAgent,
        supervisor: SupervisorAgent,
        memory: Any | None = None,
    ) -> None:
        self._bus = bus
        self._communication = communication
        self._intent = intent
        self._customer = customer
        self._vehicle = vehicle
        self._scheduling = scheduling
        self._crm = crm
        self._revenue = revenue
        self._marketing = marketing
        self._supervisor = supervisor
        self._memory = memory
        self._logger = get_agent_logger("orchestrator")

    @classmethod
    def _is_voice_fast(cls, channel: str | None) -> bool:
        return (channel or "").strip().lower() in cls._VOICE_FAST_CHANNELS

    @staticmethod
    def _needs_vehicle_stage(
        *,
        voice_fast: bool,
        intent_value: str | None,
        entities: dict[str, Any],
    ) -> bool:
        if not voice_fast:
            return True
        if entities.get("vin") or entities.get("year") or entities.get("mileage"):
            return True
        if intent_value in {
            "repair_status",
            "in_shop_status",
            "estimate",
            "maintenance",
        }:
            return True
        return False

    def _ports(self) -> DecisionPorts:
        return ports_from_agents(
            customer=self._customer,
            vehicle=self._vehicle,
            scheduling=self._scheduling,
            crm=self._crm,
            marketing=self._marketing,
            memory=self._memory,
        )

    async def _apply(
        self, context: AgentContext, decisions: list[Decision]
    ) -> Any:
        if not decisions:
            return None
        from app.workflows.factory import get_workflow_runtime

        return await get_workflow_runtime().coordinator.apply_decisions(
            shop_id=context.shop_id,
            decisions=decisions,
            ports=self._ports(),
            context=context,
            correlation_id=context.correlation_id,
        )

    def _inject_memory(
        self,
        context: AgentContext,
        *,
        text: str | None = None,
    ) -> None:
        if self._memory is None:
            return
        try:
            bundle = self._memory.auto_load(
                context.shop_id,
                text=text,
                customer_id=context.customer_id,
                vehicle_id=context.vehicle_id,
            )
            context.metadata["long_term_memory"] = bundle.to_dict()
            context.metadata["memory_prompt"] = bundle.prompt
            context.metadata["communication_style"] = bundle.communication_style
            context.metadata["customer_preferences"] = bundle.preferences
        except Exception as exc:  # pragma: no cover
            self._logger.warning("memory.auto_load_failed err=%s", exc)
            context.metadata.setdefault("long_term_memory", {"error": str(exc)})

    async def _enrich_schedule_context(self, context: AgentContext) -> None:
        """Attach upcoming appointments so reply/advisor can reference schedule."""
        try:
            store = getattr(self._scheduling, "store", None)
            if store is None:
                return
            upcoming: list[dict[str, Any]] = []
            if context.customer_id is not None and hasattr(store, "list_by_customer"):
                appts = await store.list_by_customer(
                    context.shop_id, context.customer_id
                )
                for a in appts[:5]:
                    upcoming.append(
                        {
                            "id": str(a.id),
                            "start": a.start.isoformat() if a.start else None,
                            "end": a.end.isoformat() if a.end else None,
                            "status": a.status,
                            "service_name": getattr(a, "service_name", None),
                            "service_id": str(a.service_id)
                            if getattr(a, "service_id", None)
                            else None,
                            "notes": getattr(a, "notes", None),
                        }
                    )
            # Voice/SMS may pin a visit without a resolved customer — still load
            # its start so "same time" after a service-type change has an anchor.
            pin = context.metadata.get("appointment_id") or context.metadata.get(
                "active_appointment_id"
            )
            if pin and hasattr(store, "get"):
                try:
                    from uuid import UUID as _UUID

                    appt = await store.get(context.shop_id, _UUID(str(pin)))
                except (TypeError, ValueError, AttributeError):
                    appt = None
                if appt is not None:
                    row = {
                        "id": str(appt.id),
                        "start": appt.start.isoformat() if appt.start else None,
                        "end": appt.end.isoformat() if appt.end else None,
                        "status": appt.status,
                        "service_name": getattr(appt, "service_name", None),
                        "service_id": str(appt.service_id)
                        if getattr(appt, "service_id", None)
                        else None,
                        "notes": getattr(appt, "notes", None),
                    }
                    if not any(str(u.get("id")) == row["id"] for u in upcoming):
                        upcoming.insert(0, row)
                    if row.get("start") and not context.metadata.get(
                        "active_visit_start"
                    ):
                        context.metadata["active_visit_start"] = row["start"]
            if upcoming:
                context.metadata["upcoming_appointments"] = upcoming
                if not context.metadata.get("active_appointment_id"):
                    context.metadata["active_appointment_id"] = upcoming[0]["id"]
                if upcoming[0].get("start") and not context.metadata.get(
                    "active_visit_start"
                ):
                    context.metadata["active_visit_start"] = upcoming[0]["start"]
        except Exception as exc:  # pragma: no cover
            self._logger.warning("schedule.context_enrich_failed err=%s", exc)

    @staticmethod
    def _parse_iso_dt(value: Any) -> datetime | None:
        from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=DEFAULT_SHOP_TZ)
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        # Naive timestamps mean shop wall-clock (matches dashboard booking).
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=DEFAULT_SHOP_TZ)
        return dt

    @staticmethod
    def _pick_offered_slot(
        preferred: datetime | None, slots_offered: list[Any]
    ) -> datetime | None:
        """Bind preferred time (or YES) to a previously offered opening.

        Clock preferences must match an offered start exactly — never snap to
        the nearest opening (that can confirm a different day/time than asked,
        including implying outside-hours requests were accepted).
        """
        starts: list[datetime] = []
        for item in slots_offered or []:
            raw = item.get("start") if isinstance(item, dict) else item
            parsed = AgentOrchestrator._parse_iso_dt(raw)
            if parsed is not None:
                starts.append(parsed)
        if not starts:
            return None
        if preferred is None:
            return starts[0]
        return next((s for s in starts if s == preferred), None)

    def _merge_booking_context(
        self,
        entities: dict[str, Any],
        context: AgentContext,
        *,
        intent: str | None = None,
    ) -> dict[str, Any]:
        """Carry pending service/slots across turns; resolve preferred_start."""
        meta = context.metadata or {}
        merged = dict(entities)
        reschedule_like = intent in {"reschedule", "cancel_appointment"}

        # Time-change / cancel default to the existing appointment service.
        # Prefer pending_service when set (multi-turn service swap: name the new
        # job on turn 1, then answer day/time on turn 2).
        # If the customer names a *different* service this turn, honor that.
        if reschedule_like:
            upcoming = list(meta.get("upcoming_appointments") or [])
            appt = upcoming[0] if upcoming else {}
            named = str(
                merged.get("requested_service") or merged.get("service") or ""
            ).strip()
            appt_name = str(appt.get("service_name") or "").strip()
            pending_name = str(meta.get("pending_service") or "").strip()
            pending_id = meta.get("pending_service_id")
            named_cf = named.casefold()
            appt_cf = appt_name.casefold()
            same_service = bool(
                named_cf
                and appt_cf
                and (
                    named_cf == appt_cf
                    or named_cf in appt_cf
                    or appt_cf in named_cf
                )
            )
            if not named:
                # Service named on a prior reschedule turn (memory) beats the
                # original appointment service — otherwise a day/time answer
                # silently reverts a service-type change.
                if pending_name:
                    merged["requested_service"] = pending_name
                    merged["service"] = pending_name
                    if pending_id and not merged.get("service_id"):
                        merged["service_id"] = pending_id
                    if (
                        not merged.get("duration_minutes")
                        and meta.get("pending_duration_minutes")
                    ):
                        merged["duration_minutes"] = meta["pending_duration_minutes"]
                else:
                    if appt_name:
                        merged["requested_service"] = appt_name
                        merged["service"] = appt_name
                    if appt.get("service_id") and not merged.get("service_id"):
                        merged["service_id"] = appt["service_id"]
            elif not merged.get("service_id") and same_service and appt.get("service_id"):
                # Spoken name matches current appointment — bind the known id.
                merged["service_id"] = appt["service_id"]
            # else: leave service_id unset so catalog resolves the new name
        else:
            if not merged.get("requested_service") and not merged.get("service"):
                pending = meta.get("pending_service")
                if pending:
                    merged["requested_service"] = pending
                    merged["service"] = pending
            if not merged.get("service_id") and meta.get("pending_service_id"):
                merged["service_id"] = meta["pending_service_id"]
            if not merged.get("duration_minutes") and meta.get("pending_duration_minutes"):
                merged["duration_minutes"] = meta["pending_duration_minutes"]
            if not merged.get("service_price") and meta.get("pending_service_price"):
                merged["service_price"] = meta["pending_service_price"]

        preferred = self._parse_iso_dt(merged.get("preferred_start"))
        preferred_end = self._parse_iso_dt(merged.get("preferred_end"))
        slots_offered = list(meta.get("slots_offered") or [])
        time_precision = merged.get("time_precision")
        prefer_earliest = bool(merged.get("prefer_earliest"))
        prefer_latest = bool(merged.get("prefer_latest"))
        needs_date = bool(merged.get("needs_date"))
        needs_time = bool(merged.get("needs_time"))

        # Stashed partial day/time from a prior incomplete answer.
        prev_start = self._parse_iso_dt(meta.get("pending_preferred_start"))
        prev_end = self._parse_iso_dt(meta.get("pending_preferred_end"))
        prev_precision = meta.get("pending_time_precision")
        if not isinstance(prev_precision, str):
            prev_precision = None
        prev_needs_date = bool(meta.get("pending_needs_date"))
        prev_needs_time = bool(meta.get("pending_needs_time"))

        # Compose date-only + time-only answers across turns into one clock time.
        if preferred is not None and prev_start is not None:
            if needs_date and not needs_time and prev_precision in {"day", "part_of_day"}:
                # Current: clock only; prior: day window → use prior day + current clock.
                preferred = self._combine_day_and_clock(prev_start, preferred)
                preferred_end = preferred + timedelta(hours=1)
                time_precision = "clock"
                needs_date = False
                needs_time = False
                merged.pop("needs_date", None)
                merged.pop("needs_time", None)
                merged["time_precision"] = "clock"
            elif (
                needs_date
                and not needs_time
                and prev_precision in {"clock", "time_only"}
                and not prev_needs_date
            ):
                # Current: new clock only; prior full pick still has a known day
                # (e.g. Friday 3pm unavailable → "4pm") → keep that day, new clock.
                preferred = self._combine_day_and_clock(prev_start, preferred)
                preferred_end = preferred + timedelta(hours=1)
                time_precision = "clock"
                needs_date = False
                needs_time = False
                merged.pop("needs_date", None)
                merged.pop("needs_time", None)
                merged["time_precision"] = "clock"
            elif (
                needs_time
                and not needs_date
                and (time_precision or "day") == "day"
                and prev_precision in {"clock", "time_only"}
            ):
                # Current: day only; prior: known clock (incl. after a failed day) →
                # rebind the same clock onto the new day. Do not re-ask for time.
                preferred = self._combine_day_and_clock(preferred, prev_start)
                preferred_end = preferred + timedelta(hours=1)
                time_precision = "clock"
                needs_date = False
                needs_time = False
                merged.pop("needs_date", None)
                merged.pop("needs_time", None)
                merged["time_precision"] = "clock"
            elif needs_time and not needs_date and prev_needs_date and (
                prev_precision in {"clock", "time_only"}
            ):
                # Legacy path: prior turn was time-only with needs_date flag.
                preferred = self._combine_day_and_clock(preferred, prev_start)
                preferred_end = preferred + timedelta(hours=1)
                time_precision = "clock"
                needs_date = False
                needs_time = False
                merged.pop("needs_date", None)
                merged.pop("needs_time", None)
                merged["time_precision"] = "clock"
            elif (
                needs_date
                and needs_time
                and prev_precision in {"day", "part_of_day"}
                and not prev_needs_date
            ):
                # e.g. prior Friday + current "morning" — keep day, soft time.
                preferred = self._combine_day_and_clock(prev_start, preferred)
                preferred_end = (
                    self._combine_day_and_clock(prev_start, prev_end)
                    if prev_end is not None
                    else preferred + timedelta(hours=3)
                )
                time_precision = time_precision or "part_of_day"
                needs_date = False
                merged.pop("needs_date", None)
                merged["time_precision"] = time_precision
        elif preferred is None and prev_start is not None:
            # Carry incomplete preference when this turn had no new date/time.
            # Exception: a concrete hold is already in slots_offered (awaiting name /
            # YES). A leftover time_only/clock stash after a full hold must not
            # override binding to the offered slot.
            held_slot = bool(slots_offered)
            clock_only_stash = (
                prev_precision in {"clock", "time_only"}
                and not prev_needs_date
                and not prev_needs_time
            )
            if not (held_slot and clock_only_stash):
                preferred = prev_start
                preferred_end = prev_end or preferred_end
                time_precision = prev_precision or time_precision
                if prev_needs_date and not needs_date:
                    needs_date = True
                    merged["needs_date"] = True
                if prev_needs_time and not needs_time:
                    needs_time = True
                    merged["needs_time"] = True
                # time_only always means "clock known, day missing" — force date ask.
                if (time_precision == "time_only" or prev_precision == "time_only") and (
                    not held_slot
                ):
                    needs_date = True
                    merged["needs_date"] = True
                    needs_time = False
                    merged.pop("needs_time", None)
                if time_precision:
                    merged["time_precision"] = time_precision
            elif held_slot and not clock_only_stash:
                # Prefer a still-needed day/time half alongside the held slot.
                if prev_needs_date and not needs_date:
                    needs_date = True
                    merged["needs_date"] = True
                if prev_needs_time and not needs_time:
                    needs_time = True
                    merged["needs_time"] = True
                if prev_precision and not time_precision:
                    time_precision = prev_precision
                    merged["time_precision"] = time_precision
                    preferred = prev_start
                    preferred_end = prev_end or preferred_end
                    if time_precision == "time_only":
                        needs_date = True
                        merged["needs_date"] = True


        confirm = bool(merged.get("booking_confirmed"))
        # Soft "yes" after "Want me to book a visit?" (service remembered, no
        # slot offered yet) means continue booking — ask/list times, not create.
        if (
            confirm
            and not slots_offered
            and str(meta.get("pending_action") or "") == "book"
            and (merged.get("requested_service") or merged.get("service"))
        ):
            merged.pop("booking_confirmed", None)
            confirm = False
        # After we asked for a name, restore the held slot so confirmation can resume.
        if (
            preferred is None
            and slots_offered
            and merged.get("name")
            and str(meta.get("pending_action") or "") == "book"
        ):
            preferred = self._parse_iso_dt(slots_offered[0].get("start"))
            preferred_end = self._parse_iso_dt(slots_offered[0].get("end")) or preferred_end
            time_precision = "clock"
            merged["time_precision"] = "clock"
            needs_date = False
            needs_time = False
            merged.pop("needs_date", None)
            merged.pop("needs_time", None)
        # "First one" / earliest after we listed openings → bind to first offered.
        # "Last one" / latest → bind to last offered.
        if (prefer_earliest or prefer_latest) and slots_offered and time_precision != "clock":
            idx = -1 if prefer_latest else 0
            preferred = self._parse_iso_dt(slots_offered[idx].get("start"))
            preferred_end = self._parse_iso_dt(slots_offered[idx].get("end")) or preferred_end
            time_precision = "clock"
            merged["time_precision"] = "clock"
            needs_date = False
            needs_time = False
            merged.pop("needs_time", None)
            merged.pop("needs_date", None)
        # Day / part-of-day are filters, not a chosen clock — don't bind to an
        # offered opening until the customer picks a time or says yes.
        # Clock without an explicit day also cannot bind until day is confirmed.
        can_bind = confirm or (
            preferred is not None
            and time_precision == "clock"
            and not needs_date
            and not needs_time
        )
        if can_bind:
            bound = self._pick_offered_slot(preferred, slots_offered)
            if bound is not None:
                preferred = bound
                preferred_end = None
                # Bound to a concrete offered opening.
                needs_date = False
                needs_time = False
                merged.pop("needs_time", None)
                merged.pop("needs_date", None)
                merged["time_precision"] = "clock"
                time_precision = "clock"

        # Incomplete clock (time said, day missing): do not book as if ready.
        if needs_date and time_precision == "clock":
            # Preserve preferred_start hour for merge; scheduling waits for day.
            time_precision = "time_only"
            merged["time_precision"] = "time_only"

        if preferred is not None:
            merged["preferred_start"] = preferred
        if preferred_end is not None:
            merged["preferred_end"] = preferred_end
        if needs_date:
            merged["needs_date"] = True
        else:
            merged.pop("needs_date", None)
        if needs_time:
            merged["needs_time"] = True
        else:
            merged.pop("needs_time", None)

        # Last chance: keep-same-time after schedule enrich put a visit on context.
        if (
            (merged.get("keep_same_time") or merged.get("same_slot_preference"))
            and (
                needs_time
                or merged.get("time_precision") in {"day", "part_of_day", None}
            )
        ):
            from app.agents.intent.service import apply_same_slot_preference_to_entities

            inbound = str(meta.get("inbound_text") or "")
            if apply_same_slot_preference_to_entities(inbound, merged, context):
                preferred = self._parse_iso_dt(merged.get("preferred_start"))
                preferred_end = self._parse_iso_dt(merged.get("preferred_end"))
                time_precision = merged.get("time_precision")
                needs_date = bool(merged.get("needs_date"))
                needs_time = bool(merged.get("needs_time"))
                if preferred is not None:
                    merged["preferred_start"] = preferred
                if preferred_end is not None:
                    merged["preferred_end"] = preferred_end
                if needs_date:
                    merged["needs_date"] = True
                else:
                    merged.pop("needs_date", None)
                if needs_time:
                    merged["needs_time"] = True
                else:
                    merged.pop("needs_time", None)
                if time_precision:
                    merged["time_precision"] = time_precision

        return merged

    @staticmethod
    def _combine_day_and_clock(day_source: datetime, clock_source: datetime) -> datetime:
        """Use calendar day of day_source with clock hour/minute of clock_source."""
        from app.agents.intent.datetime_parse import combine_day_and_clock

        return combine_day_and_clock(day_source, clock_source)

    @staticmethod
    def _resolve_appointment_id(
        context: AgentContext,
        entities: dict[str, Any],
        *,
        intent: str | None = None,
    ) -> UUID | None:
        """Resolve appointment id for reschedule/cancel (not fresh books).

        Prefer entity → conversation memory → next upcoming appointment.
        New book intents must not bind an existing upcoming visit — that used
        to turn every follow-up booking into a reschedule.
        """
        meta = context.metadata or {}
        pending = str(meta.get("pending_action") or "")
        reschedule_like = (
            intent in {"reschedule", "cancel_appointment"}
            or pending in {"reschedule", "cancel"}
        )

        raw = entities.get("appointment_id")
        if raw:
            try:
                return UUID(str(raw))
            except (ValueError, TypeError):
                pass

        if not reschedule_like:
            return None

        raw = meta.get("appointment_id") or meta.get("active_appointment_id")
        if raw:
            try:
                return UUID(str(raw))
            except (ValueError, TypeError):
                pass
        upcoming = meta.get("upcoming_appointments") or []
        if upcoming and upcoming[0].get("id"):
            try:
                return UUID(str(upcoming[0]["id"]))
            except (ValueError, TypeError):
                return None
        return None

    def _capture_memory(self, context: AgentContext, stages: dict[str, AgentResult[Any]], *, escalate: bool) -> None:
        if self._memory is None:
            return
        try:
            written = self._memory.auto_capture(
                shop_id=context.shop_id,
                customer_id=context.customer_id,
                vehicle_id=context.vehicle_id,
                channel=context.channel,
                message_text=context.metadata.get("inbound_text"),
                stages=stages,
                escalate=escalate,
            )
            context.metadata["memory_writes"] = len(written)
        except Exception as exc:  # pragma: no cover
            self._logger.warning("memory.auto_capture_failed err=%s", exc)

    async def handle_incoming(
        self,
        *,
        shop_id: UUID,
        message: RawInboundMessage,
        correlation_id: str | None = None,
        customer_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        conversation_id: UUID | str | None = None,
    ) -> PipelineResult:
        conv_id = str(conversation_id) if conversation_id else None
        if conv_id is None and message.metadata:
            raw = message.metadata.get("conversation_id") or message.metadata.get(
                "sms_conversation_id"
            )
            if raw:
                conv_id = str(raw)

        context = AgentContext(
            shop_id=shop_id,
            correlation_id=correlation_id or AgentContext(shop_id=shop_id).correlation_id,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            channel=message.channel,
            conversation_id=conv_id,
            metadata={
                "inbound_text": message.content,
                **dict(message.metadata or {}),
            },
        )
        voice_fast = self._is_voice_fast(message.channel)
        if voice_fast:
            context.metadata["voice_fast_path"] = True

        # Every inbound message creates/updates a Conversation (Workflow uses ConversationId).
        # Voice already has call.id as conversation key — skip plugin overhead on hot path.
        if not (voice_fast and context.conversation_id):
            try:
                from uuid import UUID as _UUID

                from app.plugins.framework.capability import Capability
                from app.plugins.framework.context import PluginContext
                from app.plugins.framework.factory import invoke_capability

                cid_arg = _UUID(conv_id) if conv_id else None
                conv = await invoke_capability(
                    Capability.CREATE_CONVERSATION.value,
                    context=PluginContext.from_agent_context(context),
                    shop_id=shop_id,
                    channel=message.channel,
                    content=message.content,
                    sender_identifier=message.sender_identifier,
                    conversation_id=cid_arg,
                    customer_id=customer_id,
                    vehicle_id=vehicle_id,
                    attachments=list(message.attachments or []),
                    metadata=dict(message.metadata or {}),
                )
                if conv is not None and getattr(conv, "id", None):
                    context.conversation_id = str(conv.id)
                    context.metadata["conversation_id"] = str(conv.id)
            except Exception as exc:  # noqa: BLE001 — conversation is additive
                self._logger.warning("conversation.ingest_failed err=%s", exc)

        if not voice_fast:
            self._inject_memory(context, text=message.content)
        stages: dict[str, AgentResult[Any]] = {}
        stage_outputs: list[AgentStageOutput] = []
        collected: list[Decision] = []

        if not voice_fast:
            await self._publish(
                AgentEventType.INCOMING_MESSAGE.value,
                IncomingMessageEvent(
                    channel=message.channel,
                    raw_content=message.content,
                    sender_identifier=message.sender_identifier,
                    subject=message.subject,
                    received_at=message.received_at,
                    attachments=list(message.attachments or []),
                    metadata={
                        **dict(message.metadata or {}),
                        "conversation_id": context.conversation_id,
                    },
                ),
                context,
                source="orchestrator",
            )

        # 1. Communication (normalize — decide only)
        comm_result = await self._communication.run(message, context)
        stages["communication"] = comm_result
        stage_outputs.append(_stage("communication", comm_result))
        if not comm_result.success or comm_result.data is None:
            return await self._finalize(
                context,
                stages,
                stage_outputs,
                intent=None,
                decisions=collected,
                voice_fast=voice_fast,
            )

        normalized = comm_result.data
        if not voice_fast:
            await self._publish(
                AgentEventType.COMMUNICATION_NORMALIZED.value,
                CommunicationNormalizedEvent(
                    channel=normalized.channel,
                    direction=normalized.direction,
                    body=normalized.body,
                    sender=normalized.sender,
                    recipient=normalized.recipient,
                    subject=normalized.subject,
                    received_at=normalized.received_at,
                    language=normalized.language,
                    metadata=normalized.metadata,
                ),
                context,
                source="communication",
            )

        # Prefer visit anchors before intent when we already know who/which appt
        # (metadata pin or customer_id). Intent "same time" needs that clock.
        await self._enrich_schedule_context(context)

        # 2. Intent (decide only)
        intent_result = await self._intent.run(normalized, context)
        stages["intent"] = intent_result
        stage_outputs.append(_stage("intent", intent_result))
        intent_data = intent_result.data
        if intent_data and not voice_fast:
            await self._publish(
                AgentEventType.INTENT_DETECTED.value,
                IntentDetectedEvent(
                    intent=intent_data.intent.value,
                    confidence=intent_data.confidence,
                    entities=intent_data.entities,
                    secondary_intents=[i.value for i in intent_data.secondary_intents],
                    is_emergency=intent_data.is_emergency,
                    is_complaint=intent_data.is_complaint,
                    raw_excerpt=intent_data.raw_excerpt,
                ),
                context,
                source="intent",
            )

        entities = intent_data.entities if intent_data else {}

        # 3. Customer (decide) → Workflow apply
        customer_req = CustomerResolveRequest(
            name=entities.get("name"),
            phone=entities.get("phone") or message.sender_identifier,
            email=entities.get("email"),
            prefer_customer_id=context.customer_id,
            create_if_missing=True,
        )
        customer_result = await self._customer.run(customer_req, context)
        cust_decision = collect_decision(customer_result)
        if cust_decision is not None:
            collected.append(cust_decision)
            applied = await self._apply(context, [cust_decision])
            if applied and applied.customer_result:
                customer_result = AgentResult.ok(applied.customer_result)
        stages["customer"] = customer_result
        stage_outputs.append(_stage("customer", customer_result))
        if customer_result.data and customer_result.data.customer:
            cust = customer_result.data.customer
            context.customer_id = cust.id
            context.metadata["customer_snapshot"] = {
                "id": str(cust.id),
                "name": cust.name,
                "phone": cust.phone,
                "email": cust.email,
                "is_new": bool(customer_result.data.is_new),
                "tags": list(cust.tags or []),
            }
            if not voice_fast:
                await self._publish(
                    AgentEventType.CUSTOMER_RESOLVED.value,
                    CustomerResolvedEvent(
                        customer_id=cust.id,
                        is_new=customer_result.data.is_new,
                        name=cust.name,
                        phone=cust.phone,
                        email=cust.email,
                        merged_from=list(customer_result.data.merged_from),
                        profile={"tags": list(cust.tags)},
                    ),
                    context,
                    source="customer",
                )
            if not voice_fast:
                self._inject_memory(context, text=message.content)
            await self._enrich_schedule_context(context)
            # Intent ran before customer resolve; re-bind "today same time" once
            # the visit start is known from upcoming appointments.
            if intent_data is not None and isinstance(
                getattr(intent_data, "entities", None), dict
            ):
                from app.agents.intent.service import (
                    apply_same_slot_preference_to_entities,
                )

                inbound = str(
                    context.metadata.get("inbound_text") or message.content or ""
                )
                if apply_same_slot_preference_to_entities(
                    inbound, intent_data.entities, context
                ):
                    entities = intent_data.entities
        # 4. Vehicle (decide) → Workflow apply
        intent_value_for_vehicle = intent_data.intent.value if intent_data else None
        run_vehicle = self._needs_vehicle_stage(
            voice_fast=voice_fast,
            intent_value=intent_value_for_vehicle,
            entities=entities if isinstance(entities, dict) else {},
        )
        if run_vehicle:
            vehicle_req = VehicleResolveRequest(
                vin=entities.get("vin"),
                customer_id=context.customer_id,
                year=entities.get("year"),
                mileage=entities.get("mileage"),
                create_if_missing=bool(entities.get("vin")),
            )
            vehicle_result = await self._vehicle.run(vehicle_req, context)
            veh_decision = collect_decision(vehicle_result)
            if veh_decision is not None:
                collected.append(veh_decision)
                applied = await self._apply(context, [veh_decision])
                if applied and applied.vehicle_result:
                    vehicle_result = AgentResult.ok(applied.vehicle_result)
            stages["vehicle"] = vehicle_result
            stage_outputs.append(_stage("vehicle", vehicle_result))
            if vehicle_result.data and vehicle_result.data.vehicle:
                v = vehicle_result.data.vehicle
                context.vehicle_id = v.id
                if not voice_fast:
                    await self._publish(
                        AgentEventType.VEHICLE_RESOLVED.value,
                        VehicleResolvedEvent(
                            vehicle_id=v.id,
                            customer_id=v.customer_id,
                            vin=v.vin,
                            year=v.year,
                            make=v.make,
                            model=v.model,
                            mileage=v.mileage,
                            repair_history_count=len(vehicle_result.data.repair_history),
                            maintenance_timeline=[
                                {
                                    "service": m.service,
                                    "due_mileage": m.due_mileage,
                                    "status": m.status,
                                }
                                for m in vehicle_result.data.maintenance_timeline
                            ],
                        ),
                        context,
                        source="vehicle",
                    )
        else:
            vehicle_result = AgentResult.ok(None)
            stages["vehicle"] = vehicle_result


        # 5. Scheduling (decide) → Workflow apply
        # AI identifies requested service → matches catalog → AppointmentDecision;
        # Workflow validates availability and creates the appointment.
        intent_value = intent_data.intent.value if intent_data else None
        booking = self._merge_booking_context(entities, context, intent=intent_value)
        # Keep reply generators in sync with merged date/time completeness.
        if intent_data is not None and isinstance(getattr(intent_data, "entities", None), dict):
            for key in (
                "preferred_start",
                "preferred_end",
                "time_precision",
                "needs_time",
                "needs_date",
            ):
                if key in booking:
                    val = booking[key]
                    if isinstance(val, datetime):
                        intent_data.entities[key] = val.isoformat()
                    else:
                        intent_data.entities[key] = val
                else:
                    intent_data.entities.pop(key, None)
            entities = intent_data.entities
        requested_service = booking.get("requested_service") or booking.get("service")
        appointment_id = self._resolve_appointment_id(
            context, booking, intent=intent_value
        )
        service_id = None
        if booking.get("service_id"):
            try:
                service_id = UUID(str(booking["service_id"]))
            except (ValueError, TypeError):
                service_id = None
        estimated_revenue = None
        raw_price = booking.get("service_price") or booking.get("estimated_revenue")
        if raw_price is not None and str(raw_price).strip() != "":
            try:
                from decimal import Decimal

                estimated_revenue = Decimal(str(raw_price).replace("$", "").strip())
            except Exception:  # noqa: BLE001 — ignore bad price strings
                estimated_revenue = None
        preferred_start = booking.get("preferred_start")
        if isinstance(preferred_start, str):
            preferred_start = self._parse_iso_dt(preferred_start)
        preferred_end = booking.get("preferred_end")
        if isinstance(preferred_end, str):
            preferred_end = self._parse_iso_dt(preferred_end)
        time_precision = booking.get("time_precision")
        if not isinstance(time_precision, str):
            time_precision = None
        scheduling_req = SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent=intent_value,
            customer_id=context.customer_id,
            vehicle_id=context.vehicle_id,
            requested_service=requested_service,
            service_id=service_id,
            estimated_revenue=estimated_revenue,
            appointment_id=appointment_id,
            preferred_start=preferred_start if isinstance(preferred_start, datetime) else None,
            preferred_end=preferred_end if isinstance(preferred_end, datetime) else None,
            time_precision=time_precision,
            prefer_earliest=bool(booking.get("prefer_earliest")),
            prefer_latest=bool(booking.get("prefer_latest")),
            confirm_booking=bool(booking.get("booking_confirmed")),
        )
        scheduling_result = await self._scheduling.run(scheduling_req, context)
        sched_decision = collect_decision(scheduling_result)
        if sched_decision is not None and getattr(sched_decision, "action", "noop") != "noop":
            collected.append(sched_decision)
            applied = await self._apply(context, [sched_decision])
            if applied and applied.scheduling_result:
                scheduling_result = AgentResult.ok(applied.scheduling_result)
            elif (
                applied
                and getattr(applied, "errors", None)
                and getattr(sched_decision, "action", None) in {"book", "reschedule", "cancel"}
            ):
                # Persist failed — never leave the agent "recommended" success
                # so voice/SMS claim a booked appointment that isn't on the schedule.
                from app.agents.scheduling.models import SchedulingResult as SchedRes

                action = str(getattr(sched_decision, "action", "list_slots"))
                is_slot = action in {"book", "reschedule"}
                scheduling_result = AgentResult.ok(
                    SchedRes(
                        action="list_slots" if is_slot else action,
                        success=False,
                        message=(
                            "preferred_time_unavailable"
                            if is_slot
                            else (applied.errors[0] if applied.errors else "Scheduling failed")
                        ),
                        metadata={
                            "preferred_time_unavailable": is_slot,
                            "unavailable_aspect": "time",
                            "action": action,
                            "errors": list(applied.errors or []),
                        },
                        decision=sched_decision,
                    )
                )
        stages["scheduling"] = scheduling_result
        stage_outputs.append(_stage("scheduling", scheduling_result))
        if scheduling_result.data and not voice_fast:
            s = scheduling_result.data
            await self._publish(
                AgentEventType.SCHEDULING_RESULT.value,
                SchedulingResultEvent(
                    action=s.action,
                    success=s.success,
                    appointment_id=s.appointment.id if s.appointment else None,
                    slot_start=s.appointment.start if s.appointment else None,
                    slot_end=s.appointment.end if s.appointment else None,
                    available_slots=[
                        {"start": slot.start.isoformat(), "end": slot.end.isoformat()}
                        for slot in s.available_slots
                    ],
                    reminders=[
                        {"channel": r.channel, "send_at": r.send_at.isoformat(), "message": r.message}
                        for r in s.reminders
                    ],
                    message=s.message,
                ),
                context,
                source="scheduling",
            )

        # 6–8: CRM / revenue / advisor are off the voice critical path (voice memory logs turns).
        if not voice_fast:
            # 6. CRM (decide) → Workflow apply
            crm_req = CrmUpdateRequest(
                customer_id=context.customer_id,
                channel=normalized.channel,
                message=normalized.body,
                intent=intent_value,
                vehicle_id=context.vehicle_id,
            )
            crm_result = await self._crm.run(crm_req, context)
            crm_decision = collect_decision(crm_result)
            if crm_decision is not None:
                collected.append(crm_decision)
                applied = await self._apply(context, [crm_decision])
                if applied and applied.crm_result:
                    crm_result = AgentResult.ok(applied.crm_result)
            stages["crm"] = crm_result
            stage_outputs.append(_stage("crm", crm_result))
            if crm_result.data:
                c = crm_result.data
                await self._publish(
                    AgentEventType.CRM_UPDATED.value,
                    CrmUpdatedEvent(
                        customer_id=c.customer_id,
                        communication_recorded=c.communication_recorded,
                        repair_updated=c.repair_updated,
                        timeline_entries=len(c.timeline_entries),
                        customer_summary=c.customer_summary,
                    ),
                    context,
                    source="crm",
                )

            # 7. Revenue (decide only) + Marketing decisions → Workflow apply
            vehicle_data = vehicle_result.data
            revenue_req = RevenueAnalysisRequest(
                customer_id=context.customer_id,
                vehicle=vehicle_data.vehicle if vehicle_data else None,
                repair_history=vehicle_data.repair_history if vehicle_data else [],
                maintenance_timeline=vehicle_data.maintenance_timeline if vehicle_data else [],
                intent=intent_value,
            )
            revenue_result = await self._revenue.run(revenue_req, context)
            stages["revenue"] = revenue_result
            stage_outputs.append(_stage("revenue", revenue_result))
            if revenue_result.data:
                r = revenue_result.data
                await self._publish(
                    AgentEventType.REVENUE_INSIGHTS.value,
                    RevenueInsightsEvent(
                        upsell_opportunities=[
                            {
                                "service": u.service,
                                "reason": u.reason,
                                "estimated_revenue": str(u.estimated_revenue),
                                "priority": u.priority,
                            }
                            for u in r.upsell_opportunities
                        ],
                        declined_estimates=r.declined_estimates,
                        maintenance_reminders=r.maintenance_reminders,
                        lost_customer_risk=r.lost_customer_risk,
                        predicted_revenue=r.predicted_revenue,
                        notes=r.notes,
                    ),
                    context,
                    source="revenue",
                )
                rev_decision = collect_decision(revenue_result)
                if rev_decision is not None:
                    collected.append(rev_decision)
                if r.maintenance_reminders:
                    from app.workflows.enums import DomainEventType
                    from app.workflows.factory import get_workflow_runtime

                    reminder = r.maintenance_reminders[0]
                    mkt_result = await self._marketing.run(
                        MarketingRequest(
                            action_type=MarketingActionType.MAINTENANCE_REMINDER,
                            customer_id=context.customer_id,
                            channel="sms",
                            context={
                                "service": reminder.get("service", "service"),
                                "due_mileage": reminder.get("due_mileage", "—"),
                            },
                        ),
                        context,
                    )
                    mkt_decision = collect_decision(mkt_result)
                    if mkt_decision is not None:
                        collected.append(mkt_decision)
                        await get_workflow_runtime().coordinator.publish(
                            shop_id=context.shop_id,
                            event_type=DomainEventType.MAINTENANCE_REMINDER_REQUESTED,
                            payload={
                                "customer_id": str(context.customer_id) if context.customer_id else None,
                                "service": reminder.get("service"),
                                "due_mileage": reminder.get("due_mileage"),
                                "channel": "sms",
                            },
                            source="agents.revenue",
                            correlation_id=context.correlation_id,
                        )
                        await self._apply(context, [mkt_decision])

            # 8. AI Service Advisor (decide only) → Decision Objects → Workflow apply
            try:
                from app.plugins.framework.capability import Capability
                from app.plugins.framework.context import PluginContext
                from app.plugins.framework.factory import invoke_capability

                vehicle_payload = None
                repair_history: list = []
                if vehicle_result and vehicle_result.data and vehicle_result.data.vehicle:
                    v = vehicle_result.data.vehicle
                    vehicle_payload = {
                        "year": getattr(v, "year", None),
                        "make": getattr(v, "make", None),
                        "model": getattr(v, "model", None),
                        "mileage": getattr(v, "mileage", None),
                    }
                    repair_history = [
                        {
                            "service_type": getattr(r, "service_type", None),
                            "description": getattr(r, "description", None),
                        }
                        for r in (vehicle_result.data.repair_history or [])
                    ]
                customer_payload = None
                if customer_result and customer_result.data and customer_result.data.customer:
                    c = customer_result.data.customer
                    customer_payload = {
                        "name": getattr(c, "name", None),
                        "phone": getattr(c, "phone", None),
                        "email": getattr(c, "email", None),
                        "is_new": bool(customer_result.data.is_new),
                        "tags": list(getattr(c, "tags", None) or []),
                    }
                elif context.metadata.get("customer_snapshot"):
                    customer_payload = dict(context.metadata["customer_snapshot"])

                rev_meta: dict = {}
                if revenue_result and revenue_result.data:
                    r = revenue_result.data
                    rev_meta = {
                        "lost_customer_risk": getattr(r, "lost_customer_risk", 0.0),
                        "maintenance_reminders": list(
                            getattr(r, "maintenance_reminders", None) or []
                        ),
                    }

                advisor_out = await invoke_capability(
                    Capability.ANALYZE_CONVERSATION.value,
                    context=PluginContext.from_agent_context(context),
                    shop_id=context.shop_id,
                    conversation_id=context.conversation_id,
                    customer_id=context.customer_id,
                    vehicle_id=context.vehicle_id,
                    channel=context.channel,
                    inbound_text=context.metadata.get("inbound_text"),
                    intent=intent_value,
                    customer=customer_payload,
                    vehicle=vehicle_payload,
                    repair_history=repair_history,
                    mileage=(vehicle_payload or {}).get("mileage"),
                    appointments=list(context.metadata.get("upcoming_appointments") or []),
                    metadata=rev_meta,
                )
                advisor_decisions = list((advisor_out or {}).get("decisions") or [])
                collected.extend(advisor_decisions)
                stages["advisor"] = AgentResult.ok(
                    advisor_out,
                    advisor_notes=(advisor_out or {}).get("advisor_notes"),
                    queue_priority=(advisor_out or {}).get("queue_priority"),
                )
                stage_outputs.append(_stage("advisor", stages["advisor"]))
                if advisor_decisions:
                    await self._apply(context, advisor_decisions)
            except Exception as exc:  # noqa: BLE001 — advisor is additive
                self._logger.warning("advisor.stage_failed err=%s", exc)

        return await self._finalize(
            context,
            stages,
            stage_outputs,
            intent=intent_value,
            is_emergency=bool(intent_data and intent_data.is_emergency),
            is_complaint=bool(intent_data and intent_data.is_complaint),
            decisions=collected,
            voice_fast=voice_fast,
        )

    async def _finalize(
        self,
        context: AgentContext,
        stages: dict[str, AgentResult[Any]],
        stage_outputs: list[AgentStageOutput],
        *,
        intent: str | None,
        is_emergency: bool = False,
        is_complaint: bool = False,
        decisions: list[Decision] | None = None,
        voice_fast: bool = False,
    ) -> PipelineResult:
        collected = list(decisions or [])
        review = SupervisorReviewRequest(
            stages=stage_outputs,
            intent=intent,
            is_emergency=is_emergency,
            is_complaint=is_complaint,
        )
        supervisor_result = await self._supervisor.run(review, context)
        stages["supervisor"] = supervisor_result
        decision = supervisor_result.data

        if decision:
            summary_dec = SummaryDecision(
                summary=decision.owner_summary or "",
                highlights=[intent] if intent else [],
                action_items=list(decision.action_items or []),
            )
            collected.append(summary_dec)
            if decision.escalate:
                esc = EscalationDecision(
                    escalate=True,
                    reason=decision.escalation_reason or "Escalation required",
                    priority="urgent" if is_emergency else "high" if is_complaint else "normal",
                    details={"status": decision.status},
                )
                collected.append(esc)
                await self._apply(context, [esc])
            if not voice_fast:
                await self._publish(
                    AgentEventType.SUPERVISOR_DECISION.value,
                    SupervisorDecisionEvent(
                        status=decision.status,
                        escalate=decision.escalate,
                        escalation_reason=decision.escalation_reason,
                        conflicts=decision.conflicts,
                        errors=decision.errors,
                        owner_summary=decision.owner_summary,
                        agent_outputs=decision.agent_outputs,
                    ),
                    context,
                    source="supervisor",
                )
                await self._publish(
                    AgentEventType.OWNER_SUMMARY.value,
                    OwnerSummaryEvent(
                        summary=decision.owner_summary,
                        highlights=[intent] if intent else [],
                        action_items=decision.action_items,
                    ),
                    context,
                    source="supervisor",
                )
                if decision.escalate:
                    await self._publish(
                        AgentEventType.ESCALATION_REQUESTED.value,
                        EscalationRequestedEvent(
                            reason=decision.escalation_reason or "Escalation required",
                            priority="urgent"
                            if is_emergency
                            else "high"
                            if is_complaint
                            else "normal",
                            customer_id=context.customer_id,
                            details={"status": decision.status},
                        ),
                        context,
                        source="supervisor",
                    )

        success = all(
            s.success
            for name, s in stages.items()
            if name != "supervisor"
        ) and bool(decision and not decision.errors)
        escalate = bool(decision and decision.escalate) or any(
            s.escalate for s in stages.values()
        )

        if not voice_fast:
            await self._publish(
                AgentEventType.PIPELINE_COMPLETED.value,
                PipelineCompletedEvent(
                    correlation_id=context.correlation_id,
                    success=success,
                    escalate=escalate,
                    stages=list(stages.keys()),
                    summary=decision.owner_summary if decision else None,
                ),
                context,
                source="orchestrator",
            )

        if not voice_fast:
            self._capture_memory(context, stages, escalate=escalate)

        self._logger.info(
            "pipeline.completed success=%s escalate=%s decisions=%s voice_fast=%s",
            success,
            escalate,
            len(collected),
            voice_fast,
            extra=log_extra(
                correlation_id=context.correlation_id,
                shop_id=str(context.shop_id),
            ),
        )

        return PipelineResult(
            correlation_id=context.correlation_id,
            success=success,
            escalate=escalate,
            context=context,
            stages=stages,
            supervisor=decision,
            owner_summary=decision.owner_summary if decision else None,
            decisions=collected,
        )

    async def _publish(
        self,
        event_type: str,
        payload: Any,
        context: AgentContext,
        *,
        source: str,
    ) -> None:
        await self._bus.publish(
            EventEnvelope(
                event_type=event_type,
                payload=payload,
                shop_id=context.shop_id,
                correlation_id=context.correlation_id,
                source_agent=source,
            )
        )


def _stage(name: str, result: AgentResult[Any]) -> AgentStageOutput:
    return AgentStageOutput(
        agent=name,
        success=result.success,
        data=result.data,
        error=result.error,
        escalate=result.escalate,
        escalation_reason=result.escalation_reason,
    )
