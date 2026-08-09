"""DI factory for Import Engine + agent wiring."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.factory import AgentRuntime, build_agent_runtime
from app.import_engine.monitoring import ImportMonitor
from app.import_engine.service import ImportEngineService
from app.import_engine.store import InMemoryImportStore, ImportStorePort
from app.import_engine.validation import ValidationEngine
from app.infrastructure.config import settings


@dataclass(slots=True)
class ImportRuntime:
    service: ImportEngineService
    store: ImportStorePort
    monitor: ImportMonitor
    agents: AgentRuntime


_runtime: ImportRuntime | None = None


def _build_crm_backed_agents() -> AgentRuntime | None:
    """Wire agents to SQL CRM so import apply shows on /customers and dashboard."""
    try:
        if settings.environment in {"test", "testing"}:
            return None
        from app.infrastructure.agent_directories import SqlCustomerDirectory, SqlVehicleDirectory

        return build_agent_runtime(
            customer_directory=SqlCustomerDirectory(),
            vehicle_directory=SqlVehicleDirectory(),
        )
    except Exception:  # noqa: BLE001
        return None


def _build_import_store() -> ImportStorePort:
    if (settings.import_store_backend or "db").lower() == "memory":
        return InMemoryImportStore()
    if settings.environment in {"test", "testing"}:
        return InMemoryImportStore()
    try:
        from app.import_engine.sql_store import SqlAlchemyImportStore

        return SqlAlchemyImportStore()
    except Exception:  # noqa: BLE001
        return InMemoryImportStore()


def build_import_runtime(
    *,
    store: ImportStorePort | None = None,
    agents: AgentRuntime | None = None,
) -> ImportRuntime:
    # Prefer SQL-backed CRM directories in non-test envs so apply lands in the same
    # tables the customers API reads. Fall back to scheduling-wired / in-memory agents.
    if agents is None:
        agents = _build_crm_backed_agents()
    if agents is None:
        try:
            from app.workflows.factory import get_workflow_runtime

            agents = get_workflow_runtime().coordinator.resolve_scheduling_agents()
        except Exception:  # noqa: BLE001
            agents = build_agent_runtime()

    resource_store = store or _build_import_store()
    service = ImportEngineService(
        store=resource_store,
        validation=ValidationEngine(),
        agents=agents,
    )
    return ImportRuntime(
        service=service,
        store=resource_store,
        monitor=ImportMonitor(),
        agents=agents,
    )


def get_import_runtime() -> ImportRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_import_runtime()
    return _runtime


def reset_import_runtime() -> None:
    global _runtime
    _runtime = None
