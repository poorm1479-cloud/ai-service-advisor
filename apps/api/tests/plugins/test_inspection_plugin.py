"""Phase 13 — Inspection Intelligence plugin tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.decisions.types import (
    ApprovalRequestDecision,
    CustomerExplanationDecision,
    FollowUpDecision,
    InspectionAnalysisDecision,
    RepairRecommendationDecision,
    SafetyAlertDecision,
)
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.plugins.framework.plugin import IPlugin
from app.plugins.inspection.factory import reset_inspection_plugin
from app.plugins.inspection.templates import TEMPLATES, render_template
from app.workflows.decision_executor import DecisionExecutor, DecisionPorts
from app.workflows.factory import build_workflow_runtime, reset_workflow_runtime
from app.workflows.store import InMemoryWorkflowStore


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    reset_inspection_plugin()
    reset_plugin_runtime()
    yield
    reset_workflow_runtime()
    reset_inspection_plugin()
    reset_plugin_runtime()


def test_templates_cover_required_categories():
    for key in ("safety_warning", "recommended_repair", "optional_repair", "maintenance_reminder"):
        assert key in TEMPLATES
        body = render_template(key, vehicle="2018 Toyota Camry", issue="brake pad wear", amount="320.00")
        assert "Camry" in body
        assert "320.00" in body


@pytest.mark.asyncio
async def test_inspection_registers_capabilities():
    runtime = ensure_default_plugins()
    plugin = runtime.plugins.lookup("inspection")
    assert isinstance(plugin, IPlugin)
    caps = plugin.supported_capabilities()
    assert Capability.ANALYZE_INSPECTION.value in caps
    assert Capability.DETECT_SAFETY_ISSUE.value in caps
    assert Capability.CREATE_APPROVAL_REQUEST.value in caps
    assert Capability.PRIORITIZE_REPAIR.value in caps
    assert Capability.CREATE_FOLLOW_UP.value in caps
    assert Capability.GENERATE_ESTIMATE_SUGGESTION.value in caps
    # Advisor still owns shared names
    advisor = runtime.plugins.lookup("advisor")
    assert Capability.GENERATE_REPAIR_RECOMMENDATION.value in advisor.supported_capabilities()
    assert Capability.GENERATE_CUSTOMER_EXPLANATION.value in advisor.supported_capabilities()


@pytest.mark.asyncio
async def test_analyze_inspection_returns_decisions_only():
    ensure_default_plugins()
    shop_id = uuid4()
    customer_id = uuid4()
    vehicle_id = uuid4()
    out = await invoke_capability(
        Capability.ANALYZE_INSPECTION.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        channel="sms",
        findings=[
            {"title": "Brake pad wear", "severity": "safety", "system": "brakes", "estimated_cost": "380"},
            {"title": "Cabin filter dirty", "severity": "optional", "system": "hvac", "estimated_cost": "49"},
            "oil due — recommend service",
        ],
        vehicle_summary={"year": 2019, "make": "Honda", "model": "Accord"},
    )
    assert "decisions" in out
    decisions = out["decisions"]
    assert any(isinstance(d, InspectionAnalysisDecision) for d in decisions)
    assert any(isinstance(d, SafetyAlertDecision) for d in decisions)
    assert any(isinstance(d, RepairRecommendationDecision) for d in decisions)
    assert any(isinstance(d, CustomerExplanationDecision) for d in decisions)
    assert any(isinstance(d, ApprovalRequestDecision) for d in decisions)
    assert any(isinstance(d, FollowUpDecision) for d in decisions)
    assert out["dashboard"]["safety_issue_count"] >= 1
    # Decide-only: payload is decisions, not CRM mutations
    assert "customer_created" not in out


@pytest.mark.asyncio
async def test_detect_safety_and_prioritize():
    ensure_default_plugins()
    shop_id = uuid4()
    safety = await invoke_capability(
        Capability.DETECT_SAFETY_ISSUE.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        findings=[{"title": "Metal-on-metal brakes", "severity": "critical", "system": "brakes"}],
    )
    assert safety["count"] >= 1
    assert all(isinstance(d, SafetyAlertDecision) for d in safety["decisions"])

    prioritized = await invoke_capability(
        Capability.PRIORITIZE_REPAIR.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        findings=[
            {"title": "Wiper blades", "severity": "optional", "estimated_cost": "25"},
            {"title": "Brake failure risk", "severity": "critical", "estimated_cost": "800"},
            {"title": "Oil change", "severity": "recommended", "estimated_cost": "89"},
        ],
    )
    recs = prioritized["decisions"]
    assert isinstance(recs[0], RepairRecommendationDecision)
    assert recs[0].urgency == "urgent"


@pytest.mark.asyncio
async def test_estimate_approval_followup_capabilities():
    ensure_default_plugins()
    shop_id = uuid4()
    findings = [
        {"title": "Rotor scoring", "severity": "safety", "system": "brakes", "estimated_cost": "420"},
    ]
    est = await invoke_capability(
        Capability.GENERATE_ESTIMATE_SUGGESTION.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        findings=findings,
    )
    assert float(est["estimated_total"]) > 0
    assert est["line_items"]

    approval = await invoke_capability(
        Capability.CREATE_APPROVAL_REQUEST.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        customer_id=uuid4(),
        findings=findings,
    )
    assert any(isinstance(d, ApprovalRequestDecision) for d in approval["decisions"])

    follow = await invoke_capability(
        Capability.CREATE_FOLLOW_UP.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        customer_id=uuid4(),
        findings=findings,
    )
    assert any(isinstance(d, FollowUpDecision) for d in follow["decisions"])


@pytest.mark.asyncio
async def test_decision_executor_applies_inspection_decisions():
    ensure_default_plugins()
    shop_id = uuid4()
    customer_id = uuid4()
    out = await invoke_capability(
        Capability.ANALYZE_INSPECTION.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        customer_id=customer_id,
        vehicle_id=uuid4(),
        findings=[{"title": "Unsafe tire wear", "severity": "safety", "estimated_cost": "500"}],
        vehicle={"year": 2017, "make": "Ford", "model": "Escape"},
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
    assert "inspection_analysis" in kinds
    assert "safety_alert" in kinds
    assert "repair_recommendation" in kinds
    assert "customer_explanation" in kinds
    assert "approval_request" in kinds
    assert "follow_up" in kinds


@pytest.mark.asyncio
async def test_advisor_capabilities_unchanged():
    """Backward compatibility: Advisor still resolves GenerateRepairRecommendation."""
    ensure_default_plugins()
    binding = ensure_default_plugins().capabilities.resolve(
        Capability.GENERATE_REPAIR_RECOMMENDATION.value
    )
    assert binding.plugin_id == "advisor"
