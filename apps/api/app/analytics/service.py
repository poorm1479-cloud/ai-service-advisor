"""Analytics Engine service facade."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from app.analytics.engine import AnalyticsEngine
from app.analytics.enums import ExportFormat, ReportType
from app.analytics.exports import ExportService
from app.analytics.models import (
    AnalyticsReport,
    AnalyticsSnapshot,
    ExportArtifact,
    ShopMetricFact,
)
from app.analytics.monitoring import AnalyticsMonitor
from app.analytics.reports import ReportBuilder
from app.analytics.store import AnalyticsStorePort


class AnalyticsService:
    def __init__(
        self,
        store: AnalyticsStorePort,
        *,
        engine: AnalyticsEngine,
        reports: ReportBuilder,
        exports: ExportService,
        monitor: AnalyticsMonitor,
    ) -> None:
        self._store = store
        self.engine = engine
        self.reports = reports
        self.exports = exports
        self.monitor = monitor

    def dashboard(
        self,
        shop_id: UUID,
        *,
        period_days: int = 30,
        forecast_horizon: int = 30,
        force: bool = False,
    ) -> AnalyticsSnapshot:
        if not force:
            cached = self._store.get_snapshot(shop_id)
            if cached is not None:
                return cached
        return self.engine.build_snapshot(
            shop_id,
            period_days=period_days,
            forecast_horizon=forecast_horizon,
        )

    def refresh(
        self,
        shop_id: UUID,
        *,
        period_days: int = 30,
        forecast_horizon: int = 30,
    ) -> AnalyticsSnapshot:
        return self.engine.build_snapshot(
            shop_id,
            period_days=period_days,
            forecast_horizon=forecast_horizon,
        )

    def create_report(
        self,
        shop_id: UUID,
        *,
        report_type: ReportType = ReportType.FULL,
        title: str | None = None,
        period_days: int = 30,
    ) -> AnalyticsReport:
        snap = self.refresh(shop_id, period_days=period_days)
        report = self.reports.build(snap, report_type=report_type, title=title)
        return self._store.save_report(report)

    def list_reports(self, shop_id: UUID, *, limit: int = 50) -> list[AnalyticsReport]:
        return self._store.list_reports(shop_id, limit=limit)

    def get_report(self, shop_id: UUID, report_id: UUID) -> AnalyticsReport | None:
        return self._store.get_report(shop_id, report_id)

    def export_dashboard(
        self,
        shop_id: UUID,
        *,
        fmt: ExportFormat = ExportFormat.CSV,
        period_days: int = 30,
    ) -> ExportArtifact:
        snap = self.dashboard(shop_id, period_days=period_days, force=True)
        artifact = self.exports.export_snapshot(snap, fmt=fmt)
        return self._store.save_export(artifact)

    def export_report(
        self,
        shop_id: UUID,
        report_id: UUID,
        *,
        fmt: ExportFormat = ExportFormat.JSON,
    ) -> ExportArtifact:
        report = self._store.get_report(shop_id, report_id)
        if report is None:
            raise KeyError(f"Report not found: {report_id}")
        artifact = self.exports.export_report(report, fmt=fmt)
        return self._store.save_export(artifact)

    def list_exports(self, shop_id: UUID, *, limit: int = 50) -> list[ExportArtifact]:
        return self._store.list_exports(shop_id, limit=limit)

    def get_export(self, shop_id: UUID, export_id: UUID) -> ExportArtifact | None:
        return self._store.get_export(shop_id, export_id)

    def ingest_fact(self, fact: ShopMetricFact) -> ShopMetricFact:
        saved = self._store.save_fact(fact)
        self.monitor.record_facts(1)
        return saved

    def list_facts(
        self,
        shop_id: UUID,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[ShopMetricFact]:
        return self._store.list_facts(shop_id, start=start, end=end)

    def metrics(self) -> dict[str, Any]:
        return self.monitor.snapshot()
