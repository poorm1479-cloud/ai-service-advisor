"""Vehicle agent tests — AI decides; Workflow executes."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentResult
from app.agents.decisions.bridge import apply_decisions, collect_decision, ports_from_agents
from app.agents.vehicle.models import RepairRecord, VehicleRecord, VehicleResolveRequest
from app.agents.vehicle.service import InMemoryVehicleDirectory, VehicleAgent


async def _resolve_applied(agent, request, context):
    result = await agent.resolve(request, context)
    decision = collect_decision(result)
    if decision is None:
        return result
    applied = await apply_decisions(
        shop_id=context.shop_id,
        decisions=[decision],
        ports=ports_from_agents(vehicle=agent),
        context=context,
    )
    if applied and applied.vehicle_result:
        return AgentResult.ok(applied.vehicle_result)
    return result


@pytest.mark.asyncio
async def test_create_find_and_mileage(context, shop_id):
    agent = VehicleAgent()
    created = await _resolve_applied(
        agent,
        VehicleResolveRequest(
            vin="1HGCM82633A004352",
            year=2018,
            make="Honda",
            model="Civic",
            mileage=40000,
            create_if_missing=True,
        ),
        context,
    )
    assert created.success
    assert created.data.action == "created"
    assert created.data.vehicle.mileage == 40000
    assert len(created.data.maintenance_timeline) > 0

    found = await _resolve_applied(
        agent,
        VehicleResolveRequest(vin="1HGCM82633A004352", mileage=42000),
        context,
    )
    assert "mileage" in found.data.action
    assert found.data.vehicle.mileage == 42000


@pytest.mark.asyncio
async def test_find_by_customer_and_history(context, shop_id):
    directory = InMemoryVehicleDirectory()
    agent = VehicleAgent(directory)
    customer_id = uuid4()
    vehicle = await directory.create(
        VehicleRecord(
            id=uuid4(),
            shop_id=shop_id,
            vin="1FTFW1ET5DFC10312",
            year=2013,
            make="Ford",
            model="F-150",
            mileage=90000,
            customer_id=customer_id,
        )
    )
    await directory.add_repair(
        shop_id,
        RepairRecord(
            id=uuid4(),
            vehicle_id=vehicle.id,
            service_type="oil_change",
            description="Synthetic oil",
            cost=79.99,
        ),
    )
    context.customer_id = customer_id
    result = await agent.resolve(VehicleResolveRequest(customer_id=customer_id), context)
    assert result.data.action == "found_by_customer"
    history = await agent.read_repair_history(vehicle.id, context)
    assert history.success
    assert len(history.data) == 1
