"""Executive dashboard monitoring."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutiveMonitor:
    refreshes: int = 0
    cache_hits: int = 0
    poll_requests: int = 0

    def record_refresh(self) -> None:
        self.refreshes += 1

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    def record_poll(self) -> None:
        self.poll_requests += 1

    def snapshot(self) -> dict[str, int]:
        return {
            "refreshes": self.refreshes,
            "cache_hits": self.cache_hits,
            "poll_requests": self.poll_requests,
        }
