"""Phase 20 Revenue Intelligence & Retention tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.decisions.types import (
    CampaignRecommendationDecision,
    ContactTimingDecision,
    CustomerRetentionDecision,
    CustomerValueDecision,
    RevenueOpportunityDecision,
    ServiceRecommendationDecision,
)
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.revenue.factory import (
    build_revenue_intelligence_runtime,
    reset_revenue_intelligence_runtime,
)
from app.revenue_intel.factory import reset_revenue_intel_runtime
from app.workflows.decision_executor import DecisionExecutor, DecisionPorts


@pytest.fixture(autouse=True)
def _reset():
    reset_plugin_runtime()
    reset_revenue_intelligence_runtime()
    reset_revenue_intel_runtime()
    yield
    reset_plugin_runtime()
    reset_revenue_intelligence_runtime()
    reset_revenue_intel_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.mark.asyncio
async def test_phase20_capabilities_registered():
    ensure_default_plugins()
    from app.plugins.framework.capability import get_capability_registry

    caps = {c["capability"] for c in get_capability_registry().list_capabilities()}
    for name in (
        "AnalyzeCustomerValue",
        "PredictCustomerRisk",
        "DetectRevenueOpportunity",
        "RecommendService",
        "RecommendContactTiming",
        "CreateRetentionPlan",
        "AnalyzeLostRevenue",
        "GenerateCampaignSuggestion",
    ):
        assert name in caps


@pytest.mark.asyncio
async def test_analyze_and_lost_revenue_caps(shop_id):
    ensure_default_plugins()
    ctx = PluginContext.for_shop(shop_id)
    value = await invoke_capability(
        Capability.ANALYZE_CUSTOMER_VALUE.value, context=ctx, shop_id=shop_id
    )
    assert value.get("ai_actions_allowed") is False
    lost = await invoke_capability(
        Capability.ANALYZE_LOST_REVENUE.value, context=ctx, shop_id=shop_id
    )
    assert "total_lost_revenue_estimate" in lost
    risk = await invoke_capability(
        Capability.PREDICT_CUSTOMER_RISK.value, context=ctx, shop_id=shop_id
    )
    assert "at_risk_count" in risk or "churn_risk" in risk


@pytest.mark.asyncio
async def test_campaign_suggestion_never_autosends(shop_id):
    ensure_default_plugins()
    ctx = PluginContext.for_shop(shop_id)
    result = await invoke_capability(
        Capability.GENERATE_CAMPAIGN_SUGGESTION.value,
        context=ctx,
        shop_id=shop_id,
        campaign_type="winback",
    )
    assert result.get("auto_send") is False
    assert result.get("ai_actions_allowed") is False


@pytest.mark.asyncio
async def test_retention_plan_returns_decision(shop_id):
    ensure_default_plugins()
    customer_id = uuid4()
    ctx = PluginContext.for_shop(shop_id, customer_id=customer_id)
    result = await invoke_capability(
        Capability.CREATE_RETENTION_PLAN.value,
        context=ctx,
        shop_id=shop_id,
        customer_id=customer_id,
    )
    assert result.get("ai_actions_allowed") is False
    assert result.get("decision") is not None
    assert isinstance(result["decision"], CustomerRetentionDecision)


@pytest.mark.asyncio
async def test_decisions_applied_without_marketing_send(shop_id):
    ensure_default_plugins()
    customer_id = uuid4()
    executor = DecisionExecutor()
    ctx = AgentContext(shop_id=shop_id, customer_id=customer_id)
    result = await executor.apply(
        shop_id=shop_id,
        decisions=[
            CustomerRetentionDecision(
                customer_id=customer_id,
                risk_score=0.8,
                plan="Call within 48h",
                actions=["personal_check_in"],
                priority="high",
            ),
            RevenueOpportunityDecision(
                customer_id=customer_id,
                opportunity_kind="upsell",
                title="Brake service",
                expected_revenue=350.0,
            ),
            ServiceRecommendationDecision(
                customer_id=customer_id,
                service="oil_change",
                reason="Overdue",
            ),
            ContactTimingDecision(
                customer_id=customer_id,
                preferred_window="weekday_morning",
            ),
            CampaignRecommendationDecision(
                customer_id=customer_id,
                campaign_type="retention",
                auto_send=True,  # must still be blocked
                message_draft="Come back",
            ),
            CustomerValueDecision(
                customer_id=customer_id,
                lifetime_value=2400.0,
                churn_risk=0.4,
            ),
        ],
        ports=DecisionPorts(),
        context=ctx,
    )
    kinds = {a["kind"] for a in result.applied}
    assert "customer_retention" in kinds
    assert "campaign_recommendation" in kinds
    campaign = next(a for a in result.applied if a["kind"] == "campaign_recommendation")
    assert campaign.get("sent") is False
    assert campaign.get("auto_send") is False


@pytest.mark.asyncio
async def test_dashboard_metrics(shop_id):
    rt = build_revenue_intelligence_runtime()
    metrics = await rt.engine.dashboard_metrics(shop_id)
    for key in (
        "customer_retention_rate",
        "lost_customer_risk",
        "revenue_opportunities",
        "recovered_revenue",
        "service_recommendations",
        "campaign_performance",
    ):
        assert key in metrics
    assert metrics["campaign_performance"]["auto_send_blocked"] is True
