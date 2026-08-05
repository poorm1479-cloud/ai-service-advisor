"""Owner Dashboard & AI Operations Center — models (read-only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class MetricPoint:
    key: str
    label: str
    value: float | int | str
    unit: str | None = None
    tone: str = "neutral"
    detail: str | None = None


@dataclass(slots=True)
class QueueItem:
    id: str
    title: str
    subtitle: str | None = None
    status: str | None = None
    priority: str = "normal"
    href: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DashboardWidget:
    id: str
    title: str
    kind: str
    items: list[QueueItem] = field(default_factory=list)
    metrics: list[MetricPoint] = field(default_factory=list)
    summary: str | None = None


@dataclass(slots=True)
class OwnerDashboardSnapshot:
    shop_id: UUID
    generated_at: datetime
    version: int
    summary: dict[str, Any]
    widgets: list[DashboardWidget]
    performance: dict[str, Any]
    system_health: dict[str, Any]
    sources: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "shop_id": str(self.shop_id),
            "generated_at": self.generated_at.isoformat(),
            "version": self.version,
            "read_only": True,
            "summary": self.summary,
            "performance": self.performance,
            "system_health": self.system_health,
            "widgets": [
                {
                    "id": w.id,
                    "title": w.title,
                    "kind": w.kind,
                    "summary": w.summary,
                    "metrics": [
                        {
                            "key": m.key,
                            "label": m.label,
                            "value": m.value,
                            "unit": m.unit,
                            "tone": m.tone,
                            "detail": m.detail,
                        }
                        for m in w.metrics
                    ],
                    "items": [
                        {
                            "id": it.id,
                            "title": it.title,
                            "subtitle": it.subtitle,
                            "status": it.status,
                            "priority": it.priority,
                            "href": it.href,
                            "meta": it.meta,
                        }
                        for it in w.items
                    ],
                }
                for w in self.widgets
            ],
            "sources": {k: _safe(v) for k, v in self.sources.items()},
        }


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            pass
    return str(value)
