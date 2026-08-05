"""Memory Plugin — Knowledge Base & Shop Memory capabilities.

AI may invoke *read* capabilities. Write capabilities are for Workflow
DecisionExecutor only (via Decision Objects).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.memory.core.manager import MemoryManager
from app.memory.enums import MemoryCategory, MemorySource, MemoryType
from app.memory.models import MemoryQuery, RememberRequest
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext


class MemoryPlugin:
    """IPlugin for Shop / Customer / Vehicle / Knowledge memory."""

    def __init__(self, *, manager: MemoryManager | None = None) -> None:
        self._manager = manager
        self._initialized = False

    def _mgr(self) -> MemoryManager:
        if self._manager is None:
            from app.memory.factory import get_memory_runtime

            self._manager = get_memory_runtime().manager
        return self._manager

    def plugin_id(self) -> str:
        return "memory"

    def plugin_name(self) -> str:
        return "AI Knowledge Base & Shop Memory"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Personalized shop/customer/vehicle memory and business knowledge. "
            "AI reads; Workflow applies write Decisions."
        )

    def supported_capabilities(self) -> list[str]:
        return [
            Capability.SAVE_MEMORY.value,
            Capability.SEARCH_MEMORY.value,
            Capability.GET_CUSTOMER_HISTORY.value,
            Capability.GET_VEHICLE_HISTORY.value,
            Capability.GET_SHOP_PREFERENCE.value,
            Capability.RETRIEVE_KNOWLEDGE.value,
            Capability.UPDATE_CUSTOMER_PROFILE.value,
            Capability.UPDATE_VEHICLE_HEALTH.value,
        ]

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
            "capabilities": len(self.supported_capabilities()),
            "ai_write_allowed": False,
        }

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        if context is not None:
            for key, value in context.to_kwargs().items():
                if key.startswith("_"):
                    continue
                kwargs.setdefault(key, value)

        shop_id: UUID | None = kwargs.get("shop_id") or (context.shop_id if context else None)
        if shop_id is None:
            raise ValueError("shop_id is required for memory capabilities")

        mgr = self._mgr()

        if capability == Capability.SAVE_MEMORY:
            return await self._save(mgr, shop_id, kwargs)
        if capability == Capability.SEARCH_MEMORY:
            return await self._search(mgr, shop_id, kwargs)
        if capability == Capability.GET_CUSTOMER_HISTORY:
            customer_id = kwargs.get("customer_id") or (context.customer_id if context else None)
            if customer_id is None:
                raise ValueError("customer_id is required for GetCustomerHistory")
            records = await mgr.get_customer_history(
                shop_id, customer_id, limit=int(kwargs.get("limit") or 50)
            )
            return {"records": [_record_dict(r) for r in records]}
        if capability == Capability.GET_VEHICLE_HISTORY:
            vehicle_id = kwargs.get("vehicle_id") or (context.vehicle_id if context else None)
            if vehicle_id is None:
                raise ValueError("vehicle_id is required for GetVehicleHistory")
            records = await mgr.get_vehicle_history(
                shop_id, vehicle_id, limit=int(kwargs.get("limit") or 50)
            )
            return {"records": [_record_dict(r) for r in records]}
        if capability == Capability.GET_SHOP_PREFERENCE:
            return await mgr.get_shop_preference(shop_id)
        if capability == Capability.RETRIEVE_KNOWLEDGE:
            docs = await mgr.retrieve_knowledge(
                shop_id,
                query=kwargs.get("query") or kwargs.get("text"),
                limit=int(kwargs.get("limit") or 12),
            )
            return {"documents": docs}
        if capability == Capability.UPDATE_CUSTOMER_PROFILE:
            customer_id = kwargs.get("customer_id")
            if customer_id is None:
                raise ValueError("customer_id is required for UpdateCustomerProfile")
            patch = dict(kwargs.get("patch") or kwargs.get("profile") or {})
            record = await mgr.update_customer_profile(shop_id, customer_id, patch)
            return _record_dict(record)
        if capability == Capability.UPDATE_VEHICLE_HEALTH:
            vehicle_id = kwargs.get("vehicle_id")
            if vehicle_id is None:
                raise ValueError("vehicle_id is required for UpdateVehicleHealth")
            health = dict(kwargs.get("health") or kwargs.get("patch") or {})
            record = await mgr.update_vehicle_health(shop_id, vehicle_id, health)
            return _record_dict(record)

        raise ValueError(f"Unknown memory capability: {capability}")

    async def _save(
        self, mgr: MemoryManager, shop_id: UUID, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        content = str(kwargs.get("content") or "").strip()
        if not content:
            raise ValueError("content is required for SaveMemory")
        mem_type = kwargs.get("memory_type") or MemoryType.SEMANTIC.value
        category = kwargs.get("category") or MemoryCategory.GENERAL.value
        try:
            mt = MemoryType(str(mem_type))
        except ValueError:
            mt = MemoryType.SEMANTIC
        try:
            cat = MemoryCategory(str(category))
        except ValueError:
            cat = MemoryCategory.GENERAL
        record = await mgr.save_memory(
            RememberRequest(
                shop_id=shop_id,
                content=content,
                summary=kwargs.get("summary"),
                memory_type=mt,
                category=cat,
                customer_id=kwargs.get("customer_id"),
                vehicle_id=kwargs.get("vehicle_id"),
                conversation_id=kwargs.get("conversation_id"),
                importance=float(kwargs.get("importance") or 0.6),
                confidence=float(kwargs.get("confidence") or 1.0),
                tags=list(kwargs.get("tags") or []),
                metadata=dict(kwargs.get("metadata") or {}),
                source=MemorySource(str(kwargs.get("source") or MemorySource.WORKFLOW.value)),
            )
        )
        return _record_dict(record)

    async def _search(
        self, mgr: MemoryManager, shop_id: UUID, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        bundle = await mgr.search_memory(
            MemoryQuery(
                shop_id=shop_id,
                text=kwargs.get("query") or kwargs.get("text"),
                customer_id=kwargs.get("customer_id"),
                vehicle_id=kwargs.get("vehicle_id"),
                limit=int(kwargs.get("limit") or 12),
            )
        )
        return bundle.to_dict()


def _record_dict(record: Any) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "shop_id": str(record.shop_id),
        "memory_type": record.memory_type.value,
        "category": record.category.value,
        "content": record.content,
        "summary": record.summary,
        "customer_id": str(record.customer_id) if record.customer_id else None,
        "vehicle_id": str(record.vehicle_id) if record.vehicle_id else None,
        "importance": record.importance,
        "tags": list(record.tags),
        "metadata": dict(record.metadata),
    }
