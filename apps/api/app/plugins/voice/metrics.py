"""Voice plugin production metrics."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class VoicePluginMetrics:
    call_volume: int = 0
    calls_completed: int = 0
    total_response_ms: float = 0.0
    response_samples: int = 0
    ai_resolved: int = 0
    human_transfers: int = 0
    appointment_conversions: int = 0
    satisfaction_sum: float = 0.0
    satisfaction_samples: int = 0
    last_event_at: datetime | None = None
    notes: list[str] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        avg_response = (
            self.total_response_ms / self.response_samples if self.response_samples else 0.0
        )
        completed = max(1, self.calls_completed) if self.calls_completed else 0
        return {
            "call_volume": self.call_volume,
            "calls_completed": self.calls_completed,
            "average_response_time_ms": round(avg_response, 2),
            "ai_resolution_rate": round(self.ai_resolved / completed, 4) if completed else 0.0,
            "human_transfer_rate": round(self.human_transfers / completed, 4) if completed else 0.0,
            "appointment_conversion_rate": (
                round(self.appointment_conversions / completed, 4) if completed else 0.0
            ),
            "customer_satisfaction": (
                round(self.satisfaction_sum / self.satisfaction_samples, 3)
                if self.satisfaction_samples
                else None
            ),
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
        }


class VoiceMetricsCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.metrics = VoicePluginMetrics()
        self._events: list[dict[str, Any]] = []

    def _touch(self) -> None:
        self.metrics.last_event_at = datetime.now(timezone.utc)

    def record_call_started(self) -> None:
        with self._lock:
            self.metrics.call_volume += 1
            self._touch()

    def record_response_time(self, ms: float) -> None:
        with self._lock:
            self.metrics.total_response_ms += max(0.0, ms)
            self.metrics.response_samples += 1
            self._touch()

    def record_call_completed(
        self,
        *,
        resolved_by_ai: bool = False,
        transferred: bool = False,
        appointment_converted: bool = False,
        satisfaction: float | None = None,
    ) -> None:
        with self._lock:
            self.metrics.calls_completed += 1
            if resolved_by_ai:
                self.metrics.ai_resolved += 1
            if transferred:
                self.metrics.human_transfers += 1
            if appointment_converted:
                self.metrics.appointment_conversions += 1
            if satisfaction is not None:
                self.metrics.satisfaction_sum += float(satisfaction)
                self.metrics.satisfaction_samples += 1
            self._touch()

    def record_transfer(self, reason: str | None = None) -> None:
        """Note a transfer intent; completion metrics count the rate once."""
        with self._lock:
            if reason:
                self.metrics.notes.append(reason[:200])
                self.metrics.notes = self.metrics.notes[-50:]
            self._touch()

    def append_event(self, event: Any) -> None:
        with self._lock:
            self._events.append(
                {
                    "event_type": getattr(event, "event_type", type(event).__name__),
                    "event_id": str(getattr(event, "event_id", "")),
                    "occurred_at": getattr(event, "occurred_at", datetime.now(timezone.utc)).isoformat(),
                }
            )
            self._events = self._events[-200:]
            self._touch()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            out = self.metrics.snapshot()
            out["recent_events"] = list(self._events[-20:])
            return out
