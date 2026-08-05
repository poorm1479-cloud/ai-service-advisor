"""Phase 20 — AI Revenue Intelligence & Customer Retention Engine.

Wraps existing ``revenue_intel`` and Revenue Plugin. AI proposes Decisions only;
Workflow Executor applies business side effects.
"""

from app.revenue.factory import (
    RevenueIntelligenceRuntime,
    build_revenue_intelligence_runtime,
    get_revenue_intelligence_runtime,
    reset_revenue_intelligence_runtime,
)

__all__ = [
    "RevenueIntelligenceRuntime",
    "build_revenue_intelligence_runtime",
    "get_revenue_intelligence_runtime",
    "reset_revenue_intelligence_runtime",
]
