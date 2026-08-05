"""Phase 10 Workflow Engine tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.workflows.enums import (
    ActionType,
    DomainEventType,
    RunStatus,
    StepStatus,
)
from app.workflows.factory import (
    build_workflow_runtime,
    ensure_seeded,
    reset_workflow_runtime,
)
from app.workflows.store import InMemoryWorkflowStore


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    yield
    reset_workflow_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
async def runtime():
    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    await ensure_seeded(rt)
    return rt


@pytest.mark.asyncio
async def test_appointment_booked_cascade(runtime, shop_id):
    event, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.APPOINTMENT_BOOKED,
        payload={
            "appointment_id": str(uuid4()),
            "customer_id": str(uuid4()),
            "estimated_revenue": "220.00",
        },
        source="test",
    )
    assert event.event_type == DomainEventType.APPOINTMENT_BOOKED
    assert len(runs) >= 1
    run = next(r for r in runs if "booked cascade" in r.workflow_name.lower())
    assert run.status == RunStatus.COMPLETED
    assert len(run.steps) == 4
    assert all(s.status == StepStatus.SUCCEEDED for s in run.steps)
    assert [s.action_type for s in run.steps] == [
        ActionType.SCHEDULE_REMINDER.value,
        ActionType.UPDATE_CRM.value,
        ActionType.UPDATE_REVENUE.value,
        ActionType.UPDATE_DASHBOARD.value,
    ]
    # Cascade events recorded
    types = {e.event_type for e in await runtime.store.list_events(shop_id, limit=50)}
    assert DomainEventType.REMINDER_SCHEDULED in types
    assert DomainEventType.CRM_UPDATED in types
    assert DomainEventType.REVENUE_UPDATED in types
    assert DomainEventType.DASHBOARD_UPDATED in types


@pytest.mark.asyncio
async def test_retry_and_recover(runtime, shop_id):
    attempts = {"n": 0}
    orig = runtime.executor.execute

    async def wrapped(action, **kwargs):
        if action.type == ActionType.NOTIFY:
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise RuntimeError("transient")
        return await orig(action, **kwargs)

    runtime.executor.execute = wrapped  # type: ignore[method-assign]

    await runtime.service.create_workflow(
        shop_id=shop_id,
        name="Flaky notify",
        trigger=DomainEventType.REVIEW_SUBMITTED,
        actions=[{"type": "notify", "name": "ping", "order": 1, "config": {"message": "hi"}}],
        retry={"max_attempts": 3, "backoff_ms": 1, "backoff_multiplier": 1.0},
    )

    _, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.REVIEW_SUBMITTED,
        payload={"review_id": str(uuid4())},
    )
    run = next(r for r in runs if r.workflow_name == "Flaky notify")
    assert run.status == RunStatus.WAITING_RETRY

    for item in runtime.store.retries.values():
        item.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    recovered = await runtime.service.process_retries()
    assert any(r.id == run.id and r.status == RunStatus.COMPLETED for r in recovered)


@pytest.mark.asyncio
async def test_condition_filters_workflow(runtime, shop_id):
    created = await runtime.service.create_workflow(
        shop_id=shop_id,
        name="High priority only",
        trigger=DomainEventType.APPOINTMENT_BOOKED,
        conditions=[{"field": "priority", "operator": "eq", "value": "emergency"}],
        actions=[{"type": "log", "name": "log", "order": 1, "config": {"message": "hi"}}],
    )
    assert created.id

    _, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.APPOINTMENT_BOOKED,
        payload={"priority": "normal"},
    )
    assert all(r.workflow_id != created.id for r in runs)

    _, runs2 = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.APPOINTMENT_BOOKED,
        payload={"priority": "emergency"},
    )
    assert any(r.workflow_id == created.id and r.status == RunStatus.COMPLETED for r in runs2)


@pytest.mark.asyncio
async def test_rollback_compensates_steps(runtime, shop_id):
    _, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.APPOINTMENT_BOOKED,
        payload={"appointment_id": str(uuid4()), "estimated_revenue": "100"},
    )
    run = next(r for r in runs if "booked cascade" in r.workflow_name.lower())
    assert run.status == RunStatus.COMPLETED
    assert runtime.executor.side_effects["reminders"]
    assert runtime.executor.side_effects["crm"]

    rolled = await runtime.service.rollback(shop_id, run.id)
    assert rolled.status == RunStatus.ROLLED_BACK
    assert all(
        s.status in (StepStatus.ROLLED_BACK, StepStatus.PENDING) for s in rolled.steps if s.status != StepStatus.PENDING
    )
    assert runtime.executor.side_effects["reminders"] == []
    assert runtime.executor.side_effects["crm"] == []


@pytest.mark.asyncio
async def test_debugger_frame(runtime, shop_id):
    _, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.INVOICE_PAID,
        payload={"invoice_id": str(uuid4()), "amount": "500"},
    )
    run = runs[0]
    frame = await runtime.service.debug_run(shop_id, run.id, step_index=0)
    assert frame.run_id == run.id
    assert frame.current_step is not None
    assert frame.logs


@pytest.mark.asyncio
async def test_scheduling_book_emits_workflow(shop_id):
    from app.scheduling.factory import build_scheduling_runtime, reset_scheduling_runtime
    from app.scheduling.models import BookingRequest
    from app.scheduling.store import InMemoryShopResourceStore

    reset_scheduling_runtime()
    reset_workflow_runtime()
    store = InMemoryShopResourceStore()
    store.ensure_shop(shop_id)
    sched = build_scheduling_runtime(store=store)
    wf = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    await ensure_seeded(wf)
    # Point global runtime to our wf store so emitter hits it
    import app.workflows.factory as wf_factory

    wf_factory._runtime = wf

    result = await sched.service.book(
        BookingRequest(shop_id=shop_id, repair_type="brakes", priority="normal")
    )
    assert result.success
    runs = await wf.service.list_runs(shop_id)
    assert any(r.trigger_event_type == DomainEventType.APPOINTMENT_BOOKED for r in runs)
    reset_scheduling_runtime()


@pytest.mark.asyncio
async def test_coordinator_publish_and_pause_resume(runtime, shop_id):
    assert runtime.coordinator is not None
    event, runs = await runtime.coordinator.publish(
        shop_id=shop_id,
        event_type=DomainEventType.MAINTENANCE_REMINDER_REQUESTED,
        payload={"service": "oil_change"},
        source="test",
    )
    assert event.event_type == DomainEventType.MAINTENANCE_REMINDER_REQUESTED
    assert len(runs) >= 1
    completed = next(r for r in runs if r.status == RunStatus.COMPLETED)

    # Create a multi-step run and pause it mid-flight via store status
    event2, runs2 = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.APPOINTMENT_BOOKED,
        payload={"appointment_id": str(uuid4())},
        source="test",
    )
    run = runs2[0]
    # After completion, pause should reject; mark as running then pause
    run.status = RunStatus.RUNNING
    await runtime.store.save_run(run)
    paused = await runtime.coordinator.pause_run(shop_id, run.id)
    assert paused.status == RunStatus.PAUSED
    resumed = await runtime.coordinator.resume_run(shop_id, run.id)
    assert resumed.status in {RunStatus.COMPLETED, RunStatus.RUNNING, RunStatus.FAILED}
    snap = runtime.monitor.snapshot()
    assert snap["orchestrations"] >= 1
    assert completed.id  # history path exercised
    history = await runtime.coordinator.workflow_history(shop_id, limit=10)
    assert len(history) >= 1


@pytest.mark.asyncio
async def test_coordinator_publish_and_invoke(runtime, shop_id):
    called = {"ok": False}

    async def _invoke():
        called["ok"] = True
        return "done"

    result = await runtime.coordinator.publish_and_invoke(
        shop_id=shop_id,
        event_type=DomainEventType.MARKETING_ACTION_REQUESTED,
        payload={"action": "test"},
        source="test",
        invoke=_invoke,
    )
    assert result == "done"
    assert called["ok"] is True
    esc = runtime.coordinator.escalate_human(
        shop_id=shop_id, reason="manual review", details={"case": "1"}
    )
    assert esc["reason"] == "manual review"
    assert len(runtime.coordinator.escalations) == 1
