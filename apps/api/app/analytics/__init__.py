"""Phase 16 — Analytics Engine.

Shop KPIs, forecasts, benchmarks, reports, and exports.
"""

from app.analytics.factory import (
    AnalyticsRuntime,
    build_analytics_runtime,
    get_analytics_runtime,
    reset_analytics_runtime,
)

__all__ = [
    "AnalyticsRuntime",
    "build_analytics_runtime",
    "get_analytics_runtime",
    "reset_analytics_runtime",
]
