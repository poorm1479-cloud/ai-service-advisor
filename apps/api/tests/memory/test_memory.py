"""Phase 15 Long-Term AI Memory tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.communication.models import RawInboundMessage
from app.agents.factory import build_agent_runtime
from app.memory.enums import MemoryCategory, MemoryType
from app.memory.factory import build_memory_runtime, get_memory_runtime, reset_memory_runtime
from app.memory.models import MemoryQuery, RememberRequest
from app.memory.store import InMemoryMemoryStore


@pytest.fixture(autouse=True)
def _reset():
    reset_memory_runtime()
    yield
    reset_memory_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def customer_id():
    return uuid4()


@pytest.fixture
def runtime():
    return build_memory_runtime(store=InMemoryMemoryStore())


def test_memory_types_and_categories(runtime):
    types = set(runtime.service.types())
    assert {"semantic", "conversation", "customer", "business"}.issubset(types)
    # Phase 19 extensions
    assert {"shop", "vehicle", "knowledge"}.issubset(types)
    cats = set(runtime.service.categories())
    for required in {
        "customer_preferences",
        "communication_style",
        "vehicle_history",
        "previous_conversations",
        "repair_decisions",
        "declined_estimates",
        "appointment_behavior",
        "shop_profile",
        "shop_preferences",
        "customer_history",
        "vehicle_health",
        "business_knowledge",
    }:
        assert required in cats


def test_remember_and_semantic_retrieve(runtime, shop_id, customer_id):
    runtime.service.remember(
        RememberRequest(
            shop_id=shop_id,
            content="Customer prefers morning appointments before 10am",
            memory_type=MemoryType.CUSTOMER,
            category=MemoryCategory.CUSTOMER_PREFERENCES,
            customer_id=customer_id,
            importance=0.9,
        )
    )
    runtime.service.remember(
        RememberRequest(
            shop_id=shop_id,
            content="Declined estimate for transmission flush due to cost",
            memory_type=MemoryType.CUSTOMER,
            category=MemoryCategory.DECLINED_ESTIMATES,
            customer_id=customer_id,
            importance=0.95,
        )
    )
    bundle = runtime.service.retrieve(
        MemoryQuery(
            shop_id=shop_id,
            customer_id=customer_id,
            text="morning appointment transmission estimate",
            limit=10,
        )
    )
    assert bundle.hits
    assert bundle.prompt
    contents = " ".join(h.record.content for h in bundle.hits).lower()
    assert "morning" in contents or "declined" in contents


def test_seed_profile_covers_remember_domains(runtime, shop_id, customer_id):
    rows = runtime.service.seed_customer_profile(
        shop_id,
        customer_id,
        preferences=["SMS only"],
        communication_style={"tone": "concise"},
        vehicle_notes=["2019 Toyota Camry"],
        declined_estimates=["Declined alignment"],
        appointment_behavior=["Often late cancellations"],
    )
    assert len(rows) >= 5
    cats = {r.category for r in rows}
    assert MemoryCategory.CUSTOMER_PREFERENCES in cats
    assert MemoryCategory.COMMUNICATION_STYLE in cats
    assert MemoryCategory.VEHICLE_HISTORY in cats
    assert MemoryCategory.DECLINED_ESTIMATES in cats
    assert MemoryCategory.APPOINTMENT_BEHAVIOR in cats


@pytest.mark.asyncio
async def test_orchestrator_auto_loads_and_writes_memory(shop_id, customer_id):
    # Shared singleton so agent factory picks up the same store
    mem = build_memory_runtime(store=InMemoryMemoryStore())
    # Force singleton
    import app.memory.factory as mf

    mf._runtime = mem

    mem.service.seed_customer_profile(
        shop_id,
        customer_id,
        preferences=["Prefers text reminders"],
        communication_style={"tone": "friendly"},
        vehicle_notes=["Brake work in 2024"],
        declined_estimates=["Declined timing belt"],
        appointment_behavior=["Books mid-week"],
    )

    agents = build_agent_runtime()
    result = await agents.orchestrator.handle_incoming(
        shop_id=shop_id,
        customer_id=customer_id,
        message=RawInboundMessage(
            channel="sms",
            content="Can I book an appointment tomorrow morning?",
            sender_identifier="555-0100",
        ),
    )
    assert "long_term_memory" in result.context.metadata
    assert result.context.metadata.get("memory_writes", 0) >= 1
    assert get_memory_runtime().monitor.auto_loads >= 1
    assert get_memory_runtime().monitor.auto_writes >= 1


def test_main_imports_memory_routes():
    from app.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/v1/memory/remember" in paths
    assert "/v1/memory/retrieve" in paths
    assert "/v1/memory/memories" in paths
