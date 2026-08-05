"""DI factory for Long-Term AI Memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.memory.auto import MemoryAutoPilot
from app.memory.indexer import MemoryIndexer
from app.memory.monitoring import MemoryMonitor
from app.memory.retriever import MemoryRetriever
from app.memory.service import LongTermMemoryService
from app.memory.store import InMemoryMemoryStore, MemoryStorePort


@dataclass(slots=True)
class MemoryRuntime:
    service: LongTermMemoryService
    store: MemoryStorePort
    indexer: MemoryIndexer
    retriever: MemoryRetriever
    auto: MemoryAutoPilot
    monitor: MemoryMonitor
    manager: Any = None


_runtime: MemoryRuntime | None = None


def build_memory_runtime(*, store: MemoryStorePort | None = None) -> MemoryRuntime:
    resource_store = store or InMemoryMemoryStore()
    monitor = MemoryMonitor()
    indexer = MemoryIndexer(resource_store, monitor=monitor)
    retriever = MemoryRetriever(resource_store, monitor=monitor)
    auto = MemoryAutoPilot(retriever, indexer, monitor=monitor)
    service = LongTermMemoryService(
        resource_store,
        indexer=indexer,
        retriever=retriever,
        auto=auto,
        monitor=monitor,
    )
    from app.memory.core.manager import MemoryManager
    from app.memory.core.store import InMemoryKnowledgeBaseStore

    manager = MemoryManager(long_term=service, kb_store=InMemoryKnowledgeBaseStore())
    # Expose write helpers for DecisionExecutor / legacy MemoryDecision path
    service.write_facts = manager.write_facts  # type: ignore[method-assign]
    service.manager = manager  # type: ignore[attr-defined]
    return MemoryRuntime(
        service=service,
        store=resource_store,
        indexer=indexer,
        retriever=retriever,
        auto=auto,
        monitor=monitor,
        manager=manager,
    )


def get_memory_runtime() -> MemoryRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_memory_runtime()
    return _runtime


def reset_memory_runtime() -> None:
    global _runtime
    _runtime = None
