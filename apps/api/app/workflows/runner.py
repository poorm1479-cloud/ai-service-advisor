"""Workflow runner — execute definitions against domain events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.workflows.actions import ActionExecutor
from app.workflows.bus import WorkflowEventBus
from app.workflows.conditions import evaluate_conditions
from app.workflows.enums import (
    DomainEventType,
    RetryState,
    RunStatus,
    StepStatus,
)
from app.workflows.models import (
    DebuggerFrame,
    DomainEvent,
    StepLog,
    WorkflowDefinition,
    WorkflowRun,
)
from app.workflows.retry_queue import RetryQueue
from app.workflows.store import WorkflowStorePort


class WorkflowRunner:
    def __init__(
        self,
        *,
        store: WorkflowStorePort,
        bus: WorkflowEventBus,
        retry_queue: RetryQueue,
        executor: ActionExecutor | None = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self._retry = retry_queue
        self._executor = executor or ActionExecutor(emit=self._bus.publish)

    async def handle_event(self, event: DomainEvent) -> list[WorkflowRun]:
        workflows = await self._store.find_by_trigger(event.shop_id, event.event_type)
        runs: list[WorkflowRun] = []
        for wf in workflows:
            matched, failures = evaluate_conditions(
                wf.conditions, payload=event.payload, context={}
            )
            if not matched:
                continue
            run = await self._start_run(wf, event)
            run.logs.append(f"Conditions matched" if not failures else f"Conditions: {failures}")
            await self._execute_run(run, wf, event)
            runs.append(run)
        return runs

    async def _start_run(self, wf: WorkflowDefinition, event: DomainEvent) -> WorkflowRun:
        now = datetime.now(timezone.utc)
        run = WorkflowRun(
            id=uuid4(),
            shop_id=event.shop_id,
            workflow_id=wf.id,
            workflow_name=wf.name,
            workflow_version=wf.version,
            trigger_event_id=event.event_id,
            trigger_event_type=event.event_type,
            correlation_id=event.correlation_id,
            status=RunStatus.RUNNING,
            context={"payload": dict(event.payload)},
            started_at=now,
            logs=[f"Triggered by {event.event_type.value} ({event.event_id})"],
        )
        actions = sorted(wf.actions, key=lambda a: a.order)
        for action in actions:
            run.steps.append(
                StepLog(
                    action_id=action.id,
                    action_type=action.type.value,
                    action_name=action.name or action.type.value,
                    status=StepStatus.PENDING,
                    input={"config": dict(action.config)},
                )
            )
        return await self._store.save_run(run)

    async def _execute_run(
        self,
        run: WorkflowRun,
        wf: WorkflowDefinition,
        event: DomainEvent,
        *,
        from_step: int = 0,
    ) -> WorkflowRun:
        actions = sorted(wf.actions, key=lambda a: a.order)
        for idx in range(from_step, len(actions)):
            if run.status == RunStatus.PAUSED:
                run.logs.append(f"Paused before step {idx}")
                await self._store.save_run(run)
                return run
            action = actions[idx]
            step = run.steps[idx]
            if step.status == StepStatus.SUCCEEDED:
                continue
            step.status = StepStatus.RUNNING
            step.attempt += 1
            step.started_at = datetime.now(timezone.utc)
            run.logs.append(f"Step {idx + 1}: {step.action_name} started (attempt {step.attempt})")
            await self._store.save_run(run)

            try:
                output = await self._executor.execute(
                    action,
                    shop_id=run.shop_id,
                    payload=event.payload,
                    context=run.context,
                    correlation_id=run.correlation_id,
                )
                step.output = output
                step.status = StepStatus.SUCCEEDED
                step.finished_at = datetime.now(timezone.utc)
                step.compensation = dict(action.compensate)
                run.logs.append(f"Step {idx + 1}: {step.action_name} succeeded")
            except Exception as exc:  # noqa: BLE001
                step.error = str(exc)
                step.status = StepStatus.FAILED
                step.finished_at = datetime.now(timezone.utc)
                run.logs.append(f"Step {idx + 1}: {step.action_name} failed: {exc}")
                if action.continue_on_error:
                    step.status = StepStatus.SKIPPED
                    continue
                retry_item = await self._retry.schedule(
                    shop_id=run.shop_id,
                    run=run,
                    step_id=step.id,
                    attempt=step.attempt,
                    policy=wf.retry,
                    error=str(exc),
                )
                if retry_item:
                    step.status = StepStatus.RETRYING
                    run.status = RunStatus.WAITING_RETRY
                    run.logs.append(
                        f"Scheduled retry {retry_item.attempt}/{retry_item.max_attempts} "
                        f"at {retry_item.next_attempt_at.isoformat()}"
                    )
                    await self._store.save_run(run)
                    return run

                run.status = RunStatus.FAILED
                run.error = str(exc)
                run.finished_at = datetime.now(timezone.utc)
                await self._store.save_run(run)
                await self._bus.publish(
                    DomainEvent(
                        event_type=DomainEventType.WORKFLOW_FAILED,
                        shop_id=run.shop_id,
                        payload={"run_id": str(run.id), "error": str(exc)},
                        correlation_id=run.correlation_id,
                        source="workflow.runner",
                        occurred_at=datetime.now(timezone.utc),
                    )
                )
                return run

            await self._store.save_run(run)

        run.status = RunStatus.COMPLETED
        run.finished_at = datetime.now(timezone.utc)
        run.logs.append("Workflow completed")
        await self._store.save_run(run)
        await self._bus.publish(
            DomainEvent(
                event_type=DomainEventType.WORKFLOW_COMPLETED,
                shop_id=run.shop_id,
                payload={"run_id": str(run.id), "workflow_id": str(wf.id)},
                correlation_id=run.correlation_id,
                source="workflow.runner",
                occurred_at=datetime.now(timezone.utc),
            )
        )
        return run

    async def pause(self, shop_id: UUID, run_id: UUID) -> WorkflowRun:
        run = await self._store.get_run(shop_id, run_id)
        if run is None:
            raise LookupError("Workflow run not found")
        if run.status not in {RunStatus.RUNNING, RunStatus.WAITING_RETRY, RunStatus.PENDING}:
            raise ValueError(f"Cannot pause run in status {run.status.value}")
        run.status = RunStatus.PAUSED
        run.logs.append("Run paused by coordinator")
        await self._store.save_run(run)
        await self._bus.publish(
            DomainEvent(
                event_type=DomainEventType.WORKFLOW_PAUSED,
                shop_id=shop_id,
                payload={"run_id": str(run.id)},
                correlation_id=run.correlation_id,
                source="workflow.runner",
                occurred_at=datetime.now(timezone.utc),
            )
        )
        return run

    async def resume(self, shop_id: UUID, run_id: UUID) -> WorkflowRun:
        run = await self._store.get_run(shop_id, run_id)
        if run is None:
            raise LookupError("Workflow run not found")
        if run.status != RunStatus.PAUSED:
            raise ValueError(f"Cannot resume run in status {run.status.value}")
        wf = await self._store.get_workflow(shop_id, run.workflow_id)
        if wf is None:
            raise LookupError("Workflow definition not found")
        from_step = next(
            (i for i, s in enumerate(run.steps) if s.status != StepStatus.SUCCEEDED),
            len(run.steps),
        )
        event = DomainEvent(
            event_type=run.trigger_event_type,
            shop_id=run.shop_id,
            payload=dict(run.context.get("payload") or {}),
            event_id=run.trigger_event_id,
            correlation_id=run.correlation_id,
            source="workflow.resume",
            occurred_at=datetime.now(timezone.utc),
        )
        run.status = RunStatus.RUNNING
        run.logs.append(f"Run resumed from step {from_step}")
        await self._bus.publish(
            DomainEvent(
                event_type=DomainEventType.WORKFLOW_RESUMED,
                shop_id=shop_id,
                payload={"run_id": str(run.id), "from_step": from_step},
                correlation_id=run.correlation_id,
                source="workflow.runner",
                occurred_at=datetime.now(timezone.utc),
            )
        )
        return await self._execute_run(run, wf, event, from_step=from_step)

    async def process_retries(self, *, now: datetime | None = None) -> list[WorkflowRun]:
        due = await self._retry.due(now=now)
        completed: list[WorkflowRun] = []
        for item in due:
            await self._retry.mark(item, RetryState.IN_FLIGHT)
            run = await self._store.get_run(item.shop_id, item.run_id)
            if run is None:
                await self._retry.mark(item, RetryState.CANCELLED)
                continue
            wf = await self._store.get_workflow(item.shop_id, run.workflow_id)
            if wf is None:
                await self._retry.mark(item, RetryState.CANCELLED)
                continue
            step_index = next((i for i, s in enumerate(run.steps) if s.id == item.step_id), None)
            if step_index is None:
                await self._retry.mark(item, RetryState.CANCELLED)
                continue
            event = DomainEvent(
                event_type=run.trigger_event_type,
                shop_id=run.shop_id,
                payload=dict(run.context.get("payload") or {}),
                event_id=run.trigger_event_id,
                correlation_id=run.correlation_id,
                source="workflow.retry",
                occurred_at=datetime.now(timezone.utc),
            )
            run.status = RunStatus.RUNNING
            run.steps[step_index].status = StepStatus.PENDING
            await self._execute_run(run, wf, event, from_step=step_index)
            if run.status == RunStatus.COMPLETED:
                await self._retry.mark(item, RetryState.SUCCEEDED)
            elif run.status == RunStatus.WAITING_RETRY:
                await self._retry.mark(item, RetryState.SUCCEEDED)  # superseded by new retry
            elif run.status == RunStatus.FAILED:
                if item.attempt >= item.max_attempts:
                    await self._retry.mark(item, RetryState.EXHAUSTED)
                else:
                    await self._retry.mark(item, RetryState.SUCCEEDED)
            completed.append(run)
        return completed

    async def rollback(self, shop_id: UUID, run_id: UUID) -> WorkflowRun:
        run = await self._store.get_run(shop_id, run_id)
        if run is None:
            raise LookupError("Workflow run not found")
        wf = await self._store.get_workflow(shop_id, run.workflow_id)
        if wf is None:
            raise LookupError("Workflow definition not found")

        actions_by_id = {a.id: a for a in wf.actions}
        for step in reversed(run.steps):
            if step.status != StepStatus.SUCCEEDED:
                continue
            action = actions_by_id.get(step.action_id) if step.action_id else None
            if action is None:
                continue
            try:
                result = await self._executor.compensate(
                    action,
                    step.output,
                    shop_id=shop_id,
                    correlation_id=run.correlation_id,
                )
                step.status = StepStatus.ROLLED_BACK
                step.compensation = {**step.compensation, **result}
                run.logs.append(f"Rolled back: {step.action_name}")
            except Exception as exc:  # noqa: BLE001
                run.logs.append(f"Rollback failed for {step.action_name}: {exc}")

        run.status = RunStatus.ROLLED_BACK
        run.rolled_back_at = datetime.now(timezone.utc)
        run.finished_at = run.finished_at or run.rolled_back_at
        await self._store.save_run(run)
        await self._bus.publish(
            DomainEvent(
                event_type=DomainEventType.WORKFLOW_ROLLED_BACK,
                shop_id=shop_id,
                payload={"run_id": str(run.id)},
                correlation_id=run.correlation_id,
                source="workflow.runner",
                occurred_at=datetime.now(timezone.utc),
            )
        )
        return run

    def debugger_frame(self, run: WorkflowRun, *, step_index: int = 0) -> DebuggerFrame:
        step = run.steps[step_index] if 0 <= step_index < len(run.steps) else None
        return DebuggerFrame(
            run_id=run.id,
            step_index=step_index,
            status=run.status,
            context=dict(run.context),
            current_step=step,
            logs=list(run.logs),
        )
