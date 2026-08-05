"""Workflow engine service — CRUD + emit + history + debugger."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.workflows.bus import WorkflowEventBus
from app.workflows.enums import (
    ActionType,
    ConditionOperator,
    DomainEventType,
    WorkflowStatus,
)
from app.workflows.models import (
    DebuggerFrame,
    DomainEvent,
    RetryPolicy,
    WorkflowAction,
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowRun,
)
from app.workflows.retry_queue import RetryQueue
from app.workflows.runner import WorkflowRunner
from app.workflows.store import WorkflowStorePort, new_workflow


class WorkflowEngineService:
    def __init__(
        self,
        *,
        store: WorkflowStorePort,
        bus: WorkflowEventBus,
        runner: WorkflowRunner,
        retry_queue: RetryQueue,
    ) -> None:
        self._store = store
        self._bus = bus
        self._runner = runner
        self._retry = retry_queue

    # --- Events ---

    async def emit(
        self,
        *,
        shop_id: UUID,
        event_type: DomainEventType | str,
        payload: dict[str, Any] | None = None,
        source: str = "api",
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[DomainEvent, list[WorkflowRun]]:
        return await self.emit_and_run(
            shop_id=shop_id,
            event_type=event_type,
            payload={**(payload or {}), **({"_metadata": metadata} if metadata else {})},
            source=source,
            correlation_id=correlation_id,
        )
    async def emit_and_run(
        self,
        *,
        shop_id: UUID,
        event_type: DomainEventType | str,
        payload: dict[str, Any] | None = None,
        source: str = "api",
        correlation_id: str | None = None,
    ) -> tuple[DomainEvent, list[WorkflowRun]]:
        et = event_type if isinstance(event_type, DomainEventType) else DomainEventType(event_type)
        event = DomainEvent(
            event_type=et,
            shop_id=shop_id,
            payload=payload or {},
            correlation_id=correlation_id or str(uuid4()),
            source=source,
            occurred_at=datetime.now(timezone.utc),
        )
        await self._store.append_event(event)
        # Observers (e.g. admin notification center) — not workflow handlers (*).
        await self._bus.notify_observers(event)
        runs = await self._runner.handle_event(event)
        return event, runs

    # --- Workflows CRUD ---

    async def list_workflows(
        self, shop_id: UUID, *, status: WorkflowStatus | None = None
    ) -> list[WorkflowDefinition]:
        return await self._store.list_workflows(shop_id, status=status)

    async def get_workflow(self, shop_id: UUID, workflow_id: UUID) -> WorkflowDefinition:
        wf = await self._store.get_workflow(shop_id, workflow_id)
        if wf is None:
            raise LookupError("Workflow not found")
        return wf

    async def create_workflow(
        self,
        *,
        shop_id: UUID,
        name: str,
        trigger: DomainEventType | str,
        description: str = "",
        conditions: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
        retry: dict[str, Any] | None = None,
        status: WorkflowStatus = WorkflowStatus.ACTIVE,
        tags: list[str] | None = None,
    ) -> WorkflowDefinition:
        et = trigger if isinstance(trigger, DomainEventType) else DomainEventType(trigger)
        wf = new_workflow(
            shop_id=shop_id,
            name=name,
            trigger=et,
            description=description,
            conditions=[_parse_condition(c) for c in (conditions or [])],
            actions=[_parse_action(a, i) for i, a in enumerate(actions or [], start=1)],
            retry=_parse_retry(retry),
            status=status,
            tags=tags or [],
        )
        return await self._store.save_workflow(wf)

    async def update_workflow(
        self,
        *,
        shop_id: UUID,
        workflow_id: UUID,
        patch: dict[str, Any],
    ) -> WorkflowDefinition:
        wf = await self.get_workflow(shop_id, workflow_id)
        if wf.shop_id is None:
            raise PermissionError("Cannot modify global template; clone it first")
        if "name" in patch and patch["name"]:
            wf.name = str(patch["name"])
        if "description" in patch:
            wf.description = str(patch["description"] or "")
        if "trigger" in patch and patch["trigger"]:
            wf.trigger = DomainEventType(patch["trigger"])
        if "status" in patch and patch["status"]:
            wf.status = WorkflowStatus(patch["status"])
        if "conditions" in patch and patch["conditions"] is not None:
            wf.conditions = [_parse_condition(c) for c in patch["conditions"]]
        if "actions" in patch and patch["actions"] is not None:
            wf.actions = [_parse_action(a, i) for i, a in enumerate(patch["actions"], start=1)]
        if "retry" in patch and patch["retry"] is not None:
            wf.retry = _parse_retry(patch["retry"])
        if "tags" in patch and patch["tags"] is not None:
            wf.tags = list(patch["tags"])
        wf.version += 1
        return await self._store.save_workflow(wf)

    async def clone_workflow(self, shop_id: UUID, workflow_id: UUID) -> WorkflowDefinition:
        src = await self.get_workflow(shop_id, workflow_id)
        clone = WorkflowDefinition(
            id=uuid4(),
            shop_id=shop_id,
            name=f"{src.name} (copy)",
            description=src.description,
            trigger=src.trigger,
            conditions=list(src.conditions),
            actions=[
                WorkflowAction(
                    type=a.type,
                    name=a.name,
                    config=dict(a.config),
                    order=a.order,
                    continue_on_error=a.continue_on_error,
                    compensate=dict(a.compensate),
                )
                for a in src.actions
            ],
            retry=RetryPolicy(
                max_attempts=src.retry.max_attempts,
                backoff_ms=src.retry.backoff_ms,
                backoff_multiplier=src.retry.backoff_multiplier,
                max_backoff_ms=src.retry.max_backoff_ms,
            ),
            status=WorkflowStatus.DRAFT,
            tags=list(src.tags),
        )
        return await self._store.save_workflow(clone)

    async def delete_workflow(self, shop_id: UUID, workflow_id: UUID) -> None:
        ok = await self._store.delete_workflow(shop_id, workflow_id)
        if not ok:
            raise LookupError("Workflow not found or not deletable")

    # --- Runs / history / debugger ---

    async def list_runs(
        self, shop_id: UUID, *, workflow_id: UUID | None = None, limit: int = 50
    ) -> list[WorkflowRun]:
        return await self._store.list_runs(shop_id, workflow_id=workflow_id, limit=limit)

    async def get_run(self, shop_id: UUID, run_id: UUID) -> WorkflowRun:
        run = await self._store.get_run(shop_id, run_id)
        if run is None:
            raise LookupError("Run not found")
        return run

    async def rollback(self, shop_id: UUID, run_id: UUID) -> WorkflowRun:
        return await self._runner.rollback(shop_id, run_id)

    async def pause(self, shop_id: UUID, run_id: UUID) -> WorkflowRun:
        return await self._runner.pause(shop_id, run_id)

    async def resume(self, shop_id: UUID, run_id: UUID) -> WorkflowRun:
        return await self._runner.resume(shop_id, run_id)

    async def process_retries(self) -> list[WorkflowRun]:
        return await self._runner.process_retries()

    async def list_events(
        self, shop_id: UUID, *, limit: int = 100, event_type: str | None = None
    ) -> list[DomainEvent]:
        return await self._store.list_events(shop_id, limit=limit, event_type=event_type)

    async def debug_run(
        self, shop_id: UUID, run_id: UUID, *, step_index: int = 0
    ) -> DebuggerFrame:
        run = await self.get_run(shop_id, run_id)
        return self._runner.debugger_frame(run, step_index=step_index)

    def list_event_types(self) -> list[str]:
        return [e.value for e in DomainEventType]

    def list_action_types(self) -> list[str]:
        return [a.value for a in ActionType]


def _parse_condition(raw: dict[str, Any]) -> WorkflowCondition:
    return WorkflowCondition(
        field=str(raw["field"]),
        operator=ConditionOperator(raw.get("operator", "eq")),
        value=raw.get("value"),
    )


def _parse_action(raw: dict[str, Any], order: int) -> WorkflowAction:
    return WorkflowAction(
        id=UUID(raw["id"]) if raw.get("id") else uuid4(),
        type=ActionType(raw["type"]),
        name=str(raw.get("name") or raw["type"]),
        config=dict(raw.get("config") or {}),
        order=int(raw.get("order") or order),
        continue_on_error=bool(raw.get("continue_on_error", False)),
        compensate=dict(raw.get("compensate") or {}),
    )


def _parse_retry(raw: dict[str, Any] | None) -> RetryPolicy:
    if not raw:
        return RetryPolicy()
    return RetryPolicy(
        max_attempts=int(raw.get("max_attempts", 3)),
        backoff_ms=int(raw.get("backoff_ms", 1000)),
        backoff_multiplier=float(raw.get("backoff_multiplier", 2.0)),
        max_backoff_ms=int(raw.get("max_backoff_ms", 60_000)),
    )
