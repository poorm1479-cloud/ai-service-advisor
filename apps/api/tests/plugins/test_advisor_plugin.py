"""AI Service Advisor Plugin tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.communication.models import RawInboundMessage
from app.agents.decisions.bridge import ports_from_agents
from app.agents.decisions.types import (
    ApprovalRequestDecision,
    CustomerCommunicationDecision,
    RepairRecommendationDecision,
)
from app.agents.factory import build_agent_runtime
from app.plugins.advisor.factory import reset_advisor_plugin
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
    reset_advisor_plugin()
    reset_plugin_runtime()
    yield
    reset_workflow_runtime()
    reset_advisor_plugin()
    reset_plugin_runtime()


@pytest.mark.asyncio
async def test_advisor_registers_capabilities():
    runtime = ensure_default_plugins()
    plugin = runtime.plugins.lookup("advisor")
    assert isinstance(plugin, IPlugin)
    assert Capability.ANALYZE_CONVERSATION.value in plugin.supported_capabilities()
    assert Capability.GENERATE_REPAIR_RECOMMENDATION.value in plugin.supported_capabilities()


@pytest.mark.asyncio
async def test_analyze_conversation_returns_decisions_only():
    ensure_default_plugins()
    shop_id = uuid4()
    out = await invoke_capability(
        Capability.ANALYZE_CONVERSATION.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        channel="sms",
        inbound_text="My brakes are squeaking badly",
        intent="repair",
        customer_id=uuid4(),
        vehicle={"year": 2018, "make": "Toyota", "model": "Camry", "mileage": 72000},
    )
    assert "decisions" in out
    assert any(isinstance(d, RepairRecommendationDecision) for d in out["decisions"])
    assert any(isinstance(d, CustomerCommunicationDecision) for d in out["decisions"])
    assert out["advisor_notes"]
    assert "dashboard" in out


@pytest.mark.asyncio
async def test_workflow_applies_advisor_decisions():
    ensure_default_plugins()
    shop_id = uuid4()
    customer_id = uuid4()
    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    import app.workflows.factory as wf_factory

    wf_factory._runtime = rt
    ctx = AgentContext(shop_id=shop_id, customer_id=customer_id, conversation_id=str(uuid4()))
    applied = await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=[
            CustomerCommunicationDecision(
                customer_id=customer_id,
                channel="sms",
                body="We recommend a brake inspection soon.",
                rationale="test",
            ),
            ApprovalRequestDecision(
                customer_id=customer_id,
                amount=__import__("decimal").Decimal("349.00"),
                services=["brakes"],
                message_body="Reply YES to approve brake service.",
            ),
        ],
        ports=ports_from_agents(),
        context=ctx,
    )
    kinds = {a.get("kind") for a in applied.applied}
    assert "customer_communication" in kinds
    assert "approval_request" in kinds


@pytest.mark.asyncio
async def test_orchestrator_runs_advisor_stage():
    agents = build_agent_runtime()
    shop_id = uuid4()
    result = await agents.orchestrator.handle_incoming(
        shop_id=shop_id,
        message=RawInboundMessage(
            channel="sms",
            content="Need oil change and status update please",
            sender_identifier="+15550001111",
        ),
    )
    assert "advisor" in result.stages or any(
        getattr(getattr(d, "kind", None), "value", None)
        in {
            "repair_recommendation",
            "customer_communication",
            "maintenance_reminder",
            "estimate_explanation",
        }
        for d in result.decisions
    )
