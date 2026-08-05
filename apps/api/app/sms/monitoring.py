"""SMS AI monitoring metrics."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("asa.sms.monitor")


@dataclass
class SmsMetrics:
    inbound_received: int = 0
    outbound_sent: int = 0
    escalations: int = 0
    appointments_booked: int = 0
    appointments_cancelled: int = 0
    appointments_rescheduled: int = 0
    queue_failures: int = 0
    webhook_rejected: int = 0
    conversations_active: int = 0
    last_event_at: datetime | None = None
    notes: list[str] = field(default_factory=list)

    def snapshot(self) -> dict:
        return {
            "inbound_received": self.inbound_received,
            "outbound_sent": self.outbound_sent,
            "escalations": self.escalations,
            "appointments_booked": self.appointments_booked,
            "appointments_cancelled": self.appointments_cancelled,
            "appointments_rescheduled": self.appointments_rescheduled,
            "queue_failures": self.queue_failures,
            "webhook_rejected": self.webhook_rejected,
            "conversations_active": self.conversations_active,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
        }


class SmsMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.metrics = SmsMetrics()

    def _touch(self) -> None:
        self.metrics.last_event_at = datetime.now(timezone.utc)

    def record_inbound(self) -> None:
        with self._lock:
            self.metrics.inbound_received += 1
            self._touch()
        logger.info("sms.monitor.inbound total=%s", self.metrics.inbound_received)

    def record_outbound(self) -> None:
        with self._lock:
            self.metrics.outbound_sent += 1
            self._touch()

    def record_escalation(self, reason: str | None = None) -> None:
        with self._lock:
            self.metrics.escalations += 1
            if reason:
                self.metrics.notes.append(reason[:200])
                self.metrics.notes = self.metrics.notes[-50:]
            self._touch()

    def record_appointment(self, action: str) -> None:
        with self._lock:
            if action == "book":
                self.metrics.appointments_booked += 1
            elif action == "cancel":
                self.metrics.appointments_cancelled += 1
            elif action == "reschedule":
                self.metrics.appointments_rescheduled += 1
            self._touch()

    def record_queue_failure(self) -> None:
        with self._lock:
            self.metrics.queue_failures += 1
            self._touch()

    def record_webhook_rejected(self) -> None:
        with self._lock:
            self.metrics.webhook_rejected += 1
            self._touch()

    def set_active_conversations(self, count: int) -> None:
        with self._lock:
            self.metrics.conversations_active = count
            self._touch()

    def snapshot(self) -> dict:
        with self._lock:
            return self.metrics.snapshot()
