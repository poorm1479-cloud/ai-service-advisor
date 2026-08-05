"""Retry queue for failed workflow steps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.workflows.enums import RetryState
from app.workflows.models import RetryItem, RetryPolicy, WorkflowRun
from app.workflows.store import WorkflowStorePort


class RetryQueue:
    def __init__(self, store: WorkflowStorePort) -> None:
        self._store = store

    async def schedule(
        self,
        *,
        shop_id: UUID,
        run: WorkflowRun,
        step_id: UUID,
        attempt: int,
        policy: RetryPolicy,
        error: str | None,
    ) -> RetryItem | None:
        if attempt >= policy.max_attempts:
            return None
        delay = min(
            int(policy.backoff_ms * (policy.backoff_multiplier ** max(attempt - 1, 0))),
            policy.max_backoff_ms,
        )
        item = RetryItem(
            id=uuid4(),
            shop_id=shop_id,
            run_id=run.id,
            step_id=step_id,
            attempt=attempt + 1,
            max_attempts=policy.max_attempts,
            next_attempt_at=datetime.now(timezone.utc) + timedelta(milliseconds=delay),
            state=RetryState.PENDING,
            last_error=error,
        )
        return await self._store.enqueue_retry(item)

    async def due(self, *, now: datetime | None = None, limit: int = 50) -> list[RetryItem]:
        return await self._store.list_due_retries(
            now=now or datetime.now(timezone.utc), limit=limit
        )

    async def mark(self, item: RetryItem, state: RetryState) -> RetryItem:
        item.state = state
        return await self._store.save_retry(item)
