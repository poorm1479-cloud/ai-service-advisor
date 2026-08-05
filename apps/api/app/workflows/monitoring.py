"""Workflow monitoring counters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkflowMonitor:
    events_emitted: int = 0
    runs_started: int = 0
    runs_completed: int = 0
    runs_failed: int = 0
    runs_rolled_back: int = 0
    runs_paused: int = 0
    runs_resumed: int = 0
    retries_processed: int = 0
    orchestrations: int = 0
    by_event: dict[str, int] = field(default_factory=dict)
    by_orchestration: dict[str, int] = field(default_factory=dict)

    def record_event(self, event_type: str) -> None:
        self.events_emitted += 1
        self.by_event[event_type] = self.by_event.get(event_type, 0) + 1

    def record_run_started(self) -> None:
        self.runs_started += 1

    def record_run_completed(self) -> None:
        self.runs_completed += 1

    def record_run_failed(self) -> None:
        self.runs_failed += 1

    def record_rollback(self) -> None:
        self.runs_rolled_back += 1

    def record_retries(self, n: int) -> None:
        self.retries_processed += n

    def record_orchestration(self, kind: str) -> None:
        self.orchestrations += 1
        self.by_orchestration[kind] = self.by_orchestration.get(kind, 0) + 1

    def record_pause(self) -> None:
        self.runs_paused += 1

    def record_resume(self) -> None:
        self.runs_resumed += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "events_emitted": self.events_emitted,
            "runs_started": self.runs_started,
            "runs_completed": self.runs_completed,
            "runs_failed": self.runs_failed,
            "runs_rolled_back": self.runs_rolled_back,
            "runs_paused": self.runs_paused,
            "runs_resumed": self.runs_resumed,
            "retries_processed": self.retries_processed,
            "orchestrations": self.orchestrations,
            "by_event": dict(self.by_event),
            "by_orchestration": dict(self.by_orchestration),
        }
