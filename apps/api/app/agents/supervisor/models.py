"""Supervisor agent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentStageOutput:
    agent: str
    success: bool
    data: Any = None
    error: str | None = None
    escalate: bool = False
    escalation_reason: str | None = None


@dataclass(slots=True)
class SupervisorReviewRequest:
    stages: list[AgentStageOutput] = field(default_factory=list)
    intent: str | None = None
    is_emergency: bool = False
    is_complaint: bool = False


@dataclass(slots=True)
class SupervisorDecision:
    status: str
    escalate: bool
    escalation_reason: str | None = None
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    owner_summary: str = ""
    action_items: list[str] = field(default_factory=list)
    agent_outputs: dict[str, Any] = field(default_factory=dict)
