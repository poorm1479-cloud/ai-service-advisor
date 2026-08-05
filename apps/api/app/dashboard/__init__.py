"""Owner Dashboard & AI Operations Center (read-only)."""

from app.dashboard.api import router
from app.dashboard.factory import (
    DashboardRuntime,
    build_dashboard_plugin,
    get_dashboard_runtime,
    reset_dashboard_runtime,
)
from app.dashboard.service import DashboardService

__all__ = [
    "DashboardRuntime",
    "DashboardService",
    "build_dashboard_plugin",
    "get_dashboard_runtime",
    "reset_dashboard_runtime",
    "router",
]
