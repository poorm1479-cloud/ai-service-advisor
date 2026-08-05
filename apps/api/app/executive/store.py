"""In-memory executive snapshot store (per shop)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from app.executive.models import ExecutiveSnapshot, ShopLiveState


class ExecutiveStorePort(Protocol):
    def get_live(self, shop_id: UUID) -> ShopLiveState: ...

    def save_live(self, state: ShopLiveState) -> ShopLiveState: ...

    def get_snapshot(self, shop_id: UUID) -> ExecutiveSnapshot | None: ...

    def save_snapshot(self, snapshot: ExecutiveSnapshot) -> ExecutiveSnapshot: ...


class InMemoryExecutiveStore:
    def __init__(self) -> None:
        self.live: dict[UUID, ShopLiveState] = {}
        self.snapshots: dict[UUID, ExecutiveSnapshot] = {}

    def get_live(self, shop_id: UUID) -> ShopLiveState:
        if shop_id not in self.live:
            self.live[shop_id] = ShopLiveState(
                shop_id=shop_id, updated_at=datetime.now(timezone.utc)
            )
        return self.live[shop_id]

    def save_live(self, state: ShopLiveState) -> ShopLiveState:
        state.updated_at = datetime.now(timezone.utc)
        state.version += 1
        self.live[state.shop_id] = state
        return state

    def get_snapshot(self, shop_id: UUID) -> ExecutiveSnapshot | None:
        return self.snapshots.get(shop_id)

    def save_snapshot(self, snapshot: ExecutiveSnapshot) -> ExecutiveSnapshot:
        self.snapshots[snapshot.shop_id] = snapshot
        return snapshot
