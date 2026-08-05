"""DI factory for Analytics Engine."""

from __future__ import annotations

from dataclasses import dataclass

from app.analytics.engine import AnalyticsEngine
from app.analytics.exports import ExportService
from app.analytics.forecast import ForecastEngine
from app.analytics.monitoring import AnalyticsMonitor
from app.analytics.reports import ReportBuilder
from app.analytics.service import AnalyticsService
from app.analytics.store import AnalyticsStorePort, InMemoryAnalyticsStore


@dataclass(slots=True)
class AnalyticsRuntime:
    service: AnalyticsService
    store: AnalyticsStorePort
    engine: AnalyticsEngine
    reports: ReportBuilder
    exports: ExportService
    monitor: AnalyticsMonitor


_runtime: AnalyticsRuntime | None = None


def build_analytics_runtime(*, store: AnalyticsStorePort | None = None) -> AnalyticsRuntime:
    resource_store = store or InMemoryAnalyticsStore()
    monitor = AnalyticsMonitor()
    forecast = ForecastEngine(monitor)
    engine = AnalyticsEngine(resource_store, forecast=forecast, monitor=monitor)
    reports = ReportBuilder(monitor)
    exports = ExportService(monitor)
    service = AnalyticsService(
        resource_store,
        engine=engine,
        reports=reports,
        exports=exports,
        monitor=monitor,
    )
    return AnalyticsRuntime(
        service=service,
        store=resource_store,
        engine=engine,
        reports=reports,
        exports=exports,
        monitor=monitor,
    )


def get_analytics_runtime() -> AnalyticsRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_analytics_runtime()
    return _runtime


def reset_analytics_runtime() -> None:
    global _runtime
    _runtime = None
