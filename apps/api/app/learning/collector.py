"""Collect decision outcomes from shop interactions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.learning.models.decision_result import DecisionResultRecord, OutcomeKind
from app.learning.store import LearningStorePort


class LearningCollector:
    def __init__(self, store: LearningStorePort) -> None:
        self._store = store

    async def collect_decision_result(
        self,
        shop_id: UUID,
        *,
        decision_kind: str,
        outcome_kind: str | OutcomeKind,
        success: bool,
        customer_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
        correlation_id: str | None = None,
        score: float | None = None,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DecisionResultRecord:
        record = DecisionResultRecord.create(
            shop_id=shop_id,
            decision_kind=decision_kind,
            outcome_kind=outcome_kind,
            success=success,
            customer_id=customer_id,
            workflow_run_id=workflow_run_id,
            correlation_id=correlation_id,
            score=float(score if score is not None else (1.0 if success else 0.0)),
            notes=notes,
            metadata=metadata,
        )
        return await self._store.save_result(record)

    async def collect_from_workflow_run(
        self,
        shop_id: UUID,
        *,
        run: Any,
        decision_kind: str = "workflow",
    ) -> DecisionResultRecord:
        status_val = getattr(getattr(run, "status", None), "value", str(getattr(run, "status", "")))
        success = status_val in {"completed", "success", "COMPLETED"}
        return await self.collect_decision_result(
            shop_id,
            decision_kind=decision_kind,
            outcome_kind=OutcomeKind.WORKFLOW,
            success=success,
            workflow_run_id=getattr(run, "id", None),
            correlation_id=getattr(run, "correlation_id", None),
            notes=f"Workflow run status={status_val}",
            metadata={"workflow_name": getattr(run, "workflow_name", None)},
        )
