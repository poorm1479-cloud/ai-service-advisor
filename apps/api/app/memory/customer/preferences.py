"""Customer preference / profile memory."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.memory.enums import MemoryCategory, MemorySource, MemoryType
from app.memory.models import MemoryRecord, RememberRequest
from app.memory.service import LongTermMemoryService


class CustomerPreferenceService:
    def __init__(self, ltm: LongTermMemoryService) -> None:
        self._ltm = ltm

    async def get(self, shop_id: UUID, customer_id: UUID) -> dict[str, Any]:
        records = self._ltm.list_memories(
            shop_id,
            customer_id=customer_id,
            category=MemoryCategory.CUSTOMER_PREFERENCES,
            limit=50,
        )
        prefs: dict[str, Any] = {}
        for rec in records:
            key = str(rec.metadata.get("key") or (rec.tags[0] if rec.tags else str(rec.id)))
            prefs[key] = rec.metadata.get("value", rec.content)
        style_records = self._ltm.list_memories(
            shop_id,
            customer_id=customer_id,
            category=MemoryCategory.COMMUNICATION_STYLE,
            limit=10,
        )
        style: dict[str, Any] = {}
        for rec in style_records:
            style.update(rec.metadata if rec.metadata else {"note": rec.content})
        return {
            "customer_id": str(customer_id),
            "preferences": prefs,
            "communication_style": style,
        }

    async def update_profile(
        self, shop_id: UUID, customer_id: UUID, patch: dict[str, Any]
    ) -> MemoryRecord:
        content = patch.get("summary") or json.dumps(patch, default=str)
        return self._ltm.remember(
            RememberRequest(
                shop_id=shop_id,
                customer_id=customer_id,
                content=str(content),
                summary=str(patch.get("rationale") or "Customer profile update"),
                memory_type=MemoryType.CUSTOMER,
                category=MemoryCategory.CUSTOMER_PREFERENCES
                if "preference" in patch or "preferences" in patch
                else MemoryCategory.CUSTOMER_HISTORY,
                importance=float(patch.get("importance") or 0.7),
                tags=["customer_profile", *(patch.get("tags") or [])],
                metadata={"patch": patch},
                source=MemorySource.WORKFLOW,
            )
        )
