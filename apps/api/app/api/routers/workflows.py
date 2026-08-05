"""Workflow Engine HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user, require_workflow_access
from app.workflows.enums import DomainEventType, WorkflowStatus
from app.workflows.factory import (
    WorkflowRuntime,
    ensure_seeded,
    get_workflow_runtime,
)

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])


def _runtime() -> WorkflowRuntime:
    return get_workflow_runtime()


class ConditionIn(BaseModel):
    field: str
    operator: str = "eq"
    value: Any = None


class ActionIn(BaseModel):
    id: UUID | None = None
    type: str
    name: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    order: int | None = None
    continue_on_error: bool = False
    compensate: dict[str, Any] = Field(default_factory=dict)


class RetryIn(BaseModel):
    max_attempts: int = 3
    backoff_ms: int = 1000
    backoff_multiplier: float = 2.0
    max_backoff_ms: int = 60_000


class WorkflowCreate(BaseModel):
    name: str
    trigger: str
    description: str = ""
    conditions: list[ConditionIn] = Field(default_factory=list)
    actions: list[ActionIn] = Field(default_factory=list)
    retry: RetryIn | None = None
    status: str = "active"
    tags: list[str] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger: str | None = None
    conditions: list[ConditionIn] | None = None
    actions: list[ActionIn] | None = None
    retry: RetryIn | None = None
    status: str | None = None
    tags: list[str] | None = None


class EmitRequest(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class StepOut(BaseModel):
    id: UUID
    action_id: UUID | None
    action_type: str
    action_name: str
    status: str
    attempt: int
    input: dict[str, Any]
    output: dict[str, Any]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    compensation: dict[str, Any] = Field(default_factory=dict)


class WorkflowOut(BaseModel):
    id: UUID
    shop_id: UUID | None
    name: str
    description: str
    trigger: str
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    retry: dict[str, Any]
    status: str
    version: int
    tags: list[str]
    is_template: bool
    created_at: datetime | None
    updated_at: datetime | None


class RunOut(BaseModel):
    id: UUID
    shop_id: UUID
    workflow_id: UUID
    workflow_name: str
    workflow_version: int
    trigger_event_id: UUID
    trigger_event_type: str
    correlation_id: str
    status: str
    context: dict[str, Any]
    steps: list[StepOut]
    logs: list[str]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    rolled_back_at: datetime | None


class EventOut(BaseModel):
    event_id: UUID
    event_type: str
    shop_id: UUID
    payload: dict[str, Any]
    correlation_id: str
    source: str
    occurred_at: datetime | None


class DebuggerOut(BaseModel):
    run_id: UUID
    step_index: int
    status: str
    context: dict[str, Any]
    current_step: StepOut | None
    logs: list[str]


def _wf_out(wf) -> WorkflowOut:
    return WorkflowOut(
        id=wf.id,
        shop_id=wf.shop_id,
        name=wf.name,
        description=wf.description,
        trigger=wf.trigger.value,
        conditions=[
            {"field": c.field, "operator": c.operator.value, "value": c.value}
            for c in wf.conditions
        ],
        actions=[
            {
                "id": str(a.id),
                "type": a.type.value,
                "name": a.name,
                "config": a.config,
                "order": a.order,
                "continue_on_error": a.continue_on_error,
                "compensate": a.compensate,
            }
            for a in sorted(wf.actions, key=lambda x: x.order)
        ],
        retry={
            "max_attempts": wf.retry.max_attempts,
            "backoff_ms": wf.retry.backoff_ms,
            "backoff_multiplier": wf.retry.backoff_multiplier,
            "max_backoff_ms": wf.retry.max_backoff_ms,
        },
        status=wf.status.value,
        version=wf.version,
        tags=wf.tags,
        is_template=wf.shop_id is None,
        created_at=wf.created_at,
        updated_at=wf.updated_at,
    )


def _step_out(s) -> StepOut:
    return StepOut(
        id=s.id,
        action_id=s.action_id,
        action_type=s.action_type,
        action_name=s.action_name,
        status=s.status.value,
        attempt=s.attempt,
        input=s.input,
        output=s.output,
        error=s.error,
        started_at=s.started_at,
        finished_at=s.finished_at,
        compensation=s.compensation,
    )


def _run_out(run) -> RunOut:
    return RunOut(
        id=run.id,
        shop_id=run.shop_id,
        workflow_id=run.workflow_id,
        workflow_name=run.workflow_name,
        workflow_version=run.workflow_version,
        trigger_event_id=run.trigger_event_id,
        trigger_event_type=run.trigger_event_type.value,
        correlation_id=run.correlation_id,
        status=run.status.value,
        context=run.context,
        steps=[_step_out(s) for s in run.steps],
        logs=run.logs,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        rolled_back_at=run.rolled_back_at,
    )


@router.get("/meta/events")
async def list_event_types(
    _: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> list[str]:
    await ensure_seeded(rt)
    return rt.service.list_event_types()


@router.get("/meta/actions")
async def list_action_types(
    _: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> list[str]:
    return rt.service.list_action_types()


@router.get("/metrics/summary")
async def metrics(
    _: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> dict[str, Any]:
    return rt.monitor.snapshot()


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(
    status_filter: str | None = Query(None, alias="status"),
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> list[WorkflowOut]:
    await ensure_seeded(rt)
    st = WorkflowStatus(status_filter) if status_filter else None
    return [_wf_out(w) for w in await rt.service.list_workflows(user.shop_id, status=st)]


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: WorkflowCreate,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> WorkflowOut:
    wf = await rt.service.create_workflow(
        shop_id=user.shop_id,
        name=body.name,
        trigger=body.trigger,
        description=body.description,
        conditions=[c.model_dump() for c in body.conditions],
        actions=[a.model_dump(mode="json") for a in body.actions],
        retry=body.retry.model_dump() if body.retry else None,
        status=WorkflowStatus(body.status),
        tags=body.tags,
    )
    return _wf_out(wf)


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    workflow_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> list[RunOut]:
    runs = await rt.service.list_runs(user.shop_id, workflow_id=workflow_id, limit=limit)
    return [_run_out(r) for r in runs]


@router.get("/events", response_model=list[EventOut])
async def list_events(
    limit: int = Query(100, ge=1, le=500),
    event_type: str | None = None,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> list[EventOut]:
    events = await rt.service.list_events(user.shop_id, limit=limit, event_type=event_type)
    return [
        EventOut(
            event_id=e.event_id,
            event_type=e.event_type.value,
            shop_id=e.shop_id,
            payload=e.payload,
            correlation_id=e.correlation_id,
            source=e.source,
            occurred_at=e.occurred_at,
        )
        for e in events
    ]


@router.post("/emit")
async def emit_event(
    body: EmitRequest,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> dict[str, Any]:
    await ensure_seeded(rt)
    try:
        DomainEventType(body.event_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown event type: {body.event_type}") from exc
    event, runs = await rt.service.emit_and_run(
        shop_id=user.shop_id,
        event_type=body.event_type,
        payload=body.payload,
        source="dashboard",
        correlation_id=body.correlation_id,
    )
    rt.monitor.record_event(body.event_type)
    for run in runs:
        rt.monitor.record_run_started()
        if run.status.value == "completed":
            rt.monitor.record_run_completed()
        elif run.status.value == "failed":
            rt.monitor.record_run_failed()
    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type.value,
        "runs": [_run_out(r) for r in runs],
    }


@router.post("/retries/process", response_model=list[RunOut])
async def process_retries(
    _: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> list[RunOut]:
    runs = await rt.service.process_retries()
    rt.monitor.record_retries(len(runs))
    return [_run_out(r) for r in runs]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: UUID,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> RunOut:
    try:
        return _run_out(await rt.service.get_run(user.shop_id, run_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/debug", response_model=DebuggerOut)
async def debug_run(
    run_id: UUID,
    step_index: int = Query(0, ge=0),
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> DebuggerOut:
    try:
        frame = await rt.service.debug_run(user.shop_id, run_id, step_index=step_index)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DebuggerOut(
        run_id=frame.run_id,
        step_index=frame.step_index,
        status=frame.status.value,
        context=frame.context,
        current_step=_step_out(frame.current_step) if frame.current_step else None,
        logs=frame.logs,
    )


@router.post("/runs/{run_id}/rollback", response_model=RunOut)
async def rollback_run(
    run_id: UUID,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> RunOut:
    try:
        run = await rt.service.rollback(user.shop_id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rt.monitor.record_rollback()
    return _run_out(run)


@router.post("/runs/{run_id}/pause", response_model=RunOut)
async def pause_run(
    run_id: UUID,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> RunOut:
    try:
        run = await rt.coordinator.pause_run(user.shop_id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rt.monitor.record_pause()
    return _run_out(run)


@router.post("/runs/{run_id}/resume", response_model=RunOut)
async def resume_run(
    run_id: UUID,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> RunOut:
    try:
        run = await rt.coordinator.resume_run(user.shop_id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rt.monitor.record_resume()
    return _run_out(run)


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: UUID,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> WorkflowOut:
    try:
        return _wf_out(await rt.service.get_workflow(user.shop_id, workflow_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(
    workflow_id: UUID,
    body: WorkflowUpdate,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> WorkflowOut:
    patch = body.model_dump(exclude_unset=True)
    try:
        return _wf_out(
            await rt.service.update_workflow(
                shop_id=user.shop_id, workflow_id=workflow_id, patch=patch
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/{workflow_id}/clone", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
async def clone_workflow(
    workflow_id: UUID,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> WorkflowOut:
    try:
        return _wf_out(await rt.service.clone_workflow(user.shop_id, workflow_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: UUID,
    user: CurrentUser = Depends(require_workflow_access()),
    rt: WorkflowRuntime = Depends(_runtime),
) -> None:
    try:
        await rt.service.delete_workflow(user.shop_id, workflow_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
