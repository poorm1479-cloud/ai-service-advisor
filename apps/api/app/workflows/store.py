"""Workflow storage port + in-memory implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from app.workflows.enums import DomainEventType, RetryState, RunStatus, WorkflowStatus
from app.workflows.models import DomainEvent, RetryItem, WorkflowDefinition, WorkflowRun


class WorkflowStorePort(Protocol):
    async def save_workflow(self, wf: WorkflowDefinition) -> WorkflowDefinition: ...

    async def get_workflow(self, shop_id: UUID, workflow_id: UUID) -> WorkflowDefinition | None: ...

    async def list_workflows(
        self, shop_id: UUID, *, status: WorkflowStatus | None = None
    ) -> list[WorkflowDefinition]: ...

    async def delete_workflow(self, shop_id: UUID, workflow_id: UUID) -> bool: ...

    async def find_by_trigger(
        self, shop_id: UUID, event_type: DomainEventType
    ) -> list[WorkflowDefinition]: ...

    async def save_run(self, run: WorkflowRun) -> WorkflowRun: ...

    async def get_run(self, shop_id: UUID, run_id: UUID) -> WorkflowRun | None: ...

    async def list_runs(
        self, shop_id: UUID, *, workflow_id: UUID | None = None, limit: int = 50
    ) -> list[WorkflowRun]: ...

    async def append_event(self, event: DomainEvent) -> DomainEvent: ...

    async def list_events(
        self, shop_id: UUID, *, limit: int = 100, event_type: str | None = None
    ) -> list[DomainEvent]: ...

    async def enqueue_retry(self, item: RetryItem) -> RetryItem: ...

    async def list_due_retries(self, *, now: datetime, limit: int = 50) -> list[RetryItem]: ...

    async def save_retry(self, item: RetryItem) -> RetryItem: ...

    async def get_retry(self, retry_id: UUID) -> RetryItem | None: ...


class InMemoryWorkflowStore:
    def __init__(self) -> None:
        self.workflows: dict[UUID, WorkflowDefinition] = {}
        self.runs: dict[UUID, WorkflowRun] = {}
        self.events: list[DomainEvent] = []
        self.retries: dict[UUID, RetryItem] = {}

    async def save_workflow(self, wf: WorkflowDefinition) -> WorkflowDefinition:
        now = datetime.now(timezone.utc)
        if wf.created_at is None:
            wf.created_at = now
        wf.updated_at = now
        self.workflows[wf.id] = wf
        return wf

    async def get_workflow(self, shop_id: UUID, workflow_id: UUID) -> WorkflowDefinition | None:
        wf = self.workflows.get(workflow_id)
        if wf is None:
            return None
        if wf.shop_id is not None and wf.shop_id != shop_id:
            return None
        return wf

    async def list_workflows(
        self, shop_id: UUID, *, status: WorkflowStatus | None = None
    ) -> list[WorkflowDefinition]:
        items = [w for w in self.workflows.values() if w.shop_id is None or w.shop_id == shop_id]
        if status:
            items = [w for w in items if w.status == status]
        items.sort(key=lambda w: w.name)
        return items

    async def delete_workflow(self, shop_id: UUID, workflow_id: UUID) -> bool:
        wf = await self.get_workflow(shop_id, workflow_id)
        if wf is None or wf.shop_id is None:
            return False
        del self.workflows[workflow_id]
        return True

    async def find_by_trigger(
        self, shop_id: UUID, event_type: DomainEventType
    ) -> list[WorkflowDefinition]:
        return [
            w
            for w in await self.list_workflows(shop_id, status=WorkflowStatus.ACTIVE)
            if w.trigger == event_type
        ]

    async def save_run(self, run: WorkflowRun) -> WorkflowRun:
        self.runs[run.id] = run
        return run

    async def get_run(self, shop_id: UUID, run_id: UUID) -> WorkflowRun | None:
        run = self.runs.get(run_id)
        if run is None or run.shop_id != shop_id:
            return None
        return run

    async def list_runs(
        self, shop_id: UUID, *, workflow_id: UUID | None = None, limit: int = 50
    ) -> list[WorkflowRun]:
        items = [r for r in self.runs.values() if r.shop_id == shop_id]
        if workflow_id:
            items = [r for r in items if r.workflow_id == workflow_id]
        items.sort(key=lambda r: r.started_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[:limit]

    async def append_event(self, event: DomainEvent) -> DomainEvent:
        if event.occurred_at is None:
            event.occurred_at = datetime.now(timezone.utc)
        self.events.append(event)
        return event

    async def list_events(
        self, shop_id: UUID, *, limit: int = 100, event_type: str | None = None
    ) -> list[DomainEvent]:
        items = [e for e in self.events if e.shop_id == shop_id]
        if event_type:
            items = [e for e in items if e.event_type.value == event_type]
        items.sort(key=lambda e: e.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[:limit]

    async def enqueue_retry(self, item: RetryItem) -> RetryItem:
        if item.created_at is None:
            item.created_at = datetime.now(timezone.utc)
        self.retries[item.id] = item
        return item

    async def list_due_retries(self, *, now: datetime, limit: int = 50) -> list[RetryItem]:
        items = [
            r
            for r in self.retries.values()
            if r.state == RetryState.PENDING and r.next_attempt_at <= now
        ]
        items.sort(key=lambda r: r.next_attempt_at)
        return items[:limit]

    async def save_retry(self, item: RetryItem) -> RetryItem:
        self.retries[item.id] = item
        return item

    async def get_retry(self, retry_id: UUID) -> RetryItem | None:
        return self.retries.get(retry_id)


def new_workflow(
    *,
    shop_id: UUID | None,
    name: str,
    trigger: DomainEventType,
    **kwargs,
) -> WorkflowDefinition:
    return WorkflowDefinition(
        id=uuid4(),
        shop_id=shop_id,
        name=name,
        trigger=trigger,
        **kwargs,
    )
