"""Central Workflow Coordinator — sole cross-module orchestration layer.

Feature modules must not import each other for orchestration. They call this
coordinator (or emit_domain_event) instead. Business logic stays in modules;
only fan-out / sequencing / live aggregation lives here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.workflows.decision_executor import DecisionExecutor, DecisionExecutionResult, DecisionPorts
from app.workflows.enums import DomainEventType, RunStatus
from app.workflows.models import DomainEvent, WorkflowRun
from app.workflows.monitoring import WorkflowMonitor
from app.workflows.runner import WorkflowRunner
from app.workflows.service import WorkflowEngineService

logger = logging.getLogger("asa.workflows.coordinator")

InvokeFn = Callable[[], Awaitable[Any]]


class WorkflowCoordinator:
    """Orchestration facade used by executive, analytics, agents, enterprise, etc."""

    def __init__(
        self,
        *,
        service: WorkflowEngineService,
        runner: WorkflowRunner,
        monitor: WorkflowMonitor,
        decision_executor: DecisionExecutor | None = None,
    ) -> None:
        self._service = service
        self._runner = runner
        self._monitor = monitor
        self._decision_executor = decision_executor or DecisionExecutor(monitor=monitor)
        self._escalations: list[dict[str, Any]] = []
        # Lazy-wire emit/escalate onto executor (may already be set by factory)
        if self._decision_executor._emit is None:  # noqa: SLF001
            self._decision_executor._emit = self._emit_for_executor  # noqa: SLF001
        if self._decision_executor._escalate is None:  # noqa: SLF001
            self._decision_executor._escalate = self._escalate_for_executor  # noqa: SLF001

    async def _emit_for_executor(self, **kwargs: Any) -> tuple[DomainEvent, list[WorkflowRun]]:
        return await self.publish(**kwargs)

    def _escalate_for_executor(
        self, *, shop_id: UUID, reason: str, details: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self.escalate_human(shop_id=shop_id, reason=reason, details=details)

    async def apply_decisions(
        self,
        *,
        shop_id: UUID,
        decisions: list[Any],
        ports: DecisionPorts,
        context: Any | None = None,
        correlation_id: str | None = None,
    ) -> DecisionExecutionResult:
        """Execute AI Decision objects — the only path for business mutations from AI."""
        return await self._decision_executor.apply(
            shop_id=shop_id,
            decisions=decisions,
            ports=ports,
            context=context,
            correlation_id=correlation_id,
        )

    @property
    def decision_executor(self) -> DecisionExecutor:
        return self._decision_executor

    async def invoke_capability(self, capability: str, **kwargs: Any) -> Any:
        """Resolve a capability via Plugin Framework registries only."""
        from app.plugins.framework.context import PluginContext
        from app.plugins.framework.factory import ensure_default_plugins, invoke_capability

        ensure_default_plugins()
        shop_id = kwargs.get("shop_id")
        context = kwargs.pop("context", None)
        if context is None and shop_id is not None:
            context = PluginContext.for_shop(shop_id)
        self._monitor.record_orchestration(f"capability:{capability}")
        return await invoke_capability(capability, context=context, **kwargs)

    # --- Publish / receive events ---

    async def publish(
        self,
        *,
        shop_id: UUID,
        event_type: DomainEventType | str,
        payload: dict[str, Any] | None = None,
        source: str = "system",
        correlation_id: str | None = None,
    ) -> tuple[DomainEvent, list[WorkflowRun]]:
        self._monitor.record_orchestration("publish")
        event, runs = await self._service.emit_and_run(
            shop_id=shop_id,
            event_type=event_type,
            payload=payload,
            source=source,
            correlation_id=correlation_id,
        )
        self._monitor.record_event(
            event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
        )
        logger.info(
            "workflow.publish source=%s type=%s shop=%s runs=%s",
            source,
            event.event_type,
            shop_id,
            len(runs),
        )
        return event, runs

    async def publish_and_invoke(
        self,
        *,
        shop_id: UUID,
        event_type: DomainEventType | str,
        payload: dict[str, Any] | None = None,
        source: str = "system",
        correlation_id: str | None = None,
        invoke: InvokeFn | None = None,
    ) -> Any:
        """Emit domain event (history + matching workflows), then run module business invoke."""
        self._monitor.record_orchestration("publish_and_invoke")
        await self.publish(
            shop_id=shop_id,
            event_type=event_type,
            payload=payload,
            source=source,
            correlation_id=correlation_id,
        )
        if invoke is None:
            return None
        return await invoke()

    # --- Live source aggregation (was scattered in executive/analytics) ---

    async def collect_live_sources(
        self, shop_id: UUID, *, now: datetime | None = None
    ) -> dict[str, Any]:
        """Pull monitors/snapshots from domain modules — only allowed here."""
        self._monitor.record_orchestration("collect_live_sources")
        now = now or datetime.now(timezone.utc)
        sources: dict[str, Any] = {}

        try:
            from app.plugins.scheduling.factory import get_scheduling_plugin
            from app.scheduling.catalog import ensure_shop_resources_synced

            plugin = get_scheduling_plugin()
            intel = getattr(plugin, "intelligence", None)
            store = getattr(intel, "_store", None) if intel is not None else None
            if store is not None:
                # Sync Team/hours from DB — seed-only ensure_shop loses roster on restart.
                try:
                    await ensure_shop_resources_synced(shop_id, store)
                except Exception:  # noqa: BLE001
                    if hasattr(store, "ensure_shop"):
                        store.ensure_shop(shop_id)
            sources["scheduling"] = await plugin.live_snapshot(shop_id, now=now)
        except Exception as exc:  # noqa: BLE001
            sources["scheduling"] = {"error": str(exc)}

        try:
            from app.plugins.revenue.factory import get_revenue_plugin

            plugin = get_revenue_plugin()
            sources["revenue"] = await plugin.live_snapshot(shop_id, now=now)
        except Exception as exc:  # noqa: BLE001
            sources["revenue"] = {"error": str(exc)}

        try:
            from app.plugins.advisor.factory import get_advisor_plugin

            advisor = get_advisor_plugin()
            sources["advisor"] = {
                "queue": list(getattr(advisor, "_queue", []) or [])[-20:],
                "health": await advisor.health_check(),
            }
        except Exception as exc:  # noqa: BLE001
            sources["advisor"] = {"error": str(exc)}

        try:
            from app.marketing.factory import peek_marketing_runtime

            mkt = peek_marketing_runtime()
            follow_up_customers = await self._marketing_follow_up_count(shop_id, mkt=mkt)
            if mkt is None:
                sources["marketing"] = {
                    "summary": {},
                    "monitor": {},
                    "cold": True,
                    "follow_up_customers": follow_up_customers,
                }
            else:
                summary = await mkt.service.analytics_summary(shop_id)
                sources["marketing"] = {
                    "summary": summary,
                    "monitor": mkt.monitor.snapshot(),
                    "follow_up_customers": follow_up_customers,
                }
        except Exception as exc:  # noqa: BLE001
            sources["marketing"] = {"error": str(exc)}

        try:
            from app.sms.runtime import peek_sms_runtime

            sms = peek_sms_runtime()
            monitor = {} if sms is None else sms.monitor.snapshot()
            durable = await self._sms_live_counts(shop_id, now=now)
            sources["sms"] = {
                "monitor": {**monitor, **durable},
                "cold": sms is None and not durable,
            }
        except Exception as exc:  # noqa: BLE001
            sources["sms"] = {"error": str(exc)}

        try:
            from app.voice.runtime import peek_voice_runtime

            voice = peek_voice_runtime()
            monitor = {} if voice is None else voice.monitor.snapshot()
            durable = await self._voice_live_counts(shop_id, now=now)
            sources["voice"] = {
                "monitor": {**monitor, **durable},
                "cold": voice is None and not durable,
            }
        except Exception as exc:  # noqa: BLE001
            sources["voice"] = {"error": str(exc)}

        try:
            sources["workflows"] = {"monitor": self._monitor.snapshot()}
        except Exception as exc:  # noqa: BLE001
            sources["workflows"] = {"error": str(exc)}

        try:
            sources["crm"] = await self._crm_live_snapshot(shop_id, now=now)
        except Exception as exc:  # noqa: BLE001
            sources["crm"] = {"error": str(exc)}

        return sources

    async def _shop_day_start_utc(self, session: Any, shop_id: UUID, *, now: datetime) -> datetime:
        from zoneinfo import ZoneInfo

        from sqlalchemy import select

        from app.infrastructure.models import ShopModel

        tz_name = await session.scalar(select(ShopModel.timezone).where(ShopModel.id == shop_id))
        try:
            shop_tz = ZoneInfo(tz_name or "America/Los_Angeles")
        except Exception:  # noqa: BLE001
            shop_tz = ZoneInfo("America/Los_Angeles")
        return (
            now.astimezone(shop_tz)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
        )

    async def _sms_live_counts(self, shop_id: UUID, *, now: datetime) -> dict[str, Any]:
        """Durable today SMS inbound/escalation counts (RLS via app.shop_id)."""
        from sqlalchemy import func, select, text

        from app.infrastructure.database import SessionLocal
        from app.infrastructure.models import SmsConversationModel, SmsMessageModel
        from app.sms.enums import SmsMessageDirection

        async with SessionLocal() as session:
            await session.execute(
                text("SELECT set_config('app.shop_id', :sid, true)"),
                {"sid": str(shop_id)},
            )
            start = await self._shop_day_start_utc(session, shop_id, now=now)
            inbound = await session.scalar(
                select(func.count())
                .select_from(SmsMessageModel)
                .where(
                    SmsMessageModel.shop_id == shop_id,
                    SmsMessageModel.direction == SmsMessageDirection.INBOUND.value,
                    SmsMessageModel.created_at >= start,
                )
            )
            escalations = await session.scalar(
                select(func.count())
                .select_from(SmsConversationModel)
                .where(
                    SmsConversationModel.shop_id == shop_id,
                    SmsConversationModel.escalate.is_(True),
                    SmsConversationModel.last_message_at >= start,
                )
            )
        return {
            "inbound_received": int(inbound or 0),
            "escalations": int(escalations or 0),
            "source": "database",
        }

    async def _voice_live_counts(self, shop_id: UUID, *, now: datetime) -> dict[str, Any]:
        """Durable today voice call counts (RLS via app.shop_id)."""
        from sqlalchemy import func, select, text

        from app.infrastructure.database import SessionLocal
        from app.infrastructure.models import VoiceCallModel
        from app.voice.enums import VoiceCallStatus

        async with SessionLocal() as session:
            await session.execute(
                text("SELECT set_config('app.shop_id', :sid, true)"),
                {"sid": str(shop_id)},
            )
            start = await self._shop_day_start_utc(session, shop_id, now=now)
            started = await session.scalar(
                select(func.count())
                .select_from(VoiceCallModel)
                .where(
                    VoiceCallModel.shop_id == shop_id,
                    VoiceCallModel.created_at >= start,
                )
            )
            missed = await session.scalar(
                select(func.count())
                .select_from(VoiceCallModel)
                .where(
                    VoiceCallModel.shop_id == shop_id,
                    VoiceCallModel.created_at >= start,
                    VoiceCallModel.status.in_(
                        (
                            VoiceCallStatus.FAILED.value,
                            VoiceCallStatus.NO_ANSWER.value,
                        )
                    ),
                )
            )
            escalations = await session.scalar(
                select(func.count())
                .select_from(VoiceCallModel)
                .where(
                    VoiceCallModel.shop_id == shop_id,
                    VoiceCallModel.created_at >= start,
                    VoiceCallModel.escalate.is_(True),
                )
            )
        return {
            "calls_started": int(started or 0),
            # Dashboard "AI calls handled" uses call count (not turns). Soft-deleted
            # rows still count so purging call history does not shrink today's metric.
            "turns": int(started or 0),
            "missed_calls": int(missed or 0),
            "escalations": int(escalations or 0),
            "source": "database",
        }

    async def _marketing_follow_up_count(self, shop_id: UUID, *, mkt: Any = None) -> int:
        """Unique customers in Marketing suggested-action audiences (RLS via app.shop_id)."""
        from sqlalchemy import text

        from app.infrastructure.database import SessionLocal
        from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
        from app.marketing.audience import count_follow_up_customers

        exclude = None
        if mkt is not None and hasattr(mkt, "service"):

            async def _exclude(ctype: str):
                return await mkt.service.customers_in_recommendation_cooldown(shop_id, ctype)

            exclude = _exclude

        async with SessionLocal() as session:
            await session.execute(
                text("SELECT set_config('app.shop_id', :sid, true)"),
                {"sid": str(shop_id)},
            )
            uow = SqlAlchemyUnitOfWork(session)
            return await count_follow_up_customers(
                uow, shop_id, exclude_customer_ids=exclude
            )

    async def _crm_live_snapshot(self, shop_id: UUID, *, now: datetime) -> dict[str, Any]:
        """Count today's CRM creates + walk-in arrivals; list in-shop walk-ins.

        Must set app.shop_id — customers/walk_ins tables use RLS.
        Day boundary follows the shop timezone (default America/Los_Angeles).
        open_walk_ins feeds the executive Repair Status widget
        (Waiting / Active / Scheduled via linked appointments).
        """
        from zoneinfo import ZoneInfo

        from sqlalchemy import func, select, text

        from app.infrastructure.database import SessionLocal
        from app.infrastructure.models import (
            CustomerModel,
            ShopModel,
            VehicleModel,
            WalkInVisitModel,
        )

        async with SessionLocal() as session:
            await session.execute(
                text("SELECT set_config('app.shop_id', :sid, true)"),
                {"sid": str(shop_id)},
            )
            tz_name = await session.scalar(
                select(ShopModel.timezone).where(ShopModel.id == shop_id)
            )
            try:
                shop_tz = ZoneInfo(tz_name or "America/Los_Angeles")
            except Exception:  # noqa: BLE001
                shop_tz = ZoneInfo("America/Los_Angeles")
            start = (
                now.astimezone(shop_tz)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .astimezone(timezone.utc)
            )
            customers_today = await session.scalar(
                select(func.count())
                .select_from(CustomerModel)
                .where(
                    CustomerModel.shop_id == shop_id,
                    CustomerModel.created_at >= start,
                )
            )
            walk_ins_today = await session.scalar(
                select(func.count())
                .select_from(WalkInVisitModel)
                .where(
                    WalkInVisitModel.shop_id == shop_id,
                    WalkInVisitModel.arrived_at >= start,
                )
            )
            customers_total = await session.scalar(
                select(func.count())
                .select_from(CustomerModel)
                .where(CustomerModel.shop_id == shop_id)
            )
            # In-shop walk-ins for Repair Status (open + converted; exclude closed/cancelled).
            open_rows = (
                await session.execute(
                    select(WalkInVisitModel, VehicleModel)
                    .join(
                        VehicleModel,
                        VehicleModel.id == WalkInVisitModel.vehicle_id,
                    )
                    .where(
                        WalkInVisitModel.shop_id == shop_id,
                        WalkInVisitModel.status.in_(("open", "converted")),
                    )
                    .order_by(WalkInVisitModel.arrived_at.desc())
                    .limit(40)
                )
            ).all()
            open_walk_ins: list[dict[str, Any]] = []
            for visit, vehicle in open_rows:
                arrived = visit.arrived_at
                if arrived is not None and arrived.tzinfo is None:
                    arrived = arrived.replace(tzinfo=timezone.utc)
                open_walk_ins.append(
                    {
                        "id": str(visit.id),
                        "complaint": visit.complaint,
                        "status": visit.status,
                        "arrived_at": arrived.isoformat() if arrived else None,
                        "vehicle_id": str(vehicle.id),
                        "customer_id": (
                            str(visit.customer_id)
                            if visit.customer_id
                            else (
                                str(vehicle.customer_id)
                                if vehicle.customer_id
                                else None
                            )
                        ),
                        "vehicle_label": f"{vehicle.year} {vehicle.make} {vehicle.model}".strip(),
                        "license_plate": vehicle.license_plate,
                    }
                )
        return {
            "customers_today": int(customers_today or 0),
            "walk_ins_today": int(walk_ins_today or 0),
            "customers_total": int(customers_total or 0),
            "open_walk_ins": open_walk_ins,
        }

    async def get_shop_analytics_overlay(self, shop_id: UUID) -> dict[str, Any]:
        """Franchise overlay — modules must not import analytics directly."""
        return self.get_shop_analytics_overlay_sync(shop_id)

    def get_shop_analytics_overlay_sync(self, shop_id: UUID) -> dict[str, Any]:
        """Sync variant for sync callers (franchise engine)."""
        self._monitor.record_orchestration("analytics_overlay")
        try:
            from app.analytics.factory import get_analytics_runtime

            snap = get_analytics_runtime().service.dashboard(shop_id, force=False)
            by_id = {k.id.value: k.value for k in snap.kpis}
            return {
                "revenue": float(by_id.get("revenue", 0) or 0),
                "retention": float(by_id.get("retention", 0) or 0),
                "ai_success_rate": float(by_id.get("ai_success_rate", 0) or 0),
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def collect_monitor_snapshots(self, shop_id: UUID) -> dict[str, Any]:
        """Sync monitor-only aggregation for analytics (no async IO)."""
        _ = shop_id
        self._monitor.record_orchestration("collect_monitor_snapshots")
        sources: dict[str, Any] = {}
        try:
            from app.marketing.factory import peek_marketing_runtime

            m = peek_marketing_runtime()
            sources["marketing"] = (
                {"monitor": {}, "cold": True}
                if m is None
                else {"monitor": m.monitor.snapshot()}
            )
        except Exception as exc:  # noqa: BLE001
            sources["marketing"] = {"error": str(exc)}
        try:
            from app.plugins.scheduling.factory import get_scheduling_plugin

            plugin = get_scheduling_plugin()
            mon = getattr(plugin, "monitor", None)
            if mon is not None and hasattr(mon, "snapshot"):
                sources["scheduling"] = {"monitor": mon.snapshot()}
            else:
                sources["scheduling"] = {"monitor": {}}
        except Exception as exc:  # noqa: BLE001
            sources["scheduling"] = {"error": str(exc)}
        try:
            from app.sms.runtime import peek_sms_runtime

            sms = peek_sms_runtime()
            sources["sms"] = (
                {"cold": True} if sms is None else sms.monitor.snapshot()
            )
        except Exception as exc:  # noqa: BLE001
            sources["sms"] = {"error": str(exc)}
        try:
            from app.voice.runtime import peek_voice_runtime

            voice = peek_voice_runtime()
            sources["voice"] = (
                {"cold": True} if voice is None else voice.monitor.snapshot()
            )
        except Exception as exc:  # noqa: BLE001
            sources["voice"] = {"error": str(exc)}
        return sources

    def resolve_scheduling_agent_store(self) -> Any:
        """Shared scheduling agent store via Scheduling Plugin (no direct scheduling import)."""
        self._monitor.record_orchestration("resolve_scheduling_agent_store")
        from app.plugins.scheduling.factory import get_scheduling_plugin

        return get_scheduling_plugin().store

    def resolve_conversation_plugin(self) -> Any:
        """Conversation Plugin — Workflow uses ConversationId across channels."""
        self._monitor.record_orchestration("resolve_conversation_plugin")
        from app.plugins.conversation.factory import get_conversation_plugin

        return get_conversation_plugin()

    def resolve_advisor_plugin(self) -> Any:
        """AI Service Advisor — decide-only; Workflow applies returned Decisions."""
        self._monitor.record_orchestration("resolve_advisor_plugin")
        from app.plugins.advisor.factory import get_advisor_plugin

        return get_advisor_plugin()

    def resolve_scheduling_agents(self) -> Any:
        """Scheduling agents façade via Scheduling Plugin only (no direct scheduling import)."""
        self._monitor.record_orchestration("resolve_scheduling_agents")
        from app.plugins.scheduling.factory import get_scheduling_plugin

        plugin = get_scheduling_plugin()
        if plugin.agents is not None:
            return plugin.agents
        from app.agents.factory import build_agent_runtime

        return build_agent_runtime(scheduling_store=plugin.store)

    def resolve_memory_service(self) -> Any:
        """Long-term memory service — agents must not import memory factory directly."""
        self._monitor.record_orchestration("resolve_memory_service")
        from app.memory.factory import get_memory_runtime

        return get_memory_runtime().service

    # --- Control: pause / resume / retry / history ---

    async def pause_run(self, shop_id: UUID, run_id: UUID) -> WorkflowRun:
        self._monitor.record_orchestration("pause")
        return await self._runner.pause(shop_id, run_id)

    async def resume_run(self, shop_id: UUID, run_id: UUID) -> WorkflowRun:
        self._monitor.record_orchestration("resume")
        return await self._runner.resume(shop_id, run_id)

    async def retry_run(self, shop_id: UUID, run_id: UUID) -> WorkflowRun:
        """Force-retry a waiting/failed run from the first incomplete step."""
        self._monitor.record_orchestration("retry")
        run = await self._service.get_run(shop_id, run_id)
        if run.status == RunStatus.PAUSED:
            return await self.resume_run(shop_id, run_id)
        # Drain matching retries if any; otherwise resume-like re-execute
        await self._service.process_retries()
        return await self._service.get_run(shop_id, run_id)

    async def workflow_history(
        self, shop_id: UUID, *, workflow_id: UUID | None = None, limit: int = 50
    ) -> list[WorkflowRun]:
        self._monitor.record_orchestration("history")
        return await self._service.list_runs(shop_id, workflow_id=workflow_id, limit=limit)

    def escalate_human(
        self,
        *,
        shop_id: UUID,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._monitor.record_orchestration("human_escalation")
        entry = {
            "shop_id": str(shop_id),
            "reason": reason,
            "details": details or {},
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self._escalations.append(entry)
        logger.warning("workflow.human_escalation shop=%s reason=%s", shop_id, reason)
        return entry

    @property
    def escalations(self) -> list[dict[str, Any]]:
        return list(self._escalations)
