"""Bridge helpers — apply AI Decisions via Workflow (for tests / MCP)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.decisions.types import Decision


def ports_from_agents(
    *,
    customer: Any = None,
    vehicle: Any = None,
    scheduling: Any = None,
    crm: Any = None,
    marketing: Any = None,
    memory: Any = None,
    crm_plugin: Any = None,
    scheduling_plugin: Any = None,
    conversation_plugin: Any = None,
    revenue_plugin: Any = None,
    advisor_plugin: Any = None,
) -> Any:
    from app.workflows.decision_executor import DecisionPorts

    customer_directory = getattr(customer, "directory", None) if customer else None
    vehicle_directory = getattr(vehicle, "directory", None) if vehicle else None
    crm_store = getattr(crm, "store", None) if crm else None
    scheduling_store = getattr(scheduling, "store", None) if scheduling else None

    plugin = crm_plugin
    if plugin is None and (customer_directory or vehicle_directory or crm_store):
        from app.plugins.crm.factory import crm_plugin_from_ports

        plugin = crm_plugin_from_ports(
            customer_directory=customer_directory,
            vehicle_directory=vehicle_directory,
            crm_store=crm_store,
        )

    sched_plugin = scheduling_plugin
    if sched_plugin is None and scheduling_store is not None:
        from app.plugins.scheduling.factory import scheduling_plugin_from_ports

        sched_plugin = scheduling_plugin_from_ports(scheduling_store=scheduling_store)

    return DecisionPorts(
        customer_directory=customer_directory,
        vehicle_directory=vehicle_directory,
        scheduling_store=scheduling_store,
        crm_store=crm_store,
        marketing_dispatcher=getattr(marketing, "dispatcher", None) if marketing else None,
        memory_service=memory,
        crm_plugin=plugin,
        scheduling_plugin=sched_plugin,
        conversation_plugin=conversation_plugin,
        revenue_plugin=revenue_plugin,
        advisor_plugin=advisor_plugin,
    )


def collect_decision(result: AgentResult[Any] | None) -> Decision | None:
    if result is None or result.data is None:
        return None
    data = result.data
    decision = getattr(data, "decision", None)
    if decision is not None:
        return decision
    meta = getattr(result, "metadata", None) or {}
    return meta.get("decision")


async def apply_decisions(
    *,
    shop_id: UUID,
    decisions: list[Decision],
    ports: Any,
    context: AgentContext | None = None,
) -> Any:
    from app.workflows.factory import get_workflow_runtime

    if not decisions:
        return None
    rt = get_workflow_runtime()
    return await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=decisions,
        ports=ports,
        context=context,
    )
