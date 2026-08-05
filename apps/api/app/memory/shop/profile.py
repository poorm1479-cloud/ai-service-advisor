"""Shop profile memory."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.memory.core.store import KnowledgeBaseStorePort, ShopProfileRecord
from app.memory.enums import MemoryCategory, MemorySource, MemoryType
from app.memory.models import MemoryRecord, RememberRequest
from app.memory.service import LongTermMemoryService


class ShopProfileService:
    def __init__(self, kb: KnowledgeBaseStorePort, ltm: LongTermMemoryService) -> None:
        self._kb = kb
        self._ltm = ltm

    async def get(self, shop_id: UUID) -> dict[str, Any]:
        profile = await self._kb.get_shop_profile(shop_id)
        return profile.to_dict()

    async def update(self, shop_id: UUID, patch: dict[str, Any]) -> dict[str, Any]:
        profile = await self._kb.get_shop_profile(shop_id)
        if "display_name" in patch:
            profile.display_name = str(patch["display_name"] or "")
        if "timezone" in patch:
            profile.timezone = str(patch["timezone"] or profile.timezone)
        if "specialties" in patch:
            profile.specialties = list(patch["specialties"] or [])
        if "hours" in patch and isinstance(patch["hours"], dict):
            profile.hours = dict(patch["hours"])
        if "metadata" in patch and isinstance(patch["metadata"], dict):
            profile.metadata.update(patch["metadata"])
        saved = await self._kb.save_shop_profile(profile)
        self._ltm.remember(
            RememberRequest(
                shop_id=shop_id,
                content=f"Shop profile updated: {saved.display_name or shop_id}",
                memory_type=MemoryType.SHOP,
                category=MemoryCategory.SHOP_PROFILE,
                importance=0.8,
                tags=["shop_profile"],
                metadata=saved.to_dict(),
                source=MemorySource.WORKFLOW,
            )
        )
        return saved.to_dict()
