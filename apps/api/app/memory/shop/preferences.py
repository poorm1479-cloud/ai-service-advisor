"""Shop preference memory."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.memory.core.store import KnowledgeBaseStorePort
from app.memory.enums import MemoryCategory, MemorySource, MemoryType
from app.memory.models import MemoryRecord, RememberRequest
from app.memory.service import LongTermMemoryService


class ShopPreferenceService:
    def __init__(self, kb: KnowledgeBaseStorePort, ltm: LongTermMemoryService) -> None:
        self._kb = kb
        self._ltm = ltm

    async def get_all(self, shop_id: UUID) -> dict[str, Any]:
        profile = await self._kb.get_shop_profile(shop_id)
        # Merge durable memory preference snippets
        records = self._ltm.list_memories(
            shop_id,
            memory_type=MemoryType.SHOP,
            category=MemoryCategory.SHOP_PREFERENCES,
            limit=50,
        )
        prefs = dict(profile.preferences)
        for rec in records:
            key = str(rec.metadata.get("key") or rec.tags[0] if rec.tags else rec.id)
            prefs[key] = rec.metadata.get("value", rec.content)
        return {
            "shop_id": str(shop_id),
            "preferences": prefs,
            "profile": profile.to_dict(),
        }

    async def save(
        self, shop_id: UUID, key: str, value: Any, *, rationale: str = ""
    ) -> MemoryRecord:
        profile = await self._kb.get_shop_profile(shop_id)
        profile.preferences[key] = value
        await self._kb.save_shop_profile(profile)
        return self._ltm.remember(
            RememberRequest(
                shop_id=shop_id,
                content=f"Shop preference {key}={value}",
                summary=rationale or None,
                memory_type=MemoryType.SHOP,
                category=MemoryCategory.SHOP_PREFERENCES,
                importance=0.75,
                tags=["shop_preference", key],
                metadata={"key": key, "value": value, "rationale": rationale},
                source=MemorySource.WORKFLOW,
            )
        )

    async def apply_patch(
        self, shop_id: UUID, preferences: dict[str, Any], *, rationale: str = ""
    ) -> list[MemoryRecord]:
        out: list[MemoryRecord] = []
        for key, value in preferences.items():
            out.append(await self.save(shop_id, str(key), value, rationale=rationale))
        return out
