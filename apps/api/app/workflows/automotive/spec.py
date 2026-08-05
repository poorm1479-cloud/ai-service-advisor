"""Shared builders for automotive business workflow definitions.

These definitions run on the existing Workflow Engine + ActionExecutor.
They document required Capabilities / AI Decisions in action config metadata
without modifying Plugins or rewriting the engine.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.workflows.enums import (
    ActionType,
    ConditionOperator,
    DomainEventType,
    WorkflowStatus,
)
from app.workflows.models import (
    RetryPolicy,
    WorkflowAction,
    WorkflowCondition,
    WorkflowDefinition,
)


def meta(
    *,
    workflow_id: str,
    purpose: str,
    trigger: str,
    capabilities: list[str],
    ai_decisions: list[str],
    events_published: list[str],
    failure_handling: str,
    human_escalation: str,
) -> dict[str, Any]:
    return {
        "workflow_id": workflow_id,
        "purpose": purpose,
        "trigger_event": trigger,
        "required_capabilities": capabilities,
        "ai_decisions": ai_decisions,
        "events_published": events_published,
        "failure_handling": failure_handling,
        "human_escalation": human_escalation,
    }


def build_definition(
    *,
    workflow_id: UUID,
    name: str,
    description: str,
    trigger: DomainEventType,
    actions: list[WorkflowAction],
    conditions: list[WorkflowCondition] | None = None,
    tags: list[str] | None = None,
    retry: RetryPolicy | None = None,
    spec: dict[str, Any] | None = None,
) -> WorkflowDefinition:
    # Embed catalog metadata on the first LOG / SET_CONTEXT step when present.
    if spec:
        for action in actions:
            if action.type in (ActionType.LOG, ActionType.SET_CONTEXT):
                action.config = {**action.config, "automotive_spec": spec}
                break
    return WorkflowDefinition(
        id=workflow_id,
        shop_id=None,
        name=name,
        description=description,
        trigger=trigger,
        conditions=list(conditions or []),
        actions=sorted(actions, key=lambda a: a.order),
        retry=retry
        or RetryPolicy(max_attempts=3, backoff_ms=500, backoff_multiplier=2.0),
        status=WorkflowStatus.ACTIVE,
        tags=["automotive", *(tags or [])],
    )


def cond(field: str, operator: ConditionOperator, value: Any = None) -> WorkflowCondition:
    return WorkflowCondition(field=field, operator=operator, value=value)


def action(
    type: ActionType,
    name: str,
    order: int,
    *,
    config: dict[str, Any] | None = None,
    continue_on_error: bool = False,
    compensate: dict[str, Any] | None = None,
) -> WorkflowAction:
    return WorkflowAction(
        type=type,
        name=name,
        order=order,
        config=dict(config or {}),
        continue_on_error=continue_on_error,
        compensate=dict(compensate or {}),
    )
