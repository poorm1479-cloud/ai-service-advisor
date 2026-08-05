"""Retention / campaign insight store (Phase 20) — suggestions only, no sends."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RetentionInsightStorePort(Protocol):
    async def record(
        self,
        shop_id: UUID,
        *,
        kind: str,
        customer_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def list_for_shop(
        self, shop_id: UUID, *, kind: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]: ...


class InMemoryRetentionInsightStore:
    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    async def record(
        self,
        shop_id: UUID,
        *,
        kind: str,
        customer_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = {
            "id": str(uuid4()),
            "shop_id": str(shop_id),
            "customer_id": str(customer_id) if customer_id else None,
            "kind": kind,
            "payload": dict(payload or {}),
            "created_at": _utcnow().isoformat(),
        }
        self._rows.append(row)
        return row

    async def list_for_shop(
        self, shop_id: UUID, *, kind: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        items = [r for r in self._rows if r["shop_id"] == str(shop_id)]
        if kind:
            items = [r for r in items if r["kind"] == kind]
        return list(reversed(items))[:limit]
