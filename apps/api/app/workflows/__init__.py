"""Phase 10 — Event-driven Workflow Engine (central orchestration layer)."""

from __future__ import annotations

from typing import Any

__all__ = [
    "WorkflowCoordinator",
    "WorkflowRuntime",
    "build_workflow_runtime",
    "ensure_seeded",
    "get_workflow_runtime",
    "reset_workflow_runtime",
    "EventPublisherPort",
    "LiveSourceCollectorPort",
    "OrchestrationPort",
    "WorkflowControlPort",
    "DecisionExecutor",
    "DecisionPorts",
]


def __getattr__(name: str) -> Any:
    # Lazy exports avoid circular imports with agents.decisions.bridge.
    if name == "WorkflowCoordinator":
        from app.workflows.coordinator import WorkflowCoordinator

        return WorkflowCoordinator
    if name in {
        "WorkflowRuntime",
        "build_workflow_runtime",
        "ensure_seeded",
        "get_workflow_runtime",
        "reset_workflow_runtime",
    }:
        from app.workflows import factory as _factory

        return getattr(_factory, name)
    if name in {
        "EventPublisherPort",
        "LiveSourceCollectorPort",
        "OrchestrationPort",
        "WorkflowControlPort",
    }:
        from app.workflows import interfaces as _interfaces

        return getattr(_interfaces, name)
    if name in {"DecisionExecutor", "DecisionPorts"}:
        from app.workflows import decision_executor as _de

        return getattr(_de, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
