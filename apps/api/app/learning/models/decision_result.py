"""Learning domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutcomeKind(StrEnum):
    CONVERSATION = "conversation"
    APPOINTMENT_CONVERSION = "appointment_conversion"
    REPAIR_APPROVAL = "repair_approval"
    REVENUE = "revenue"
    CUSTOMER_RESPONSE = "customer_response"
    WORKFLOW = "workflow"
    STAFF_FEEDBACK = "staff_feedback"


class OutcomeStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class DecisionResultRecord:
    """Captured outcome of a prior AI Decision."""

    id: UUID
    shop_id: UUID
    decision_kind: str
    outcome_kind: OutcomeKind
    status: OutcomeStatus
    success: bool
    customer_id: UUID | None = None
    workflow_run_id: UUID | None = None
    correlation_id: str | None = None
    score: float = 0.0
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        *,
        shop_id: UUID,
        decision_kind: str,
        outcome_kind: OutcomeKind | str,
        success: bool,
        status: OutcomeStatus | str | None = None,
        customer_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
        correlation_id: str | None = None,
        score: float = 0.0,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DecisionResultRecord:
        okind = (
            outcome_kind
            if isinstance(outcome_kind, OutcomeKind)
            else OutcomeKind(str(outcome_kind))
        )
        if status is None:
            st = OutcomeStatus.SUCCESS if success else OutcomeStatus.FAILURE
        else:
            st = status if isinstance(status, OutcomeStatus) else OutcomeStatus(str(status))
        return cls(
            id=uuid4(),
            shop_id=shop_id,
            decision_kind=decision_kind,
            outcome_kind=okind,
            status=st,
            success=success,
            customer_id=customer_id,
            workflow_run_id=workflow_run_id,
            correlation_id=correlation_id,
            score=float(score),
            notes=notes,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "shop_id": str(self.shop_id),
            "decision_kind": self.decision_kind,
            "outcome_kind": self.outcome_kind.value,
            "status": self.status.value,
            "success": self.success,
            "customer_id": str(self.customer_id) if self.customer_id else None,
            "workflow_run_id": str(self.workflow_run_id) if self.workflow_run_id else None,
            "correlation_id": self.correlation_id,
            "score": self.score,
            "notes": self.notes,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class SuccessPattern:
    id: UUID
    shop_id: UUID
    pattern_key: str
    description: str
    support_count: int = 0
    success_rate: float = 0.0
    decision_kinds: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "shop_id": str(self.shop_id),
            "pattern_key": self.pattern_key,
            "description": self.description,
            "support_count": self.support_count,
            "success_rate": self.success_rate,
            "decision_kinds": list(self.decision_kinds),
            "signals": dict(self.signals),
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class LearningFeedback:
    id: UUID
    shop_id: UUID
    source: str  # customer | staff | workflow
    rating: float | None = None
    comment: str = ""
    customer_id: UUID | None = None
    staff_user_id: UUID | None = None
    decision_kind: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "shop_id": str(self.shop_id),
            "source": self.source,
            "rating": self.rating,
            "comment": self.comment,
            "customer_id": str(self.customer_id) if self.customer_id else None,
            "staff_user_id": str(self.staff_user_id) if self.staff_user_id else None,
            "decision_kind": self.decision_kind,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class LearningInsight:
    shop_id: UUID
    title: str
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "shop_id": str(self.shop_id),
            "title": self.title,
            "summary": self.summary,
            "metrics": dict(self.metrics),
            "recommendations": list(self.recommendations),
            "confidence": self.confidence,
            "ai_actions_allowed": False,
        }
