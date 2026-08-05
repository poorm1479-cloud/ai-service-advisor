"""Import engine monitoring counters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImportMonitor:
    jobs_created: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    records_imported: int = 0
    duplicates_detected: int = 0
    by_source: dict[str, int] = field(default_factory=dict)

    def record_created(self, source: str) -> None:
        self.jobs_created += 1
        self.by_source[source] = self.by_source.get(source, 0) + 1

    def record_completed(self, *, records: int, duplicates: int) -> None:
        self.jobs_completed += 1
        self.records_imported += records
        self.duplicates_detected += duplicates

    def record_failed(self) -> None:
        self.jobs_failed += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "jobs_created": self.jobs_created,
            "jobs_completed": self.jobs_completed,
            "jobs_failed": self.jobs_failed,
            "records_imported": self.records_imported,
            "duplicates_detected": self.duplicates_detected,
            "by_source": dict(self.by_source),
        }
