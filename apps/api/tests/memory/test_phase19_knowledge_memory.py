"""Phase 19 Knowledge Base & Shop Memory tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.decisions.types import (
    CustomerMemoryDecision,
    KnowledgeRetrievalDecision,
    ShopPreferenceDecision,
    VehicleMemoryDecision,
)
from app.memory.factory import build_memory_runtime, reset_memory_runtime
from app.plugins.framework.capability import Capability
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.plugins.framework.context import PluginContext
from app.workflows.decision_executor import DecisionExecutor, DecisionPorts


@pytest.fixture(autouse=True)
def _reset():
    reset_memory_runtime()
    reset_plugin_runtime()
    yield
    reset_memory_runtime()
    reset_plugin_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def runtime():
    return build_memory_runtime()


@pytest.mark.asyncio
async def test_memory_plugin_capabilities_registered():
    ensure_default_plugins()
    from app.plugins.framework.capability import get_capability_registry

    caps = {c["capability"] for c in get_capability_registry().list_capabilities()}
    for name in (
        "SaveMemory",
        "SearchMemory",
        "GetCustomerHistory",
        "GetVehicleHistory",
        "GetShopPreference",
        "RetrieveKnowledge",
        "UpdateCustomerProfile",
        "UpdateVehicleHealth",
    ):
        assert name in caps


@pytest.mark.asyncio
async def test_save_and_search_memory_via_plugin(shop_id):
    ensure_default_plugins()
    ctx = PluginContext.for_shop(shop_id)
    saved = await invoke_capability(
        Capability.SAVE_MEMORY.value,
        context=ctx,
        shop_id=shop_id,
        content="Customer prefers morning appointments",
        category="customer_preferences",
        memory_type="customer",
        source="workflow",
    )
    assert saved["content"]
    bundle = await invoke_capability(
        Capability.SEARCH_MEMORY.value,
        context=ctx,
        shop_id=shop_id,
        query="morning appointments",
    )
    assert bundle["hit_count"] >= 1


@pytest.mark.asyncio
async def test_shop_preference_and_knowledge(runtime, shop_id):
    mgr = runtime.manager
    await mgr.apply_shop_preference_decision(
        shop_id, preferences={"tone": "friendly"}, rationale="owner setting"
    )
    prefs = await mgr.get_shop_preference(shop_id)
    assert prefs["preferences"]["tone"] == "friendly"

    doc = await mgr.upsert_knowledge_document(
        shop_id,
        title="Brake pad SOP",
        content="Always inspect rotors when replacing pads.",
        tags=["brakes", "sop"],
    )
    docs = await mgr.retrieve_knowledge(shop_id, query="brake", limit=5)
    assert any(d.get("id") == str(doc.id) or "Brake" in str(d.get("title", "")) for d in docs)


@pytest.mark.asyncio
async def test_customer_and_vehicle_history(runtime, shop_id):
    customer_id = uuid4()
    vehicle_id = uuid4()
    await runtime.manager.update_customer_profile(
        shop_id, customer_id, {"preference": "text_only", "summary": "Prefers SMS"}
    )
    await runtime.manager.update_vehicle_health(
        shop_id, vehicle_id, {"status": "fair", "score": 62, "summary": "Brakes worn"}
    )
    ch = await runtime.manager.get_customer_history(shop_id, customer_id)
    vh = await runtime.manager.get_vehicle_history(shop_id, vehicle_id)
    assert ch and vh
    health = await runtime.manager.vehicle_health.get(shop_id, vehicle_id)
    assert health["status"] == "fair"


@pytest.mark.asyncio
async def test_decisions_applied_via_workflow_not_ai_direct(shop_id):
    ensure_default_plugins()
    runtime = build_memory_runtime()
    customer_id = uuid4()
    vehicle_id = uuid4()
    executor = DecisionExecutor()
    ports = DecisionPorts(memory_service=runtime.service)
    ctx = AgentContext(shop_id=shop_id, customer_id=customer_id, vehicle_id=vehicle_id)

    result = await executor.apply(
        shop_id=shop_id,
        decisions=[
            CustomerMemoryDecision(
                customer_id=customer_id,
                action="update_profile",
                content="Likes detailed estimates",
                patch={"preference": "detailed_estimates"},
                rationale="from conversation",
            ),
            VehicleMemoryDecision(
                vehicle_id=vehicle_id,
                action="update_health",
                health={"status": "good", "score": 80},
                rationale="post-service",
            ),
            ShopPreferenceDecision(preferences={"upsell_style": "soft"}),
            KnowledgeRetrievalDecision(query="brake", limit=5),
        ],
        ports=ports,
        context=ctx,
    )
    kinds = {a["kind"] for a in result.applied}
    assert "customer_memory" in kinds
    assert "vehicle_memory" in kinds
    assert "shop_preference" in kinds
    assert "knowledge_retrieval" in kinds
    assert ctx.metadata.get("retrieved_knowledge") is not None


@pytest.mark.asyncio
async def test_knowledge_retrieval_is_read_only(shop_id):
    ensure_default_plugins()
    runtime = build_memory_runtime()
    await runtime.manager.upsert_knowledge_document(
        shop_id, title="Oil change", content="Use OEM filter", tags=["oil"]
    )
    before = len(await runtime.manager.knowledge_store.list_documents(shop_id))
    executor = DecisionExecutor()
    ctx = AgentContext(shop_id=shop_id)
    await executor.apply(
        shop_id=shop_id,
        decisions=[KnowledgeRetrievalDecision(query="oil")],
        ports=DecisionPorts(memory_service=runtime.service),
        context=ctx,
    )
    after = len(await runtime.manager.knowledge_store.list_documents(shop_id))
    assert before == after
