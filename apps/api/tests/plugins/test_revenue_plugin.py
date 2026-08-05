"""Revenue Intelligence Plugin tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.decisions.bridge import ports_from_agents
from app.agents.decisions.types import RevenueDecision
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.plugins.framework.plugin import IPlugin
from app.plugins.revenue.factory import reset_revenue_plugin
from app.revenue_intel.factory import reset_revenue_intel_runtime
from app.workflows.factory import build_workflow_runtime, reset_workflow_runtime
from app.workflows.store import InMemoryWorkflowStore


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    reset_revenue_plugin()
    reset_revenue_intel_runtime()
    reset_plugin_runtime()
    yield
    reset_workflow_runtime()
    reset_revenue_plugin()
    reset_revenue_intel_runtime()
    reset_plugin_runtime()


@pytest.mark.asyncio
async def test_revenue_plugin_registers_capabilities():
    runtime = ensure_default_plugins()
    plugin = runtime.plugins.lookup("revenue")
    assert isinstance(plugin, IPlugin)
    caps = {c["capability"] for c in runtime.capabilities.list_capabilities()}
    assert Capability.DETECT_REVENUE_OPPORTUNITY.value in caps
    assert Capability.CALCULATE_CUSTOMER_LIFETIME_VALUE.value in caps
    assert Capability.OPTIMIZE_TECHNICIAN_UTILIZATION.value in plugin.supported_capabilities()


@pytest.mark.asyncio
async def test_detect_and_dashboard_capabilities():
    ensure_default_plugins()
    shop_id = uuid4()
    detected = await invoke_capability(
        Capability.DETECT_REVENUE_OPPORTUNITY.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        run_analysis=True,
        emit_workflow_events=False,
    )
    assert detected["count"] >= 0
    assert "workflow_events" in detected

    maintenance = await invoke_capability(
        Capability.PREDICT_MAINTENANCE.value,
        shop_id=shop_id,
    )
    assert isinstance(maintenance, list)

    declined = await invoke_capability(
        Capability.FIND_DECLINED_ESTIMATES.value,
        shop_id=shop_id,
    )
    assert isinstance(declined, list)

    upsells = await invoke_capability(
        Capability.GENERATE_UPSELL_RECOMMENDATIONS.value,
        shop_id=shop_id,
    )
    assert isinstance(upsells, list)

    capacity = await invoke_capability(
        Capability.PREDICT_SHOP_CAPACITY.value,
        shop_id=shop_id,
    )
    assert "monthly_expected_revenue" in capacity

    util = await invoke_capability(
        Capability.OPTIMIZE_TECHNICIAN_UTILIZATION.value,
        shop_id=shop_id,
    )
    assert "recommendations" in util


@pytest.mark.asyncio
async def test_customer_health_and_clv():
    ensure_default_plugins()
    shop_id = uuid4()
    await invoke_capability(
        Capability.DETECT_REVENUE_OPPORTUNITY.value,
        shop_id=shop_id,
        run_analysis=True,
    )
    health = await invoke_capability(
        Capability.CALCULATE_CUSTOMER_HEALTH.value,
        shop_id=shop_id,
    )
    assert isinstance(health, list)
    if health:
        clv = await invoke_capability(
            Capability.CALCULATE_CUSTOMER_LIFETIME_VALUE.value,
            shop_id=shop_id,
            customer_id=health[0].entity_id,
        )
        assert clv["found"] is True
        assert "lifetime_value" in clv


@pytest.mark.asyncio
async def test_workflow_applies_revenue_decision_via_plugin():
    ensure_default_plugins()
    shop_id = uuid4()
    # Seed opportunities first
    await invoke_capability(
        Capability.DETECT_REVENUE_OPPORTUNITY.value,
        shop_id=shop_id,
        run_analysis=True,
        emit_workflow_events=False,
    )
    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    import app.workflows.factory as wf_factory

    wf_factory._runtime = rt
    ctx = AgentContext(shop_id=shop_id)
    applied = await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=[
            RevenueDecision(
                predicted_revenue=__import__("decimal").Decimal("250.00"),
                lost_customer_risk=0.4,
                notes=["plugin test"],
            )
        ],
        ports=ports_from_agents(),
        context=ctx,
    )
    assert any(a.get("kind") == "revenue" for a in applied.applied)
    assert applied.revenue_result is not None
