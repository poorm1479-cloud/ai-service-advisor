"""Scheduling intelligence monitoring."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class SchedulingMetrics:
    bookings: int = 0
    reschedules: int = 0
    cancellations: int = 0
    conflicts_detected: int = 0
    optimizations_run: int = 0
    last_event_at: datetime | None = None

    def snapshot(self) -> dict:
        return {
            "bookings": self.bookings,
            "reschedules": self.reschedules,
            "cancellations": self.cancellations,
            "conflicts_detected": self.conflicts_detected,
            "optimizations_run": self.optimizations_run,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
        }


class SchedulingMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.metrics = SchedulingMetrics()

    def record_booking(self) -> None:
        with self._lock:
            self.metrics.bookings += 1
            self.metrics.last_event_at = datetime.now(timezone.utc)

    def record_reschedule(self) -> None:
        with self._lock:
            self.metrics.reschedules += 1
            self.metrics.last_event_at = datetime.now(timezone.utc)

    def record_cancel(self) -> None:
        with self._lock:
            self.metrics.cancellations += 1
            self.metrics.last_event_at = datetime.now(timezone.utc)

    def record_conflict(self) -> None:
        with self._lock:
            self.metrics.conflicts_detected += 1
            self.metrics.last_event_at = datetime.now(timezone.utc)

    def record_optimize(self) -> None:
        with self._lock:
            self.metrics.optimizations_run += 1
            self.metrics.last_event_at = datetime.now(timezone.utc)

    def snapshot(self) -> dict:
        with self._lock:
            return self.metrics.snapshot()
