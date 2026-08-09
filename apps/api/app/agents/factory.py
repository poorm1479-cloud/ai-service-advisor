"""Dependency-injection factory for the agent runtime."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.bus.in_memory import InMemoryEventBus
from app.agents.bus.protocol import EventBus
from app.agents.communication.service import CommunicationAgent
from app.agents.crm.interfaces import CrmStorePort
from app.agents.crm.service import CrmAgent, InMemoryCrmStore
from app.agents.customer.interfaces import CustomerDirectoryPort
from app.agents.customer.service import CustomerAgent, InMemoryCustomerDirectory
from app.agents.marketing.interfaces import MarketingDispatcherPort
from app.agents.marketing.service import LoggingMarketingDispatcher, MarketingAgent
from app.agents.mcp.registry import McpToolRegistry
from app.agents.orchestrator import AgentOrchestrator
from app.agents.revenue.service import RevenueAgent
from app.agents.scheduling.catalog_port import (
    InMemoryServiceCatalog,
    ServiceCatalogPort,
    SessionServiceCatalog,
)
from app.agents.scheduling.interfaces import SchedulingStorePort
from app.agents.scheduling.service import InMemorySchedulingStore, SchedulingAgent
from app.agents.supervisor.service import SupervisorAgent
from app.agents.vehicle.interfaces import VehicleDirectoryPort
from app.agents.vehicle.service import InMemoryVehicleDirectory, VehicleAgent


@dataclass(slots=True)
class AgentRuntime:
    """Fully wired agent graph ready for API / workers / tests."""

    bus: EventBus
    orchestrator: AgentOrchestrator
    communication: CommunicationAgent
    intent: object
    customer: CustomerAgent
    vehicle: VehicleAgent
    scheduling: SchedulingAgent
    crm: CrmAgent
    revenue: RevenueAgent
    marketing: MarketingAgent
    supervisor: SupervisorAgent
    mcp: McpToolRegistry


def _default_service_catalog() -> ServiceCatalogPort:
    """Shop catalog for AI booking durations.

    Production/dev use Postgres (SessionServiceCatalog) so SMS/voice bookings
    honor setup durations (e.g. Oil Change = 30m). Tests keep an empty
    in-memory catalog unless they seed one explicitly.
    """
    try:
        from app.infrastructure.config import settings

        if settings.environment.lower() in {"test", "testing"}:
            return InMemoryServiceCatalog()
        from app.infrastructure.database import SessionLocal
        from app.agents.scheduling.catalog_port import CachingServiceCatalog

        # Cache ~60s — cuts multi-DB hits per voice turn (intent + scheduling).
        return CachingServiceCatalog(SessionServiceCatalog(SessionLocal), ttl_sec=60.0)
    except Exception:  # pragma: no cover
        return InMemoryServiceCatalog()


def _default_customer_directory() -> CustomerDirectoryPort:
    """CRM customers for AI resolve — SQL in prod/dev, in-memory in tests."""
    try:
        from app.infrastructure.config import settings

        if settings.environment.lower() in {"test", "testing"}:
            return InMemoryCustomerDirectory()
        from app.infrastructure.agent_directories import SqlCustomerDirectory

        return SqlCustomerDirectory()
    except Exception:  # pragma: no cover
        return InMemoryCustomerDirectory()


def _default_vehicle_directory() -> VehicleDirectoryPort:
    """CRM vehicles for AI resolve — SQL in prod/dev, in-memory in tests."""
    try:
        from app.infrastructure.config import settings

        if settings.environment.lower() in {"test", "testing"}:
            return InMemoryVehicleDirectory()
        from app.infrastructure.agent_directories import SqlVehicleDirectory

        return SqlVehicleDirectory()
    except Exception:  # pragma: no cover
        return InMemoryVehicleDirectory()


def build_agent_runtime(
    *,
    bus: EventBus | None = None,
    customer_directory: CustomerDirectoryPort | None = None,
    vehicle_directory: VehicleDirectoryPort | None = None,
    scheduling_store: SchedulingStorePort | None = None,
    service_catalog: ServiceCatalogPort | None = None,
    crm_store: CrmStorePort | None = None,
    marketing_dispatcher: MarketingDispatcherPort | None = None,
) -> AgentRuntime:
    """Construct agents with constructor injection (swap ports for production adapters)."""
    from app.agents.intent.service import IntentAgent

    event_bus = bus or InMemoryEventBus()
    communication = CommunicationAgent()
    catalog = service_catalog or _default_service_catalog()
    # Intent + scheduling share the shop catalog so conversation understanding
    # and booking both use real Services setup (names, duration, skill).
    intent = IntentAgent(catalog=catalog)
    customer = CustomerAgent(customer_directory or _default_customer_directory())
    vehicle = VehicleAgent(vehicle_directory or _default_vehicle_directory())
    scheduling = SchedulingAgent(
        scheduling_store or InMemorySchedulingStore(),
        catalog=catalog,
    )
    crm = CrmAgent(crm_store or InMemoryCrmStore())
    revenue = RevenueAgent()
    marketing = MarketingAgent(marketing_dispatcher or LoggingMarketingDispatcher())
    supervisor = SupervisorAgent()

    # Phase 15 long-term memory — resolve via Workflow coordinator
    try:
        from app.workflows.factory import get_workflow_runtime

        memory_service = get_workflow_runtime().coordinator.resolve_memory_service()
    except Exception:  # pragma: no cover
        memory_service = None

    orchestrator = AgentOrchestrator(
        bus=event_bus,
        communication=communication,
        intent=intent,
        customer=customer,
        vehicle=vehicle,
        scheduling=scheduling,
        crm=crm,
        revenue=revenue,
        marketing=marketing,
        supervisor=supervisor,
        memory=memory_service,
    )

    mcp = McpToolRegistry.from_runtime(
        customer=customer,
        vehicle=vehicle,
        scheduling=scheduling,
        crm=crm,
        revenue=revenue,
        marketing=marketing,
    )

    return AgentRuntime(
        bus=event_bus,
        orchestrator=orchestrator,
        communication=communication,
        intent=intent,
        customer=customer,
        vehicle=vehicle,
        scheduling=scheduling,
        crm=crm,
        revenue=revenue,
        marketing=marketing,
        supervisor=supervisor,
        mcp=mcp,
    )
