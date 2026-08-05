"""Conversation Plugin tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.communication.models import RawInboundMessage
from app.agents.decisions.types import SummaryDecision
from app.agents.factory import build_agent_runtime
from app.plugins.conversation.factory import (
    build_conversation_plugin,
    reset_conversation_plugin,
)
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.plugins.framework.plugin import IPlugin
from app.workflows.factory import build_workflow_runtime, reset_workflow_runtime
from app.workflows.store import InMemoryWorkflowStore


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    reset_conversation_plugin()
    reset_plugin_runtime()
    yield
    reset_workflow_runtime()
    reset_conversation_plugin()
    reset_plugin_runtime()


@pytest.mark.asyncio
async def test_conversation_implements_iplugin():
    runtime = ensure_default_plugins()
    plugin = runtime.plugins.lookup("conversation")
    assert isinstance(plugin, IPlugin)
    assert plugin.plugin_id() == "conversation"
    assert Capability.CREATE_CONVERSATION.value in plugin.supported_capabilities()
    health = await plugin.health_check()
    assert "sms" in health["channels"]
    assert "phone" in health["channels"]


@pytest.mark.asyncio
async def test_create_find_history_summary_via_capability_registry():
    ensure_default_plugins()
    shop_id = uuid4()
    conv = await invoke_capability(
        Capability.CREATE_CONVERSATION.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        channel="sms",
        content="Need an oil change tomorrow",
        sender_identifier="+15551234567",
    )
    assert conv.id is not None
    assert conv.channel == "sms"
    assert len(conv.messages) == 1

    found = await invoke_capability(
        Capability.FIND_CONVERSATION.value,
        shop_id=shop_id,
        conversation_id=conv.id,
    )
    assert found is not None
    assert found.id == conv.id

    history = await invoke_capability(
        Capability.CONVERSATION_HISTORY.value,
        shop_id=shop_id,
        conversation_id=conv.id,
    )
    assert len(history) == 1

    summary = await invoke_capability(
        Capability.CONVERSATION_SUMMARY.value,
        shop_id=shop_id,
        conversation_id=conv.id,
        enrich=True,
        text="Need an oil change tomorrow",
        intent="book_appointment",
    )
    assert summary["ai"]["suggested_service"] == "oil_change"
    assert summary["ai"]["intent"] == "book_appointment"


@pytest.mark.asyncio
async def test_merge_close_search():
    plugin = build_conversation_plugin(register=True)
    shop_id = uuid4()
    a = await plugin.sessions.create(shop_id, channel="sms", external_key="111")
    b = await plugin.sessions.create(shop_id, channel="email", external_key="a@b.com")
    merged = await plugin.invoke(
        Capability.MERGE_CONVERSATION.value,
        shop_id=shop_id,
        primary_id=a.id,
        duplicate_ids=[b.id],
    )
    assert "email" in merged.channel_history or "sms" in merged.channel_history
    closed = await plugin.invoke(
        Capability.CLOSE_CONVERSATION.value,
        shop_id=shop_id,
        conversation_id=a.id,
    )
    assert closed.status == "closed"
    results = await plugin.invoke(
        Capability.SEARCH_CONVERSATION.value,
        shop_id=shop_id,
        channel="sms",
    )
    assert any(c.id == a.id for c in results)


@pytest.mark.asyncio
async def test_orchestrator_sets_conversation_id():
    agents = build_agent_runtime()
    shop_id = uuid4()
    result = await agents.orchestrator.handle_incoming(
        shop_id=shop_id,
        message=RawInboundMessage(
            channel="website_chat",
            content="Hello, brakes squeaking",
            sender_identifier="web-user-1",
        ),
    )
    assert result.context.conversation_id is not None
    ensure_default_plugins()
    found = await invoke_capability(
        Capability.FIND_CONVERSATION.value,
        shop_id=shop_id,
        conversation_id=__import__("uuid").UUID(result.context.conversation_id),
    )
    assert found is not None
    assert found.channel == "website_chat"


@pytest.mark.asyncio
async def test_workflow_applies_summary_to_conversation():
    ensure_default_plugins()
    shop_id = uuid4()
    conv = await invoke_capability(
        Capability.CREATE_CONVERSATION.value,
        shop_id=shop_id,
        channel="email",
        content="Thanks for the great service",
        sender_identifier="c@example.com",
    )
    ctx = AgentContext(
        shop_id=shop_id,
        conversation_id=str(conv.id),
        metadata={"inbound_text": "Thanks for the great service"},
    )
    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    import app.workflows.factory as wf_factory

    wf_factory._runtime = rt
    applied = await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=[
            SummaryDecision(
                summary="Customer thanked shop",
                highlights=["positive"],
                action_items=[],
            )
        ],
        ports=__import__(
            "app.agents.decisions.bridge", fromlist=["ports_from_agents"]
        ).ports_from_agents(),
        context=ctx,
    )
    assert any(a.get("kind") == "summary" for a in applied.applied)
    summary = await invoke_capability(
        Capability.CONVERSATION_SUMMARY.value,
        shop_id=shop_id,
        conversation_id=conv.id,
    )
    assert summary["ai"]["summary"] == "Customer thanked shop"
