"""CRM Plugin + Capability Registry tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.customer.models import CustomerProfile
from app.agents.customer.service import CustomerAgent
from app.agents.decisions.bridge import ports_from_agents
from app.agents.decisions.types import CrmUpdateDecision, CustomerDecision
from app.plugins.crm.factory import reset_crm_plugin
from app.plugins.framework.capability import Capability
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.plugins.framework.context import PluginContext
from app.workflows.factory import build_workflow_runtime, reset_workflow_runtime
from app.workflows.store import InMemoryWorkflowStore


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    reset_crm_plugin()
    reset_plugin_runtime()
    yield
    reset_workflow_runtime()
    reset_crm_plugin()
    reset_plugin_runtime()


@pytest.mark.asyncio
async def test_crm_plugin_registers_capabilities():
    runtime = ensure_default_plugins()
    plugin = runtime.plugins.lookup("crm")
    caps = {c["capability"] for c in runtime.capabilities.list_capabilities()}
    assert Capability.FIND_CUSTOMER.value in caps
    assert Capability.CREATE_CUSTOMER.value in caps
    assert Capability.CUSTOMER_TIMELINE.value in caps
    assert Capability.REPAIR_HISTORY.value in caps
    assert plugin.plugin_id() == "crm"
    assert Capability.CREATE_CUSTOMER.value in plugin.supported_capabilities()


@pytest.mark.asyncio
async def test_capability_registry_resolves_crm_plugin():
    ensure_default_plugins()
    shop_id = uuid4()
    runtime = ensure_default_plugins()
    binding = runtime.capabilities.resolve(Capability.CREATE_CUSTOMER)
    assert binding.plugin_id == "crm"

    created = await invoke_capability(
        Capability.CREATE_CUSTOMER.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        profile=CustomerProfile(
            id=uuid4(), shop_id=shop_id, name="Plugin Customer", phone="5551112222"
        ),
    )
    assert created.name == "Plugin Customer"

    found = await invoke_capability(
        Capability.FIND_CUSTOMER.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        customer_id=created.id,
    )
    assert found is not None
    assert found.id == created.id

    summary = await invoke_capability(
        Capability.CUSTOMER_SUMMARY.value,
        context=PluginContext.for_shop(shop_id, customer_id=created.id),
        shop_id=shop_id,
        customer_id=created.id,
    )
    assert "Plugin Customer" in summary


@pytest.mark.asyncio
async def test_workflow_applies_customer_via_capability_registry():
    shop_id = uuid4()
    ctx = AgentContext(shop_id=shop_id)
    customer = CustomerAgent()
    ports = ports_from_agents(customer=customer)
    assert ports.crm_plugin is not None

    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    import app.workflows.factory as wf_factory

    wf_factory._runtime = rt

    applied = await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=[CustomerDecision(action="create", name="Via Plugin", phone="5559998888")],
        ports=ports,
        context=ctx,
    )
    assert applied.customer_result is not None
    assert applied.customer_result.action == "created"

    found = await invoke_capability(
        Capability.FIND_CUSTOMER.value,
        ports=ports,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        customer_id=applied.customer_result.customer.id,
    )
    assert found is not None

    await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=[
            CrmUpdateDecision(
                customer_id=found.id,
                channel="sms",
                message="hello",
                intent="book_appointment",
            )
        ],
        ports=ports,
        context=ctx,
    )
    timeline = await invoke_capability(
        Capability.CUSTOMER_TIMELINE.value,
        ports=ports,
        context=PluginContext.for_shop(shop_id, customer_id=found.id),
        shop_id=shop_id,
        customer_id=found.id,
    )
    assert len(timeline) >= 1


@pytest.mark.asyncio
async def test_coordinator_invoke_capability():
    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    shop_id = uuid4()
    created = await rt.coordinator.invoke_capability(
        Capability.CREATE_CUSTOMER.value,
        shop_id=shop_id,
        profile=CustomerProfile(id=uuid4(), shop_id=shop_id, name="Coord Cap"),
    )
    assert created.name == "Coord Cap"
