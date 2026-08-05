"""Phase 16 — Owner Dashboard / AI Operations Center tests (read-only)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.dashboard.factory import reset_dashboard_runtime
from app.dashboard.service import DashboardService
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.plugins.framework.plugin import IPlugin
from app.workflows.factory import reset_workflow_runtime


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    reset_dashboard_runtime()
    reset_plugin_runtime()
    yield
    reset_workflow_runtime()
    reset_dashboard_runtime()
    reset_plugin_runtime()


@pytest.mark.asyncio
async def test_dashboard_plugin_registers_read_only_capabilities():
    runtime = ensure_default_plugins()
    plugin = runtime.plugins.lookup("dashboard")
    assert isinstance(plugin, IPlugin)
    caps = set(plugin.supported_capabilities())
    for name in (
        Capability.GET_DAILY_SUMMARY.value,
        Capability.GET_AI_ACTIVITY.value,
        Capability.GET_PENDING_ACTIONS.value,
        Capability.GET_REVENUE_OPPORTUNITIES.value,
        Capability.GET_CUSTOMER_RISK.value,
        Capability.GET_APPOINTMENT_OVERVIEW.value,
        Capability.GET_WORKFLOW_STATUS.value,
        Capability.GET_PERFORMANCE_METRICS.value,
    ):
        assert name in caps
    health = await plugin.health_check()
    assert health["read_only"] is True


@pytest.mark.asyncio
async def test_snapshot_is_read_only_with_required_widgets():
    ensure_default_plugins()
    shop_id = uuid4()
    service = DashboardService()
    snap = await service.get_snapshot(shop_id, force=True)
    assert snap.read_only is True
    ids = {w.id for w in snap.widgets}
    assert "ai_employee_summary" in ids
    assert "todays_appointments" in ids
    assert "revenue_opportunities" in ids
    assert "customer_followup_queue" in ids
    assert "approval_queue" in ids
    assert "ai_escalation_queue" in ids
    assert "workflow_monitor" in ids
    assert "performance_metrics" in ids
    assert "system_health" in snap.to_dict()
    assert snap.system_health.get("status") in {"healthy", "degraded", "down", "unknown"}


@pytest.mark.asyncio
async def test_read_only_capabilities_via_registry():
    ensure_default_plugins()
    shop_id = uuid4()
    ctx = PluginContext.for_shop(shop_id)
    summary = await invoke_capability(
        Capability.GET_DAILY_SUMMARY.value, context=ctx, shop_id=shop_id
    )
    assert summary["read_only"] is True
    assert "summary" in summary

    activity = await invoke_capability(
        Capability.GET_AI_ACTIVITY.value, context=ctx, shop_id=shop_id
    )
    assert activity["read_only"] is True

    pending = await invoke_capability(
        Capability.GET_PENDING_ACTIONS.value, context=ctx, shop_id=shop_id
    )
    assert pending["read_only"] is True

    perf = await invoke_capability(
        Capability.GET_PERFORMANCE_METRICS.value, context=ctx, shop_id=shop_id
    )
    assert perf["read_only"] is True
    assert "performance" in perf


@pytest.mark.asyncio
async def test_api_router_includes_dashboard():
    from app.api.router import api_router

    paths = {getattr(r, "path", None) for r in api_router.routes}
    assert any(p and "/v1/dashboard" in p for p in paths)
