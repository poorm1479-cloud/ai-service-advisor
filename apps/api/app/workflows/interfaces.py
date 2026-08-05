"""Workflow Engine public interfaces (ports).

Feature modules depend on these protocols — not on each other.
Implementations remain inside each module; the coordinator resolves them.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.workflows.models import DomainEvent, WorkflowRun


class EventPublisherPort(Protocol):
    async def emit_and_run(
        self,
        *,
        shop_id: UUID,
        event_type: Any,
        payload: dict[str, Any] | None = None,
        source: str = "api",
        correlation_id: str | None = None,
    ) -> tuple[DomainEvent, list[WorkflowRun]]: ...


class LiveSourceCollectorPort(Protocol):
    """Cross-module read aggregation — owned by Workflow Engine coordinator."""

    async def collect_live_sources(self, shop_id: UUID, *, now: Any | None = None) -> dict[str, Any]: ...


class WorkflowControlPort(Protocol):
    async def pause_run(self, shop_id: UUID, run_id: UUID) -> WorkflowRun: ...

    async def resume_run(self, shop_id: UUID, run_id: UUID) -> WorkflowRun: ...

    async def retry_run(self, shop_id: UUID, run_id: UUID) -> WorkflowRun: ...

    async def workflow_history(
        self, shop_id: UUID, *, workflow_id: UUID | None = None, limit: int = 50
    ) -> list[WorkflowRun]: ...


class OrchestrationPort(Protocol):
    """Central orchestration entry — the only place modules should go for fan-out."""

    async def publish(
        self,
        *,
        shop_id: UUID,
        event_type: str,
        payload: dict[str, Any] | None = None,
        source: str = "system",
        correlation_id: str | None = None,
    ) -> tuple[DomainEvent, list[WorkflowRun]]: ...

    async def publish_and_invoke(
        self,
        *,
        shop_id: UUID,
        event_type: str,
        payload: dict[str, Any] | None = None,
        source: str = "system",
        correlation_id: str | None = None,
        invoke: Any = None,
    ) -> Any: ...

    async def collect_live_sources(self, shop_id: UUID, *, now: Any | None = None) -> dict[str, Any]: ...

    async def get_shop_analytics_overlay(self, shop_id: UUID) -> dict[str, Any]: ...

    async def apply_decisions(
        self,
        *,
        shop_id: UUID,
        decisions: list[Any],
        ports: Any = None,
        context: Any = None,
        correlation_id: str | None = None,
    ) -> Any: ...

    def escalate_human(
        self,
        *,
        shop_id: UUID,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
