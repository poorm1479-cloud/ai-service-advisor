"""Executive dashboard service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from app.executive.aggregator import ExecutiveAggregator
from app.executive.models import ExecutiveSnapshot
from app.executive.store import ExecutiveStorePort


class ExecutiveDashboardService:
    def __init__(self, *, store: ExecutiveStorePort, aggregator: ExecutiveAggregator) -> None:
        self._store = store
        self._aggregator = aggregator
        self._locks: dict[UUID, asyncio.Lock] = {}

    def _lock(self, shop_id: UUID) -> asyncio.Lock:
        if shop_id not in self._locks:
            self._locks[shop_id] = asyncio.Lock()
        return self._locks[shop_id]

    async def get_dashboard(
        self, shop_id: UUID, *, force: bool = False, max_age_seconds: int = 5
    ) -> ExecutiveSnapshot:
        """Realtime snapshot — refresh if stale or forced."""
        async with self._lock(shop_id):
            hydrate = getattr(self._store, "ensure_hydrated", None)
            if callable(hydrate):
                await hydrate(shop_id)
            existing = self._store.get_snapshot(shop_id)
            now = datetime.now(timezone.utc)
            if (
                not force
                and existing is not None
                and (now - existing.generated_at).total_seconds() <= max_age_seconds
            ):
                return existing
            return await self._aggregator.refresh(shop_id, now=now)

    async def bump_live(
        self,
        shop_id: UUID,
        **fields: object,
    ) -> ExecutiveSnapshot:
        """Apply realtime counter updates (webhooks / domain events)."""
        live = self._store.get_live(shop_id)
        for key, value in fields.items():
            if hasattr(live, key) and value is not None:
                setattr(live, key, value)
        self._store.save_live(live)
        return await self.get_dashboard(shop_id, force=True)
