"""Workflow domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.workflows.enums import (
    ActionType,
    ConditionOperator,
    DomainEventType,
    RetryState,
    RunStatus,
    StepStatus,
    WorkflowStatus,
)


@dataclass(slots=True)
class WorkflowCondition:
    field: str
    operator: ConditionOperator = ConditionOperator.EQ
    value: Any = None


@dataclass(slots=True)
class WorkflowAction:
    id: UUID = field(default_factory=uuid4)
    type: ActionType = ActionType.LOG
    name: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    order: int = 0
    continue_on_error: bool = False
    # Compensation config used during rollback
    compensate: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_ms: int = 1000
    backoff_multiplier: float = 2.0
    max_backoff_ms: int = 60_000


@dataclass(slots=True)
class WorkflowDefinition:
    id: UUID
    shop_id: UUID | None  # None = global template
    name: str
    description: str = ""
    trigger: DomainEventType = DomainEventType.APPOINTMENT_BOOKED
    conditions: list[WorkflowCondition] = field(default_factory=list)
    actions: list[WorkflowAction] = field(default_factory=list)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    version: int = 1
    tags: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class DomainEvent:
    event_type: DomainEventType
    shop_id: UUID
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: UUID = field(default_factory=uuid4)
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    source: str = "system"
    occurred_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StepLog:
    id: UUID = field(default_factory=uuid4)
    action_id: UUID | None = None
    action_type: str = ""
    action_name: str = ""
    status: StepStatus = StepStatus.PENDING
    attempt: int = 0
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    compensation: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowRun:
    id: UUID
    shop_id: UUID
    workflow_id: UUID
    workflow_name: str
    workflow_version: int
    trigger_event_id: UUID
    trigger_event_type: DomainEventType
    correlation_id: str
    status: RunStatus = RunStatus.PENDING
    context: dict[str, Any] = field(default_factory=dict)
    steps: list[StepLog] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    rolled_back_at: datetime | None = None


@dataclass(slots=True)
class RetryItem:
    id: UUID
    shop_id: UUID
    run_id: UUID
    step_id: UUID
    attempt: int
    max_attempts: int
    next_attempt_at: datetime
    state: RetryState = RetryState.PENDING
    last_error: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class DebuggerFrame:
    """Snapshot used by the workflow debugger UI."""

    run_id: UUID
    step_index: int
    status: RunStatus
    context: dict[str, Any]
    current_step: StepLog | None
    logs: list[str]
    event: DomainEvent | None = None
