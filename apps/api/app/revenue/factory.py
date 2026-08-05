"""DI factory for Phase 20 Revenue Intelligence Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.revenue.engine import RevenueIntelligenceEngine
from app.revenue.store import InMemoryRetentionInsightStore, RetentionInsightStorePort

_runtime: RevenueIntelligenceRuntime | None = None


@dataclass(slots=True)
class RevenueIntelligenceRuntime:
    engine: RevenueIntelligenceEngine
    insight_store: RetentionInsightStorePort
    revenue_intel_service: Any


def build_revenue_intelligence_runtime(
    *,
    revenue_intel_service: Any | None = None,
    insight_store: RetentionInsightStorePort | None = None,
) -> RevenueIntelligenceRuntime:
    if revenue_intel_service is None:
        from app.revenue_intel.factory import get_revenue_intel_runtime

        revenue_intel_service = get_revenue_intel_runtime().service
    store = insight_store or InMemoryRetentionInsightStore()
    engine = RevenueIntelligenceEngine(service=revenue_intel_service, insight_store=store)
    return RevenueIntelligenceRuntime(
        engine=engine,
        insight_store=store,
        revenue_intel_service=revenue_intel_service,
    )


def get_revenue_intelligence_runtime() -> RevenueIntelligenceRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_revenue_intelligence_runtime()
    return _runtime


def reset_revenue_intelligence_runtime() -> None:
    global _runtime
    _runtime = None
