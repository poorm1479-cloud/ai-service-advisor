"""Phase 21 AI Learning Loop tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.decisions.types import (
    LearningFeedbackDecision,
    OptimizationDecision,
    PatternDiscoveryDecision,
)
from app.learning.factory import (
    build_learning_runtime,
    reset_learning_runtime,
)
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.workflows.decision_executor import DecisionExecutor, DecisionPorts


@pytest.fixture(autouse=True)
def _reset():
    reset_plugin_runtime()
    reset_learning_runtime()
    yield
    reset_plugin_runtime()
    reset_learning_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.mark.asyncio
async def test_phase21_capabilities_registered():
    ensure_default_plugins()
    from app.plugins.framework.capability import get_capability_registry

    caps = {c["capability"] for c in get_capability_registry().list_capabilities()}
    for name in (
        "CollectDecisionResult",
        "EvaluateDecision",
        "LearnCustomerResponse",
        "AnalyzeSuccessPattern",
        "OptimizeRecommendation",
        "GenerateLearningInsight",
    ):
        assert name in caps


@pytest.mark.asyncio
async def test_collect_evaluate_and_customer_response(shop_id):
    ensure_default_plugins()
    ctx = PluginContext.for_shop(shop_id)
    collected = await invoke_capability(
        Capability.COLLECT_DECISION_RESULT.value,
        context=ctx,
        shop_id=shop_id,
        decision_kind="appointment",
        outcome_kind="appointment_conversion",
        success=True,
    )
    assert collected.get("ai_actions_allowed") is False
    assert collected["result"]["success"] is True

    await invoke_capability(
        Capability.COLLECT_DECISION_RESULT.value,
        context=ctx,
        shop_id=shop_id,
        decision_kind="appointment",
        outcome_kind="appointment_conversion",
        success=False,
    )
    evaluated = await invoke_capability(
        Capability.EVALUATE_DECISION.value,
        context=ctx,
        shop_id=shop_id,
        decision_kind="appointment",
    )
    assert evaluated["total"] == 2
    assert evaluated["accuracy"] == 0.5
    assert evaluated.get("ai_actions_allowed") is False

    customer = await invoke_capability(
        Capability.LEARN_CUSTOMER_RESPONSE.value,
        context=ctx,
        shop_id=shop_id,
        positive=True,
        comment="Helpful",
    )
    assert customer.get("ai_actions_allowed") is False
    assert customer["feedback"]["source"] == "customer"


@pytest.mark.asyncio
async def test_patterns_optimize_insight_never_auto_apply(shop_id):
    ensure_default_plugins()
    ctx = PluginContext.for_shop(shop_id)
    for ok in (True, True, False):
        await invoke_capability(
            Capability.COLLECT_DECISION_RESULT.value,
            context=ctx,
            shop_id=shop_id,
            decision_kind="repair",
            outcome_kind="repair_approval",
            success=ok,
        )
    patterns = await invoke_capability(
        Capability.ANALYZE_SUCCESS_PATTERN.value,
        context=ctx,
        shop_id=shop_id,
    )
    assert patterns.get("ai_actions_allowed") is False
    assert patterns["count"] >= 1
    assert isinstance(patterns["decisions"][0], PatternDiscoveryDecision)

    opt = await invoke_capability(
        Capability.OPTIMIZE_RECOMMENDATION.value,
        context=ctx,
        shop_id=shop_id,
    )
    assert opt.get("auto_apply") is False
    assert opt.get("ai_actions_allowed") is False
    assert isinstance(opt["decision"], OptimizationDecision)
    # Capability response must not auto-apply even if decision field is True
    assert opt["auto_apply"] is False

    insight = await invoke_capability(
        Capability.GENERATE_LEARNING_INSIGHT.value,
        context=ctx,
        shop_id=shop_id,
    )
    assert insight.get("ai_actions_allowed") is False
    assert isinstance(insight["decision"], LearningFeedbackDecision)
    assert insight["decision"].requires_review is True


@pytest.mark.asyncio
async def test_decisions_do_not_mutate_workflows_or_prices(shop_id):
    ensure_default_plugins()
    executor = DecisionExecutor()
    ctx = AgentContext(shop_id=shop_id)
    result = await executor.apply(
        shop_id=shop_id,
        decisions=[
            LearningFeedbackDecision(
                source="staff",
                summary="Tone down aggressive upsell",
                insights=["Lower upsell pressure"],
            ),
            OptimizationDecision(
                target="recommendations",
                suggestions=["Prefer maintenance reminders over upsell"],
                auto_apply=True,  # must still be blocked
            ),
            PatternDiscoveryDecision(
                pattern_key="repair:repair_approval",
                description="Repair approvals succeed often",
                support_count=10,
                success_rate=0.8,
            ),
        ],
        ports=DecisionPorts(),
        context=ctx,
    )
    kinds = {a["kind"] for a in result.applied}
    assert "learning_feedback" in kinds
    assert "optimization" in kinds
    assert "pattern_discovery" in kinds
    opt = next(a for a in result.applied if a["kind"] == "optimization")
    assert opt.get("applied") is False
    assert opt.get("auto_apply") is False
    assert opt.get("workflow_modified") is False
    feedback = next(a for a in result.applied if a["kind"] == "learning_feedback")
    assert feedback.get("rules_changed") is False
    pattern = next(a for a in result.applied if a["kind"] == "pattern_discovery")
    assert pattern.get("rules_changed") is False


@pytest.mark.asyncio
async def test_dashboard_metrics(shop_id):
    rt = build_learning_runtime()
    await rt.engine.collect_decision_result(
        shop_id,
        decision_kind="revenue",
        outcome_kind="revenue",
        success=True,
        score=0.9,
    )
    metrics = await rt.engine.dashboard_metrics(shop_id)
    for key in (
        "decision_accuracy",
        "appointment_conversion_improvement",
        "repair_approval_rate",
        "customer_retention_improvement",
        "revenue_impact",
    ):
        assert key in metrics
    assert metrics["ai_actions_allowed"] is False


@pytest.mark.asyncio
async def test_staff_and_workflow_feedback_via_collect(shop_id):
    ensure_default_plugins()
    ctx = PluginContext.for_shop(shop_id)
    staff = await invoke_capability(
        Capability.COLLECT_DECISION_RESULT.value,
        context=ctx,
        shop_id=shop_id,
        source="staff",
        comment="Good call handling",
        rating=0.9,
    )
    assert staff.get("auto_applied") is False
    assert staff["feedback"]["source"] == "staff"

    wf = await invoke_capability(
        Capability.COLLECT_DECISION_RESULT.value,
        context=ctx,
        shop_id=shop_id,
        source="workflow",
        success=True,
        notes="run completed",
    )
    assert wf.get("workflow_modified") is False
    assert wf["result"]["success"] is True
