"""Long-term memory service API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.memory.auto import MemoryAutoPilot
from app.memory.enums import MemoryCategory, MemorySource, MemoryType
from app.memory.indexer import MemoryIndexer
from app.memory.models import MemoryBundle, MemoryQuery, MemoryRecord, RememberRequest
from app.memory.monitoring import MemoryMonitor
from app.memory.retriever import MemoryRetriever
from app.memory.store import MemoryStorePort


class LongTermMemoryService:
    def __init__(
        self,
        store: MemoryStorePort,
        *,
        indexer: MemoryIndexer,
        retriever: MemoryRetriever,
        auto: MemoryAutoPilot,
        monitor: MemoryMonitor,
    ) -> None:
        self._store = store
        self.indexer = indexer
        self.retriever = retriever
        self.auto = auto
        self.monitor = monitor

    def remember(self, request: RememberRequest) -> MemoryRecord:
        return self.indexer.remember(request)

    def retrieve(self, query: MemoryQuery) -> MemoryBundle:
        return self.retriever.build_bundle(query)

    def auto_load(
        self,
        shop_id: UUID,
        *,
        text: str | None = None,
        customer_id: UUID | None = None,
        vehicle_id: UUID | None = None,
    ) -> MemoryBundle:
        return self.auto.load(
            shop_id,
            text=text,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
        )

    def auto_capture(
        self,
        *,
        shop_id: UUID,
        customer_id: UUID | None,
        vehicle_id: UUID | None,
        channel: str | None,
        message_text: str | None,
        stages: dict[str, Any],
        escalate: bool = False,
    ) -> list[MemoryRecord]:
        return self.auto.capture_from_pipeline(
            shop_id=shop_id,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            channel=channel,
            message_text=message_text,
            stages=stages,
            escalate=escalate,
        )

    def get(self, shop_id: UUID, memory_id: UUID) -> MemoryRecord | None:
        return self._store.get(shop_id, memory_id)

    def list_memories(
        self,
        shop_id: UUID,
        *,
        customer_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        memory_type: MemoryType | None = None,
        category: MemoryCategory | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        return self._store.list(
            shop_id,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            memory_type=memory_type,
            category=category,
            limit=limit,
        )

    def delete(self, shop_id: UUID, memory_id: UUID) -> bool:
        ok = self._store.delete(shop_id, memory_id)
        if ok:
            self.monitor.record_delete()
        return ok

    def seed_customer_profile(
        self,
        shop_id: UUID,
        customer_id: UUID,
        *,
        preferences: list[str] | None = None,
        communication_style: dict[str, Any] | None = None,
        vehicle_notes: list[str] | None = None,
        declined_estimates: list[str] | None = None,
        appointment_behavior: list[str] | None = None,
    ) -> list[MemoryRecord]:
        out: list[MemoryRecord] = []
        for pref in preferences or []:
            out.append(
                self.remember(
                    RememberRequest(
                        shop_id=shop_id,
                        content=pref,
                        memory_type=MemoryType.CUSTOMER,
                        category=MemoryCategory.CUSTOMER_PREFERENCES,
                        customer_id=customer_id,
                        importance=0.8,
                        source=MemorySource.MANUAL,
                        metadata={"prefs": {"notes": [pref]}},
                    )
                )
            )
        if communication_style:
            tone = communication_style.get("tone", "friendly")
            out.append(
                self.remember(
                    RememberRequest(
                        shop_id=shop_id,
                        content=f"Communication style: {tone}",
                        memory_type=MemoryType.CUSTOMER,
                        category=MemoryCategory.COMMUNICATION_STYLE,
                        customer_id=customer_id,
                        importance=0.85,
                        source=MemorySource.MANUAL,
                        metadata={"style": communication_style},
                    )
                )
            )
        for note in vehicle_notes or []:
            out.append(
                self.remember(
                    RememberRequest(
                        shop_id=shop_id,
                        content=note,
                        memory_type=MemoryType.CUSTOMER,
                        category=MemoryCategory.VEHICLE_HISTORY,
                        customer_id=customer_id,
                        importance=0.7,
                        source=MemorySource.MANUAL,
                    )
                )
            )
        for note in declined_estimates or []:
            out.append(
                self.remember(
                    RememberRequest(
                        shop_id=shop_id,
                        content=note,
                        memory_type=MemoryType.CUSTOMER,
                        category=MemoryCategory.DECLINED_ESTIMATES,
                        customer_id=customer_id,
                        importance=0.9,
                        source=MemorySource.MANUAL,
                    )
                )
            )
        for note in appointment_behavior or []:
            out.append(
                self.remember(
                    RememberRequest(
                        shop_id=shop_id,
                        content=note,
                        memory_type=MemoryType.CUSTOMER,
                        category=MemoryCategory.APPOINTMENT_BEHAVIOR,
                        customer_id=customer_id,
                        importance=0.75,
                        source=MemorySource.MANUAL,
                    )
                )
            )
        out.append(
            self.remember(
                RememberRequest(
                    shop_id=shop_id,
                    content="Shop policy: always confirm appointment time and vehicle before booking.",
                    memory_type=MemoryType.BUSINESS,
                    category=MemoryCategory.GENERAL,
                    importance=0.6,
                    source=MemorySource.SYSTEM,
                    tags=["policy"],
                )
            )
        )
        return out

    def metrics(self) -> dict[str, object]:
        return self.monitor.snapshot()

    def categories(self) -> list[str]:
        return [c.value for c in MemoryCategory]

    def types(self) -> list[str]:
        return [t.value for t in MemoryType]
