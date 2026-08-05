"""Voice AI monitoring."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("asa.voice.monitor")


@dataclass
class VoiceMetrics:
    calls_started: int = 0
    calls_completed: int = 0
    turns_processed: int = 0
    interrupts: int = 0
    escalations: int = 0
    owner_notifications: int = 0
    stream_events: int = 0
    webhook_rejected: int = 0
    live_calls: int = 0
    last_event_at: datetime | None = None
    notes: list[str] = field(default_factory=list)

    def snapshot(self) -> dict:
        return {
            "calls_started": self.calls_started,
            "calls_completed": self.calls_completed,
            "turns_processed": self.turns_processed,
            "interrupts": self.interrupts,
            "escalations": self.escalations,
            "owner_notifications": self.owner_notifications,
            "stream_events": self.stream_events,
            "webhook_rejected": self.webhook_rejected,
            "live_calls": self.live_calls,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
        }


class VoiceMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.metrics = VoiceMetrics()

    def _touch(self) -> None:
        self.metrics.last_event_at = datetime.now(timezone.utc)

    def record_call_started(self) -> None:
        with self._lock:
            self.metrics.calls_started += 1
            self._touch()

    def record_call_completed(self) -> None:
        with self._lock:
            self.metrics.calls_completed += 1
            self._touch()

    def record_turn(self) -> None:
        with self._lock:
            self.metrics.turns_processed += 1
            self._touch()

    def record_interrupt(self) -> None:
        with self._lock:
            self.metrics.interrupts += 1
            self._touch()

    def record_escalation(self, reason: str | None = None) -> None:
        with self._lock:
            self.metrics.escalations += 1
            if reason:
                self.metrics.notes.append(reason[:200])
                self.metrics.notes = self.metrics.notes[-50:]
            self._touch()

    def record_owner_notification(self) -> None:
        with self._lock:
            self.metrics.owner_notifications += 1
            self._touch()

    def record_stream_event(self) -> None:
        with self._lock:
            self.metrics.stream_events += 1
            self._touch()

    def record_webhook_rejected(self) -> None:
        with self._lock:
            self.metrics.webhook_rejected += 1
            self._touch()

    def set_live_calls(self, count: int) -> None:
        with self._lock:
            self.metrics.live_calls = count
            self._touch()

    def snapshot(self) -> dict:
        with self._lock:
            return self.metrics.snapshot()
