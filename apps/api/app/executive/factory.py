"""DI factory for Executive Dashboard."""

from __future__ import annotations

from dataclasses import dataclass

from app.executive.aggregator import ExecutiveAggregator
from app.executive.monitoring import ExecutiveMonitor
from app.executive.service import ExecutiveDashboardService
from app.executive.sql_store import build_default_executive_store
from app.executive.store import ExecutiveStorePort


@dataclass(slots=True)
class ExecutiveRuntime:
    service: ExecutiveDashboardService
    store: ExecutiveStorePort
    aggregator: ExecutiveAggregator
    monitor: ExecutiveMonitor


_runtime: ExecutiveRuntime | None = None


def build_executive_runtime(
    *,
    store: ExecutiveStorePort | None = None,
) -> ExecutiveRuntime:
    resource_store = store or build_default_executive_store()
    aggregator = ExecutiveAggregator(resource_store)
    service = ExecutiveDashboardService(store=resource_store, aggregator=aggregator)
    return ExecutiveRuntime(
        service=service,
        store=resource_store,
        aggregator=aggregator,
        monitor=ExecutiveMonitor(),
    )


def get_executive_runtime() -> ExecutiveRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_executive_runtime()
    return _runtime


def reset_executive_runtime() -> None:
    global _runtime
    _runtime = None
