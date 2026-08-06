"""AI Decision Layer → Workflow DecisionExecutor tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.crm.service import CrmAgent
from app.agents.customer.service import CustomerAgent
from app.agents.decisions.bridge import ports_from_agents
from app.agents.decisions.types import (
    AppointmentDecision,
    CustomerDecision,
    MarketingDecision,
    RepairRecommendationDecision,
)
from app.agents.marketing.service import LoggingMarketingDispatcher, MarketingAgent
from app.agents.scheduling.service import SchedulingAgent
from app.agents.vehicle.models import VehicleRecord
from app.agents.vehicle.service import VehicleAgent
from app.workflows.factory import build_workflow_runtime, reset_workflow_runtime
from app.workflows.store import InMemoryWorkflowStore


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    yield
    reset_workflow_runtime()


@pytest.mark.asyncio
async def test_decision_executor_applies_customer_and_appointment():
    shop_id = uuid4()
    ctx = AgentContext(shop_id=shop_id)
    customer = CustomerAgent()
    scheduling = SchedulingAgent()
    ports = ports_from_agents(customer=customer, scheduling=scheduling)

    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    import app.workflows.factory as wf_factory

    wf_factory._runtime = rt

    slots = await scheduling.store.list_available_slots(shop_id, days_ahead=7)
    assert slots
    applied = await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=[
            CustomerDecision(action="create", name="Decision User", phone="5550001111"),
            AppointmentDecision(
                action="book",
                rationale="test book",
                preferred_start=slots[0].start,
                recommended_slot_start=slots[0].start,
                recommended_slot_end=slots[0].end,
            ),
        ],
        ports=ports,
        context=ctx,
    )
    assert applied.customer_result is not None
    assert applied.customer_result.action == "created"
    assert applied.scheduling_result is not None
    assert applied.scheduling_result.appointment is not None
    assert ctx.customer_id is not None


@pytest.mark.asyncio
async def test_marketing_decision_dispatched_only_by_workflow():
    shop_id = uuid4()
    ctx = AgentContext(shop_id=shop_id)
    dispatcher = LoggingMarketingDispatcher()
    marketing = MarketingAgent(dispatcher)
    ports = ports_from_agents(marketing=marketing)
    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    import app.workflows.factory as wf_factory

    wf_factory._runtime = rt

    assert len(dispatcher.sent) == 0
    await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=[
            MarketingDecision(
                action_type="thank_you",
                channel="sms",
                body="Thanks!",
                template="Thanks!",
            )
        ],
        ports=ports,
        context=ctx,
    )
    assert len(dispatcher.sent) == 1
    assert dispatcher.sent[0].dispatched


@pytest.mark.asyncio
async def test_repair_recommendation_does_not_create_repair_history():
    """Recommendations / bookings must not appear as completed repair history."""
    shop_id = uuid4()
    customer_id = uuid4()
    vehicle_id = uuid4()
    ctx = AgentContext(shop_id=shop_id, customer_id=customer_id, vehicle_id=vehicle_id)

    vehicle = VehicleAgent()
    await vehicle.directory.create(
        VehicleRecord(
            id=vehicle_id,
            shop_id=shop_id,
            vin="1HGBH41JXMN109186",
            year=2018,
            make="Honda",
            model="Civic",
            mileage=50000,
            customer_id=customer_id,
        )
    )
    crm = CrmAgent()
    ports = ports_from_agents(vehicle=vehicle, crm=crm)

    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    import app.workflows.factory as wf_factory

    wf_factory._runtime = rt

    applied = await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=[
            RepairRecommendationDecision(
                customer_id=customer_id,
                vehicle_id=vehicle_id,
                service_type="oil_change",
                title="Oil change",
                description="Recommended during booking",
                estimated_cost=Decimal("79.99"),
                plain_language="We recommend an oil change.",
            )
        ],
        ports=ports,
        context=ctx,
    )

    assert any(a.get("kind") == "repair_recommendation" for a in applied.applied)
    repairs = await vehicle.directory.list_repairs(shop_id, vehicle_id)
    assert repairs == []

    timeline = await crm.store.list_timeline(shop_id, customer_id)
    assert any(e.kind == "repair_recommendation" for e in timeline)
