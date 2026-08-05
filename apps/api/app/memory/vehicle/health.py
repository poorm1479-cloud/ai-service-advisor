"""Vehicle health memory."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.memory.enums import MemoryCategory, MemorySource, MemoryType
from app.memory.models import MemoryRecord, RememberRequest
from app.memory.service import LongTermMemoryService


class VehicleHealthService:
    def __init__(self, ltm: LongTermMemoryService) -> None:
        self._ltm = ltm

    async def get(self, shop_id: UUID, vehicle_id: UUID) -> dict[str, Any]:
        records = self._ltm.list_memories(
            shop_id,
            vehicle_id=vehicle_id,
            category=MemoryCategory.VEHICLE_HEALTH,
            limit=20,
        )
        if not records:
            return {
                "vehicle_id": str(vehicle_id),
                "status": "unknown",
                "score": None,
                "notes": [],
            }
        latest = records[0]
        health = dict(latest.metadata.get("health") or {})
        return {
            "vehicle_id": str(vehicle_id),
            "status": health.get("status", "tracked"),
            "score": health.get("score"),
            "notes": [r.content for r in records[:10]],
            "latest": latest.content,
            "metadata": health,
        }

    async def update(
        self, shop_id: UUID, vehicle_id: UUID, health: dict[str, Any]
    ) -> MemoryRecord:
        status = health.get("status", "updated")
        score = health.get("score")
        content = health.get("summary") or (
            f"Vehicle health {status}" + (f" score={score}" if score is not None else "")
        )
        return self._ltm.remember(
            RememberRequest(
                shop_id=shop_id,
                vehicle_id=vehicle_id,
                customer_id=_as_uuid(health.get("customer_id")),
                content=str(content),
                summary=str(health.get("rationale") or "Vehicle health update"),
                memory_type=MemoryType.VEHICLE,
                category=MemoryCategory.VEHICLE_HEALTH,
                importance=float(health.get("importance") or 0.8),
                tags=["vehicle_health", str(status)],
                metadata={"health": health},
                source=MemorySource.WORKFLOW,
            )
        )


def _as_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None
