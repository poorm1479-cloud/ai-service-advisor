"""Scheduling Plugin tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.decisions.bridge import ports_from_agents
from app.agents.decisions.types import AppointmentDecision
from app.agents.scheduling.service import SchedulingAgent
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import (
    ensure_default_plugins,
    invoke_capability,
    reset_plugin_runtime,
)
from app.plugins.framework.plugin import IPlugin
from app.plugins.scheduling.factory import build_scheduling_plugin, reset_scheduling_plugin
from app.workflows.factory import build_workflow_runtime, reset_workflow_runtime
from app.workflows.store import InMemoryWorkflowStore


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    reset_scheduling_plugin()
    reset_plugin_runtime()
    yield
    reset_workflow_runtime()
    reset_scheduling_plugin()
    reset_plugin_runtime()


@pytest.mark.asyncio
async def test_scheduling_implements_iplugin():
    runtime = ensure_default_plugins()
    plugin = runtime.plugins.lookup("scheduling")
    assert isinstance(plugin, IPlugin)
    assert plugin.plugin_id() == "scheduling"
    assert Capability.BOOK_APPOINTMENT.value in plugin.supported_capabilities()
    health = await plugin.health_check()
    assert health["plugin_id"] == "scheduling"


@pytest.mark.asyncio
async def test_book_via_capability_registry():
    ensure_default_plugins()
    shop_id = uuid4()
    slots = await invoke_capability(
        Capability.FIND_AVAILABLE_SLOT.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        days_ahead=7,
    )
    assert len(slots) > 0
    appt = await invoke_capability(
        Capability.BOOK_APPOINTMENT.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        start=slots[0].start,
        end=slots[0].end,
        customer_id=uuid4(),
    )
    assert appt.id is not None
    assert appt.status == "booked"


@pytest.mark.asyncio
async def test_workflow_applies_appointment_via_scheduling_plugin():
    shop_id = uuid4()
    ctx = AgentContext(shop_id=shop_id)
    scheduling = SchedulingAgent()
    ports = ports_from_agents(scheduling=scheduling)
    assert ports.scheduling_plugin is not None

    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    import app.workflows.factory as wf_factory

    wf_factory._runtime = rt

    slots = await scheduling.store.list_available_slots(shop_id, days_ahead=7)
    decision = AppointmentDecision(
        action="book",
        recommended_slot_start=slots[0].start,
        recommended_slot_end=slots[0].end,
        customer_id=uuid4(),
    )
    applied = await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=[decision],
        ports=ports,
        context=ctx,
    )
    assert applied.scheduling_result is not None
    assert applied.scheduling_result.success
    assert applied.scheduling_result.appointment is not None


@pytest.mark.asyncio
async def test_walk_in_and_assign_capabilities():
    plugin = build_scheduling_plugin(register=True)
    shop_id = uuid4()
    result = await plugin.invoke(
        Capability.WALK_IN_CHECK_IN.value,
        context=PluginContext.for_shop(shop_id),
        shop_id=shop_id,
        customer_id=uuid4(),
    )
    assert result["success"] is True
    appt = result["appointment"]
    mech = await plugin.invoke(
        Capability.ASSIGN_MECHANIC.value,
        shop_id=shop_id,
        appointment_id=appt.id,
    )
    assert mech["assigned"] is True
    assert mech["mechanic_id"]
    bay = await plugin.invoke(
        Capability.ASSIGN_BAY.value,
        shop_id=shop_id,
        appointment_id=appt.id,
    )
    assert bay["assigned"] is True
    assert bay["bay_id"]


@pytest.mark.asyncio
async def test_validate_conflict_history_capabilities():
    plugin = build_scheduling_plugin(register=True)
    shop_id = uuid4()
    slots = await plugin.invoke(
        Capability.FIND_AVAILABLE_SLOT.value,
        shop_id=shop_id,
        days_ahead=7,
    )
    start, end = slots[0].start, slots[0].end
    validation = await plugin.invoke(
        Capability.VALIDATE_APPOINTMENT.value,
        shop_id=shop_id,
        start=start,
        end=end,
    )
    assert validation["valid"] is True
    appt = await plugin.invoke(
        Capability.BOOK_APPOINTMENT.value,
        shop_id=shop_id,
        start=start,
        end=end,
        customer_id=uuid4(),
    )
    conflict = await plugin.invoke(
        Capability.DETECT_CONFLICT.value,
        shop_id=shop_id,
        start=start,
        end=end,
    )
    assert conflict["has_conflict"] is True
    history = await plugin.invoke(
        Capability.APPOINTMENT_HISTORY.value,
        shop_id=shop_id,
        customer_id=appt.customer_id,
    )
    assert any(a.id == appt.id for a in history)
    duration = await plugin.invoke(
        Capability.ESTIMATE_DURATION.value,
        shop_id=shop_id,
        repair_type="oil_change",
    )
    assert duration == 45
    avail = await plugin.invoke(
        Capability.CHECK_AVAILABILITY.value,
        shop_id=shop_id,
        start=start + timedelta(days=1),
        end=end + timedelta(days=1),
    )
    assert "available" in avail
