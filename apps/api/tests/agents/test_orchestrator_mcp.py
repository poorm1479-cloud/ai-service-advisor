"""Orchestrator + MCP integration tests for the full agent pipeline."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.bus.in_memory import InMemoryEventBus
from app.agents.communication.models import RawInboundMessage
from app.agents.events.definitions import AgentEventType
from app.agents.factory import build_agent_runtime


@pytest.mark.asyncio
async def test_full_pipeline_book_appointment(runtime, shop_id):
    bus = runtime.bus
    assert isinstance(bus, InMemoryEventBus)

    result = await runtime.orchestrator.handle_incoming(
        shop_id=shop_id,
        message=RawInboundMessage(
            channel="sms",
            content="Hi, I need to book an appointment for an oil change. Call me at 555-222-3333.",
            sender_identifier="555-222-3333",
        ),
    )

    assert "communication" in result.stages
    assert "intent" in result.stages
    assert "customer" in result.stages
    assert "vehicle" in result.stages
    assert "scheduling" in result.stages
    assert "crm" in result.stages
    assert "revenue" in result.stages
    assert "supervisor" in result.stages

    intent = result.stages["intent"].data
    assert intent is not None
    assert intent.intent.value == "book_appointment"

    assert result.stages["scheduling"].data is not None
    # Ask when they want to come — do not volunteer openings on book.
    assert result.stages["scheduling"].data.action == "list_slots"
    assert result.stages["scheduling"].data.success
    assert result.stages["scheduling"].data.message == "ask_preferred_time"
    assert result.stages["scheduling"].data.available_slots == []

    assert result.context.customer_id is not None
    assert result.owner_summary

    event_types = [e.event_type for e in bus.history]
    assert AgentEventType.INCOMING_MESSAGE.value in event_types
    assert AgentEventType.COMMUNICATION_NORMALIZED.value in event_types
    assert AgentEventType.INTENT_DETECTED.value in event_types
    assert AgentEventType.CUSTOMER_RESOLVED.value in event_types
    assert AgentEventType.SCHEDULING_RESULT.value in event_types
    assert AgentEventType.CRM_UPDATED.value in event_types
    assert AgentEventType.REVENUE_INSIGHTS.value in event_types
    assert AgentEventType.SUPERVISOR_DECISION.value in event_types
    assert AgentEventType.PIPELINE_COMPLETED.value in event_types


@pytest.mark.asyncio
async def test_emergency_escalates(runtime, shop_id):
    result = await runtime.orchestrator.handle_incoming(
        shop_id=shop_id,
        message=RawInboundMessage(
            channel="phone",
            content="Emergency! My car is smoking and I'm stranded on the highway.",
            sender_identifier="5550001111",
        ),
    )
    assert result.escalate
    assert result.supervisor is not None
    assert result.supervisor.escalate


@pytest.mark.asyncio
async def test_mcp_tools_list_and_call(runtime, shop_id):
    tools = runtime.mcp.list_tools()
    names = {t["name"] for t in tools}
    assert "customer.find_or_create" in names
    assert "scheduling.list_slots" in names
    assert "scheduling.book" in names
    assert "revenue.analyze" in names
    assert "marketing.thank_you" in names

    created = await runtime.mcp.call(
        "customer.find_or_create",
        {"shop_id": str(shop_id), "name": "MCP User", "phone": "5554445555"},
    )
    assert created["success"]
    assert created["customer_id"]

    slots = await runtime.mcp.call("scheduling.list_slots", {"shop_id": str(shop_id)})
    assert slots["success"]
    assert isinstance(slots["slots"], list)


@pytest.mark.asyncio
async def test_pipeline_injects_customer_and_schedule_context(runtime, shop_id):
    from datetime import datetime, timedelta, timezone
    from uuid import UUID

    phone = "555-888-9999"
    created = await runtime.mcp.call(
        "customer.find_or_create",
        {"shop_id": str(shop_id), "name": "Schedule Context", "phone": phone},
    )
    cust_id = UUID(created["customer_id"])
    start = datetime.now(timezone.utc) + timedelta(days=2)
    end = start + timedelta(hours=1)
    await runtime.scheduling.store.book(
        shop_id,
        start=start,
        end=end,
        customer_id=cust_id,
        vehicle_id=None,
        service_name="Oil Change",
    )

    result = await runtime.orchestrator.handle_incoming(
        shop_id=shop_id,
        message=RawInboundMessage(
            channel="sms",
            content="Just checking in",
            sender_identifier=phone,
        ),
        customer_id=cust_id,
    )
    snap = result.context.metadata.get("customer_snapshot") or {}
    assert snap.get("name")
    upcoming = result.context.metadata.get("upcoming_appointments") or []
    assert upcoming
    assert any(a.get("service_name") == "Oil Change" for a in upcoming)
    assert result.context.metadata.get("active_appointment_id")


@pytest.mark.asyncio
async def test_build_agent_runtime_isolation():
    a = build_agent_runtime()
    b = build_agent_runtime()
    assert a.bus is not b.bus
    assert a.orchestrator is not b.orchestrator


@pytest.mark.asyncio
async def test_walk_in_and_website_channels(runtime, shop_id):
    for channel in ("walk_in", "website_chat", "facebook", "email"):
        result = await runtime.orchestrator.handle_incoming(
            shop_id=shop_id,
            message=RawInboundMessage(
                channel=channel,
                content="Just checking prices for a tune-up",
                sender_identifier=f"user-{uuid4().hex[:6]}@example.com",
                subject="Price check" if channel == "email" else None,
            ),
        )
        assert result.stages["communication"].success
        assert result.stages["intent"].data.intent.value in {
            "price_question",
            "maintenance_question",
            "other",
        }
