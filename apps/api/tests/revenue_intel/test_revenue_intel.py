"""Phase 11 Revenue Intelligence tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.revenue_intel.enums import OpportunityHorizon, OpportunityKind, OpportunityStatus
from app.revenue_intel.factory import (
    build_revenue_intel_runtime,
    reset_revenue_intel_runtime,
)
from app.revenue_intel.store import InMemoryRevenueIntelStore


@pytest.fixture(autouse=True)
def _reset():
    reset_revenue_intel_runtime()
    yield
    reset_revenue_intel_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def runtime(shop_id):
    store = InMemoryRevenueIntelStore()
    store.seed_demo_customers(shop_id)
    return build_revenue_intel_runtime(store=store)


@pytest.mark.asyncio
async def test_nightly_analysis_generates_opportunities(runtime, shop_id):
    report = await runtime.service.run_nightly_analysis(shop_id)
    assert report.job.status.value == "completed"
    assert report.job.customers_analyzed == 4
    assert report.job.opportunities_created > 0
    assert report.opportunities
    assert report.customer_scores
    assert report.vehicle_scores
    assert report.forecast.months
    assert report.dashboard.open_opportunities > 0


@pytest.mark.asyncio
async def test_finds_lost_customer_and_maintenance(runtime, shop_id):
    report = await runtime.service.run_nightly_analysis(shop_id)
    kinds = {o.kind for o in report.opportunities}
    assert OpportunityKind.LOST_CUSTOMER in kinds
    assert OpportunityKind.MAINTENANCE_OVERDUE in kinds or OpportunityKind.OIL_CHANGE in kinds
    assert OpportunityKind.DECLINED_ESTIMATE in kinds or OpportunityKind.LIKELY_ACCEPT in kinds


@pytest.mark.asyncio
async def test_opportunity_has_contact_plan(runtime, shop_id):
    report = await runtime.service.run_nightly_analysis(shop_id)
    opp = report.opportunities[0]
    assert opp.expected_revenue > 0
    assert 0 < opp.probability <= 1
    assert opp.recommended_contact_date is not None
    assert opp.recommended_channel
    assert opp.recommended_message
    assert opp.expected_roi is not None


@pytest.mark.asyncio
async def test_daily_weekly_lists_and_forecast(runtime, shop_id):
    await runtime.service.run_nightly_analysis(shop_id)
    daily = await runtime.service.list_opportunities(
        shop_id, horizon=OpportunityHorizon.DAILY
    )
    weekly = await runtime.service.list_opportunities(
        shop_id, horizon=OpportunityHorizon.WEEKLY
    )
    dash = await runtime.service.build_dashboard(shop_id)
    assert dash.expected_revenue_monthly >= 0
    assert dash.forecast is not None
    assert len(dash.roi_series) >= 1
    assert isinstance(daily, list)
    assert isinstance(weekly, list)


@pytest.mark.asyncio
async def test_health_scores_bands(runtime, shop_id):
    report = await runtime.service.run_nightly_analysis(shop_id)
    for s in report.customer_scores:
        assert 0 <= s.score <= 100
        assert s.band
    for s in report.vehicle_scores:
        assert 0 <= s.score <= 100


@pytest.mark.asyncio
async def test_update_opportunity_status(runtime, shop_id):
    report = await runtime.service.run_nightly_analysis(shop_id)
    opp = report.opportunities[0]
    updated = await runtime.service.update_opportunity_status(
        shop_id, opp.id, OpportunityStatus.CONTACTED
    )
    assert updated.status == OpportunityStatus.CONTACTED


@pytest.mark.asyncio
async def test_agent_adapter(runtime, shop_id):
    from app.revenue_intel.agent_adapter import opportunities_to_agent_insights

    report = await runtime.service.run_nightly_analysis(shop_id)
    insights = opportunities_to_agent_insights(report.opportunities[:5])
    assert insights.upsell_opportunities
    assert insights.predicted_revenue >= 0
