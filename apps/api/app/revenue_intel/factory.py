"""DI factory for Revenue Intelligence."""

from __future__ import annotations

from dataclasses import dataclass

from app.revenue_intel.engine import RevenueAnalysisEngine
from app.revenue_intel.monitoring import RevenueIntelMonitor
from app.revenue_intel.service import RevenueIntelService
from app.revenue_intel.store import InMemoryRevenueIntelStore, RevenueIntelStorePort


@dataclass(slots=True)
class RevenueIntelRuntime:
    service: RevenueIntelService
    store: RevenueIntelStorePort
    engine: RevenueAnalysisEngine
    monitor: RevenueIntelMonitor


_runtime: RevenueIntelRuntime | None = None


def build_revenue_intel_runtime(
    *,
    store: RevenueIntelStorePort | None = None,
) -> RevenueIntelRuntime:
    resource_store = store or InMemoryRevenueIntelStore()
    engine = RevenueAnalysisEngine()
    service = RevenueIntelService(store=resource_store, engine=engine)
    return RevenueIntelRuntime(
        service=service,
        store=resource_store,
        engine=engine,
        monitor=RevenueIntelMonitor(),
    )


def get_revenue_intel_runtime() -> RevenueIntelRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_revenue_intel_runtime()
    return _runtime


def reset_revenue_intel_runtime() -> None:
    global _runtime
    _runtime = None
