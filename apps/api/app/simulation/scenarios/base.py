"""Shared scenario runner helpers — emit workflows + soft capability probes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.simulation.generators import EntityGenerator
from app.simulation.models import (
    AiDecisionRecord,
    CapabilityCallRecord,
    EventRecord,
    PluginCallRecord,
    ScenarioKind,
    SimulationRunResult,
    WorkflowStepRecord,
)
from app.workflows.enums import DomainEventType, RunStatus, StepStatus
from app.workflows.factory import WorkflowRuntime


class ScenarioContext:
    def __init__(
        self,
        *,
        runtime: WorkflowRuntime,
        shop_id: UUID,
        generator: EntityGenerator,
        scenario: ScenarioKind,
    ) -> None:
        self.runtime = runtime
        self.shop_id = shop_id
        self.gen = generator
        self.scenario = scenario
        self.result = SimulationRunResult(
            run_id=uuid4(),
            scenario=scenario,
            shop_id=shop_id,
            success=False,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )

    def add_decision(
        self,
        decision_type: str,
        *,
        confidence: float,
        accurate: bool,
        summary: str,
        **meta: Any,
    ) -> None:
        self.result.decisions.append(
            AiDecisionRecord(
                decision_type=decision_type,
                confidence=confidence,
                accurate=accurate,
                summary=summary,
                metadata=meta,
            )
        )

    def add_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.result.events.append(EventRecord(event_type=event_type, payload=payload or {}))

    async def emit(self, event_type: DomainEventType | str, payload: dict[str, Any]) -> None:
        event, runs = await self.runtime.service.emit_and_run(
            shop_id=self.shop_id,
            event_type=event_type,
            payload=payload,
            source=f"simulation.{self.scenario.value}",
        )
        self.add_event(event.event_type.value, dict(event.payload))
        for run in runs:
            self.result.workflow_names.append(run.workflow_name)
            for step in run.steps:
                self.result.workflow_steps.append(
                    WorkflowStepRecord(
                        name=f"{run.workflow_name}:{step.action_name}",
                        status=step.status.value,
                        error=step.error,
                    )
                )
                if step.status == StepStatus.FAILED:
                    self.result.errors.append(step.error or f"Failed step {step.action_name}")
            if run.status != RunStatus.COMPLETED:
                self.result.errors.append(f"Workflow {run.workflow_name} status={run.status.value}")
            if any("escalat" in (s.action_name or "").lower() for s in run.steps):
                self.result.escalated = True
            if DomainEventType.HUMAN_ESCALATION_REQUESTED.value in {
                e.event_type for e in self.result.events
            } or any(
                "escalation" in (e.event_type or "") for e in self.result.events
            ):
                self.result.escalated = True
            for e in await self.runtime.store.list_events(self.shop_id, limit=30):
                if e.event_type == DomainEventType.REVENUE_OPPORTUNITY_DETECTED:
                    self.result.revenue_opportunity_detected = True
                if e.event_type == DomainEventType.HUMAN_ESCALATION_REQUESTED:
                    self.result.escalated = True

    async def invoke_capability(
        self,
        capability: str,
        *,
        plugin: str,
        **kwargs: Any,
    ) -> None:
        try:
            from app.plugins.framework.context import PluginContext
            from app.plugins.framework.factory import ensure_default_plugins, invoke_capability

            ensure_default_plugins()
            await invoke_capability(
                capability,
                context=PluginContext.for_shop(self.shop_id),
                shop_id=self.shop_id,
                **kwargs,
            )
            self.result.capabilities.append(
                CapabilityCallRecord(capability=capability, success=True, result_summary="ok")
            )
            self.result.plugins.append(PluginCallRecord(plugin=plugin, capability=capability, success=True))
        except Exception as exc:  # noqa: BLE001 — simulation continues
            self.result.capabilities.append(
                CapabilityCallRecord(capability=capability, success=False, error=str(exc))
            )
            self.result.plugins.append(
                PluginCallRecord(plugin=plugin, capability=capability, success=False, error=str(exc))
            )
            self.result.notes.append(f"Capability {capability} soft-fail: {exc}")

    def finish(self, *, success: bool | None = None) -> SimulationRunResult:
        self.result.finished_at = datetime.now(timezone.utc)
        if success is None:
            success = len(self.result.errors) == 0 and len(self.result.workflow_names) > 0
        self.result.success = bool(success)
        return self.result


class BaseScenario:
    kind: ScenarioKind

    async def run(self, ctx: ScenarioContext) -> SimulationRunResult:
        raise NotImplementedError
