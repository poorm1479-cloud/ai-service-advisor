"""Revenue Intelligence Plugin — Workflow-facing façade over revenue_intel."""

from app.plugins.revenue.factory import (
    build_revenue_plugin,
    get_revenue_plugin,
    reset_revenue_plugin,
    revenue_plugin_from_ports,
)
from app.plugins.revenue.interfaces import IRevenuePlugin
from app.plugins.revenue.models import RevenueOpportunity
from app.plugins.revenue.plugin import RevenuePlugin

__all__ = [
    "IRevenuePlugin",
    "RevenueOpportunity",
    "RevenuePlugin",
    "build_revenue_plugin",
    "get_revenue_plugin",
    "reset_revenue_plugin",
    "revenue_plugin_from_ports",
]
