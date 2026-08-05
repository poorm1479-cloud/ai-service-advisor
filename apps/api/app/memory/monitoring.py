"""Memory monitoring counters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemoryMonitor:
    remembers: int = 0
    retrieves: int = 0
    auto_loads: int = 0
    auto_writes: int = 0
    deletes: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)

    def record_remember(self, memory_type: str, category: str) -> None:
        self.remembers += 1
        self.by_type[memory_type] = self.by_type.get(memory_type, 0) + 1
        self.by_category[category] = self.by_category.get(category, 0) + 1

    def record_retrieve(self, hits: int) -> None:
        self.retrieves += 1
        _ = hits

    def record_auto_load(self) -> None:
        self.auto_loads += 1

    def record_auto_write(self, count: int) -> None:
        self.auto_writes += count

    def record_delete(self) -> None:
        self.deletes += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "remembers": self.remembers,
            "retrieves": self.retrieves,
            "auto_loads": self.auto_loads,
            "auto_writes": self.auto_writes,
            "deletes": self.deletes,
            "by_type": dict(self.by_type),
            "by_category": dict(self.by_category),
        }
