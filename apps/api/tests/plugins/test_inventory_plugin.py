"""Phase 14 — Parts & Inventory Intelligence plugin tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.decisions.types import (
    InventoryRiskDecision,
    PartCostDecision,
    PartsAvailabilityDecision,
    PurchaseRecommendationDecision,
    RepairReadinessDecision,
)
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.plugins.framework.plugin import IPlugin
from app.plugins.inventory.factory import reset_inventory_plugin
from app.workflows.decision_executor import DecisionExecutor, DecisionPorts
from app.workflows.factory import build_workflow_runtime, reset_workflow_runtime
from app.workflows.store import InMemoryWorkflowStore


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    reset_inventory_plugin()
    reset_plugin_runtime()
    yield
    reset_workflow_runtime()
    reset_inventory_plugin()
    reset_plugin_runtime()


@pytest.mark.asyncio
async def test_inventory_registers_capabilities():
    runtime = ensure_default_plugins()
    plugin = runtime.plugins.lookup("inventory")
    assert isinstance(plugin, IPlugin)
    caps = set(plugin.supported_capabilities())
    for name in (
        Capability.FIND_PART.value,
        Capability.CHECK_INVENTORY.value,
        Capability.PREDICT_REQUIRED_PARTS.value,
        Capability.RESERVE_PART.value,
        Capability.RELEASE_PART.value,
        Capability.FIND_SUPPLIER.value,
        Capability.CREATE_PURCHASE_RECOMMENDATION.value,
        Capability.ESTIMATE_PART_COST.value,
        Capability.CHECK_REPAIR_READINESS.value,
    ):
        assert name in caps


@pytest.mark.asyncio
async def test_find_part_and_check_inventory():
    ensure_default_plugins()
    shop_id = uuid4()
    found = await invoke_capability(
        Capability.FIND_PART.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        query="brake",
    )
    assert found["count"] >= 1
    sku = found["parts"][0]["sku"]

    check = await invoke_capability(
        Capability.CHECK_INVENTORY.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        sku=sku,
        quantity=1,
    )
    assert check["found"] is True
    assert "available" in check


@pytest.mark.asyncio
async def test_predict_and_readiness_decisions_only():
    ensure_default_plugins()
    shop_id = uuid4()
    predicted = await invoke_capability(
        Capability.PREDICT_REQUIRED_PARTS.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        service_type="brake_inspection",
    )
    assert predicted["count"] >= 1

    out = await invoke_capability(
        Capability.CHECK_REPAIR_READINESS.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        customer_id=uuid4(),
        service_type="brake_inspection",
        repair_recommendations=[{"service_type": "brake_inspection", "title": "Brakes"}],
    )
    assert "decisions" in out
    decisions = out["decisions"]
    assert any(isinstance(d, PartsAvailabilityDecision) for d in decisions)
    assert any(isinstance(d, PartCostDecision) for d in decisions)
    assert any(isinstance(d, RepairReadinessDecision) for d in decisions)
    assert "ordered" not in out
    assert "purchase_order" not in out


@pytest.mark.asyncio
async def test_out_of_stock_triggers_purchase_and_risk():
    ensure_default_plugins()
    shop_id = uuid4()
    # AC compressor is seeded at qty 0
    out = await invoke_capability(
        Capability.CHECK_REPAIR_READINESS.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        service_type="ac_service",
    )
    decisions = out["decisions"]
    assert any(isinstance(d, PurchaseRecommendationDecision) for d in decisions)
    assert any(isinstance(d, InventoryRiskDecision) for d in decisions)
    readiness = next(d for d in decisions if isinstance(d, RepairReadinessDecision))
    assert readiness.ready is False
    assert readiness.delay_days >= 1


@pytest.mark.asyncio
async def test_reserve_and_release_are_workflow_mutations():
    ensure_default_plugins()
    shop_id = uuid4()
    reserved = await invoke_capability(
        Capability.RESERVE_PART.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        sku="OIL-5W30",
        quantity=1,
    )
    assert reserved["ok"] is True
    released = await invoke_capability(
        Capability.RELEASE_PART.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        reservation_id=reserved["reservation_id"],
    )
    assert released["ok"] is True


@pytest.mark.asyncio
async def test_find_supplier_and_purchase_recommendation():
    ensure_default_plugins()
    shop_id = uuid4()
    suppliers = await invoke_capability(
        Capability.FIND_SUPPLIER.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        sku="BRK-PAD-F",
    )
    assert suppliers["count"] >= 1

    purchases = await invoke_capability(
        Capability.CREATE_PURCHASE_RECOMMENDATION.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        service_type="ac_service",
    )
    assert purchases["count"] >= 1
    assert all(isinstance(d, PurchaseRecommendationDecision) for d in purchases["decisions"])


@pytest.mark.asyncio
async def test_decision_executor_applies_inventory_decisions():
    ensure_default_plugins()
    shop_id = uuid4()
    customer_id = uuid4()
    out = await invoke_capability(
        Capability.CHECK_REPAIR_READINESS.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        customer_id=customer_id,
        service_type="oil_change",
    )
    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    executor = DecisionExecutor(
        monitor=rt.monitor,
        emit_fn=rt.coordinator._emit_for_executor,
    )
    result = await executor.apply(
        shop_id=shop_id,
        decisions=out["decisions"],
        ports=DecisionPorts(),
        context=AgentContext(shop_id=shop_id, customer_id=customer_id, correlation_id=str(uuid4())),
    )
    kinds = {a["kind"] for a in result.applied}
    assert "parts_availability" in kinds
    assert "part_cost" in kinds
    assert "repair_readiness" in kinds


@pytest.mark.asyncio
async def test_existing_plugins_still_registered():
    runtime = ensure_default_plugins()
    for pid in ("crm", "scheduling", "conversation", "revenue", "advisor", "inspection", "inventory"):
        assert runtime.plugins.lookup(pid)
