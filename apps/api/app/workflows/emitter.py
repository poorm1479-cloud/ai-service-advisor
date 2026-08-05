"""Emit domain events into the workflow engine from other modules."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.workflows.enums import DomainEventType
from app.workflows.models import DomainEvent, WorkflowRun


async def emit_domain_event(
    *,
    shop_id: UUID,
    event_type: DomainEventType | str,
    payload: dict[str, Any] | None = None,
    source: str = "system",
    correlation_id: str | None = None,
) -> tuple[DomainEvent, list[WorkflowRun]]:
    """Lazy-import runtime to avoid circular imports at module load.

    All cross-module domain events enter through the Workflow coordinator.
    """
    from app.workflows.factory import ensure_seeded, get_workflow_runtime

    rt = get_workflow_runtime()
    await ensure_seeded(rt)
    return await rt.coordinator.publish(
        shop_id=shop_id,
        event_type=event_type,
        payload=payload,
        source=source,
        correlation_id=correlation_id,
    )
