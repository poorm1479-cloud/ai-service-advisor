"""Workflow outcome feedback — reads run status, never mutates Workflow Engine."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.learning.models.decision_result import LearningFeedback, OutcomeKind
from app.learning.store import LearningStorePort


class WorkflowFeedbackService:
    def __init__(self, store: LearningStorePort, collector: Any) -> None:
        self._store = store
        self._collector = collector

    async def ingest_run(
        self,
        shop_id: UUID,
        *,
        run: Any | None = None,
        success: bool | None = None,
        workflow_run_id: UUID | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        if run is not None:
            record = await self._collector.collect_from_workflow_run(shop_id, run=run)
        else:
            ok = bool(success)
            record = await self._collector.collect_decision_result(
                shop_id,
                decision_kind="workflow",
                outcome_kind=OutcomeKind.WORKFLOW,
                success=ok,
                workflow_run_id=workflow_run_id,
                notes=notes or ("workflow success" if ok else "workflow failure"),
            )
        fb = LearningFeedback(
            id=uuid4(),
            shop_id=shop_id,
            source="workflow",
            rating=1.0 if record.success else 0.0,
            comment=record.notes,
            decision_kind=record.decision_kind,
            metadata={"workflow_run_id": str(record.workflow_run_id) if record.workflow_run_id else None},
        )
        await self._store.save_feedback(fb)
        return {
            "feedback": fb.to_dict(),
            "result": record.to_dict(),
            "workflow_modified": False,
            "ai_actions_allowed": False,
        }
