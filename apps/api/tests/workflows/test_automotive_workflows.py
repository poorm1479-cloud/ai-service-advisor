"""Phase 11 — Automotive business workflow tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.workflows.automotive import AUTOMOTIVE_SPECS, automotive_workflows
from app.workflows.enums import DomainEventType, RunStatus, StepStatus
from app.workflows.factory import build_workflow_runtime, ensure_seeded, reset_workflow_runtime
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


def test_automotive_catalog_complete():
    wfs = automotive_workflows()
    assert len(wfs) == 6
    assert len(AUTOMOTIVE_SPECS) == 6
    names = {w.name for w in wfs}
    assert any("phone repair" in n.lower() for n in names)
    assert any("maintenance reminder" in n.lower() for n in names)
    assert any("inspection completed" in n.lower() for n in names)
    assert any("declined estimate" in n.lower() for n in names)
    assert any("walk-in customer" in n.lower() for n in names)
    assert any("repair completed" in n.lower() for n in names)
    for spec in AUTOMOTIVE_SPECS:
        assert spec["workflow_id"]
        assert spec["purpose"]
        assert spec["trigger_event"]
        assert spec["required_capabilities"]
        assert spec["ai_decisions"]
        assert spec["events_published"]
        assert spec["failure_handling"]
        assert spec["human_escalation"]


@pytest.mark.asyncio
async def test_scenario_1_new_customer_phone(runtime, shop_id):
    _, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.INBOUND_MESSAGE_RECEIVED,
        payload={
            "channel": "phone",
            "customer_id": str(uuid4()),
            "body": "My brakes are making noise",
        },
        source="test.automotive",
    )
    run = next(r for r in runs if "phone repair" in r.workflow_name.lower())
    assert run.status == RunStatus.COMPLETED
    assert all(s.status == StepStatus.SUCCEEDED for s in run.steps)
    types = {e.event_type for e in await runtime.store.list_events(shop_id, limit=80)}
    assert DomainEventType.CRM_UPDATED in types
    assert DomainEventType.REMINDER_SCHEDULED in types


@pytest.mark.asyncio
async def test_scenario_2_maintenance_reminder(runtime, shop_id):
    _, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.MAINTENANCE_REMINDER_REQUESTED,
        payload={"customer_id": str(uuid4()), "vehicle_id": str(uuid4())},
        source="test.automotive",
    )
    run = next(r for r in runs if r.workflow_name.startswith("Automotive: Maintenance"))
    assert run.status == RunStatus.COMPLETED
    types = {e.event_type for e in await runtime.store.list_events(shop_id, limit=80)}
    assert DomainEventType.REVENUE_OPPORTUNITY_DETECTED in types
    assert DomainEventType.MARKETING_ACTION_REQUESTED in types


@pytest.mark.asyncio
async def test_scenario_3_inspection_completed(runtime, shop_id):
    _, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.REPAIR_FINISHED,
        payload={
            "phase": "inspection",
            "customer_id": str(uuid4()),
            "vehicle_id": str(uuid4()),
        },
        source="test.automotive",
    )
    names = [r.workflow_name for r in runs]
    assert any("Inspection completed" in n for n in names)
    assert not any(n.startswith("Automotive: Repair completed") for n in names)
    run = next(r for r in runs if "Inspection completed" in r.workflow_name)
    assert run.status == RunStatus.COMPLETED
    types = {e.event_type for e in await runtime.store.list_events(shop_id, limit=80)}
    assert DomainEventType.ESTIMATE_SENT in types


@pytest.mark.asyncio
async def test_scenario_4_declined_estimate(runtime, shop_id):
    _, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.ESTIMATE_DECLINED,
        payload={
            "customer_id": str(uuid4()),
            "estimated_revenue": "420.00",
        },
        source="test.automotive",
    )
    run = next(r for r in runs if "Declined estimate" in r.workflow_name)
    assert run.status == RunStatus.COMPLETED
    types = {e.event_type for e in await runtime.store.list_events(shop_id, limit=80)}
    assert DomainEventType.REVENUE_OPPORTUNITY_DETECTED in types
    assert DomainEventType.CUSTOMER_RETURNED in types


@pytest.mark.asyncio
async def test_scenario_5_walk_in_customer(runtime, shop_id):
    _, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.WALK_IN_CREATED,
        payload={
            "visit_id": str(uuid4()),
            "vehicle_id": str(uuid4()),
            "complaint": "Brake noise",
        },
        source="test.automotive",
    )
    run = next(r for r in runs if "Walk-in customer" in r.workflow_name)
    assert run.status == RunStatus.COMPLETED
    types = {e.event_type for e in await runtime.store.list_events(shop_id, limit=80)}
    assert DomainEventType.REPAIR_STARTED in types
    assert DomainEventType.VEHICLE_CREATED in types


@pytest.mark.asyncio
async def test_scenario_6_repair_completed(runtime, shop_id):
    _, runs = await runtime.service.emit_and_run(
        shop_id=shop_id,
        event_type=DomainEventType.REPAIR_FINISHED,
        payload={
            "phase": "repair",
            "customer_id": str(uuid4()),
            "estimated_revenue": "680.00",
        },
        source="test.automotive",
    )
    names = [r.workflow_name for r in runs]
    assert any("Repair completed" in n for n in names)
    assert not any("Inspection completed" in n for n in names)
    run = next(r for r in runs if "Repair completed" in r.workflow_name)
    assert run.status == RunStatus.COMPLETED
    types = {e.event_type for e in await runtime.store.list_events(shop_id, limit=80)}
    assert DomainEventType.MAINTENANCE_REMINDER_REQUESTED in types
    assert DomainEventType.REVENUE_UPDATED in types
