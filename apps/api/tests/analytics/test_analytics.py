"""Phase 16 Analytics Engine tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.analytics.enums import ExportFormat, KpiId, ReportType
from app.analytics.factory import build_analytics_runtime, reset_analytics_runtime
from app.analytics.store import InMemoryAnalyticsStore


@pytest.fixture(autouse=True)
def _reset():
    reset_analytics_runtime()
    yield
    reset_analytics_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def runtime():
    return build_analytics_runtime(store=InMemoryAnalyticsStore())


def test_dashboard_has_required_kpis(runtime, shop_id):
    runtime.engine.seed_demo_facts(shop_id, days=90)
    snap = runtime.service.refresh(shop_id, period_days=30)
    ids = {k.id for k in snap.kpis}
    required = {
        KpiId.REVENUE,
        KpiId.RETENTION,
        KpiId.AVERAGE_REPAIR_ORDER,
        KpiId.CUSTOMER_LIFETIME_VALUE,
        KpiId.APPOINTMENT_CONVERSION,
        KpiId.MARKETING_ROI,
        KpiId.MECHANIC_PRODUCTIVITY,
        KpiId.AI_SUCCESS_RATE,
    }
    assert required.issubset(ids)
    assert snap.forecasts
    assert snap.benchmarks
    assert snap.charts


def test_forecast_and_benchmarks(runtime, shop_id):
    runtime.engine.seed_demo_facts(shop_id, days=90)
    snap = runtime.service.refresh(shop_id)
    assert any(f.kpi == KpiId.REVENUE for f in snap.forecasts)
    assert all(b.status in {"ahead", "on_par", "behind"} for b in snap.benchmarks)
    for k in snap.kpis:
        assert k.benchmark is not None


def test_reports_and_exports(runtime, shop_id):
    runtime.engine.seed_demo_facts(shop_id, days=90)
    report = runtime.service.create_report(shop_id, report_type=ReportType.FULL)
    assert report.sections
    assert report.summary

    csv_export = runtime.service.export_dashboard(shop_id, fmt=ExportFormat.CSV)
    assert csv_export.format == ExportFormat.CSV
    assert "revenue" in csv_export.body.lower()
    assert csv_export.row_count > 0

    json_export = runtime.service.export_report(shop_id, report.id, fmt=ExportFormat.JSON)
    assert json_export.format == ExportFormat.JSON
    assert report.report_type.value in json_export.body

    assert runtime.service.list_reports(shop_id)
    assert runtime.service.list_exports(shop_id)


def test_main_imports_analytics_routes():
    from app.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/v1/analytics/dashboard" in paths
    assert "/v1/analytics/reports" in paths
    assert "/v1/analytics/exports" in paths
