"""DI factory for scheduling intelligence + agent wiring."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.factory import AgentRuntime, build_agent_runtime
from app.scheduling.agent_adapter import IntelligenceSchedulingStore
from app.scheduling.engines.availability import AvailabilityEngine
from app.scheduling.engines.conflict import ConflictEngine
from app.scheduling.engines.optimization import OptimizationEngine
from app.scheduling.monitoring import SchedulingMonitor
from app.scheduling.service import AppointmentIntelligenceService
from app.scheduling.sql_store import build_default_shop_resource_store
from app.scheduling.store import ShopResourcePort


@dataclass(slots=True)
class SchedulingRuntime:
    service: AppointmentIntelligenceService
    store: ShopResourcePort
    monitor: SchedulingMonitor
    agent_store: IntelligenceSchedulingStore
    agents: AgentRuntime


_runtime: SchedulingRuntime | None = None


def build_scheduling_runtime(
    *,
    store: ShopResourcePort | None = None,
    agents: AgentRuntime | None = None,
) -> SchedulingRuntime:
    resource_store = store or build_default_shop_resource_store()
    availability = AvailabilityEngine()
    conflict = ConflictEngine()
    optimization = OptimizationEngine(availability, conflict)
    service = AppointmentIntelligenceService(
        store=resource_store,
        availability=availability,
        conflict=conflict,
        optimization=optimization,
    )
    agent_store = IntelligenceSchedulingStore(service)
    agent_runtime = agents or build_agent_runtime(scheduling_store=agent_store)
    return SchedulingRuntime(
        service=service,
        store=resource_store,
        monitor=SchedulingMonitor(),
        agent_store=agent_store,
        agents=agent_runtime,
    )


def get_scheduling_runtime() -> SchedulingRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_scheduling_runtime()
    return _runtime


def reset_scheduling_runtime() -> None:
    global _runtime
    _runtime = None
