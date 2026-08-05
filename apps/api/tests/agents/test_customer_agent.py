"""Customer agent tests — AI decides; Workflow executes."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentResult
from app.agents.customer.models import CustomerProfile, CustomerResolveRequest
from app.agents.customer.service import CustomerAgent, InMemoryCustomerDirectory
from app.agents.decisions.bridge import apply_decisions, collect_decision, ports_from_agents
from app.agents.decisions.types import CustomerDecision


async def _resolve_applied(agent, request, context):
    result = await agent.resolve(request, context)
    decision = collect_decision(result)
    if decision is None:
        return result
    applied = await apply_decisions(
        shop_id=context.shop_id,
        decisions=[decision],
        ports=ports_from_agents(customer=agent),
        context=context,
    )
    if applied and applied.customer_result:
        return AgentResult.ok(applied.customer_result)
    return result


@pytest.mark.asyncio
async def test_create_and_find_customer(context, shop_id):
    agent = CustomerAgent()
    created = await _resolve_applied(
        agent,
        CustomerResolveRequest(name="Ada Lovelace", phone="555-111-2222", email="ada@example.com"),
        context,
    )
    assert created.success
    assert created.data is not None
    assert created.data.is_new
    assert created.data.action == "created"
    assert context.customer_id == created.data.customer.id

    found = await agent.resolve(
        CustomerResolveRequest(phone="5551112222", create_if_missing=False),
        context,
    )
    assert found.data is not None
    assert found.data.action == "found"
    assert found.data.customer.id == created.data.customer.id


@pytest.mark.asyncio
async def test_merge_duplicates(context, shop_id):
    directory = InMemoryCustomerDirectory()
    agent = CustomerAgent(directory)
    a = await directory.create(
        CustomerProfile(id=uuid4(), shop_id=shop_id, name="A", phone="5559990000")
    )
    b = await directory.create(
        CustomerProfile(
            id=uuid4(),
            shop_id=shop_id,
            name="A Duplicate",
            phone="555-999-0000",
            email="a@example.com",
        )
    )
    result = await _resolve_applied(agent, CustomerResolveRequest(phone="5559990000"), context)
    assert result.success
    assert result.data is not None
    assert result.data.action == "merged"
    assert a.id in result.data.merged_from or b.id in result.data.merged_from
    assert result.data.customer.email == "a@example.com"


@pytest.mark.asyncio
async def test_read_and_update_profile(context, shop_id):
    agent = CustomerAgent()
    created = await _resolve_applied(
        agent,
        CustomerResolveRequest(name="Grace Hopper", phone="5553334444"),
        context,
    )
    profile = created.data.customer
    profile.address = "1 Navy Way"
    updated = await agent.update_profile(profile, context)
    assert updated.success
    decision = updated.metadata.get("decision")
    assert isinstance(decision, CustomerDecision)
    applied = await apply_decisions(
        shop_id=context.shop_id,
        decisions=[decision],
        ports=ports_from_agents(customer=agent),
        context=context,
    )
    assert applied.customer_result is not None
    assert applied.customer_result.customer.address == "1 Navy Way"

    read = await agent.read_profile(profile.id, context)
    assert read.success
    assert read.data.name == "Grace Hopper"


@pytest.mark.asyncio
async def test_fills_placeholder_name_before_booking(context, shop_id):
    directory = InMemoryCustomerDirectory()
    agent = CustomerAgent(directory)
    await directory.create(
        CustomerProfile(
            id=uuid4(),
            shop_id=shop_id,
            name="Unknown Customer",
            phone="5557778888",
        )
    )
    result = await _resolve_applied(
        agent,
        CustomerResolveRequest(name="Alex Rivera", phone="5557778888"),
        context,
    )
    assert result.success
    assert result.data is not None
    assert result.data.action == "updated"
    assert result.data.customer.name == "Alex Rivera"
