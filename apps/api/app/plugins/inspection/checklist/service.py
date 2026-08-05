"""Checklist helpers — normalize technician inspection findings."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.plugins.inspection.models import FindingSeverity, InspectionFinding, InspectionRecord

_SYSTEM_HINTS: dict[str, str] = {
    "brake": "brakes",
    "pad": "brakes",
    "rotor": "brakes",
    "tire": "tires",
    "oil": "fluids",
    "fluid": "fluids",
    "battery": "electrical",
    "belt": "engine",
    "hose": "engine",
    "suspension": "suspension",
    "light": "electrical",
    "sensor": "electrical",
}


def _severity_from_text(text: str) -> FindingSeverity:
    lower = text.lower()
    if any(w in lower for w in ("unsafe", "critical", "danger", "fail", "metal-on-metal")):
        return FindingSeverity.CRITICAL
    if any(w in lower for w in ("safety", "urgent", "immediate", "leak", "worn thin")):
        return FindingSeverity.SAFETY
    if any(w in lower for w in ("recommend", "should", "replace soon", "due")):
        return FindingSeverity.RECOMMENDED
    if any(w in lower for w in ("optional", "consider", "monitor", "suggest")):
        return FindingSeverity.OPTIONAL
    return FindingSeverity.RECOMMENDED


def _system_from_text(text: str) -> str:
    lower = text.lower()
    for key, system in _SYSTEM_HINTS.items():
        if key in lower:
            return system
    return "general"


def _cost_for(severity: FindingSeverity, system: str) -> Decimal:
    base = {
        FindingSeverity.INFO: Decimal("0.00"),
        FindingSeverity.OPTIONAL: Decimal("89.00"),
        FindingSeverity.RECOMMENDED: Decimal("220.00"),
        FindingSeverity.SAFETY: Decimal("380.00"),
        FindingSeverity.CRITICAL: Decimal("650.00"),
    }[severity]
    bump = Decimal("40.00") if system in {"brakes", "suspension"} else Decimal("0.00")
    return base + bump


class ChecklistService:
    """Build / normalize checklist findings into InspectionRecord shape."""

    DEFAULT_CHECKLIST_ID = "multipoint_v1"

    def normalize_findings(self, raw: list[Any]) -> list[InspectionFinding]:
        findings: list[InspectionFinding] = []
        for item in raw:
            if isinstance(item, InspectionFinding):
                findings.append(item)
                continue
            if isinstance(item, str):
                severity = _severity_from_text(item)
                system = _system_from_text(item)
                findings.append(
                    InspectionFinding(
                        code=system[:3].upper() + "-AUTO",
                        system=system,
                        title=item[:80],
                        description=item,
                        severity=severity,
                        recommended_service=f"{system}_service",
                        estimated_cost=_cost_for(severity, system),
                    )
                )
                continue
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("finding") or item.get("name") or "Finding")
                desc = str(item.get("description") or item.get("notes") or title)
                severity_raw = item.get("severity")
                severity = (
                    FindingSeverity(str(severity_raw))
                    if severity_raw in FindingSeverity._value2member_map_
                    else _severity_from_text(f"{title} {desc}")
                )
                system = str(item.get("system") or _system_from_text(f"{title} {desc}"))
                cost = Decimal(str(item.get("estimated_cost") or _cost_for(severity, system)))
                findings.append(
                    InspectionFinding(
                        id=UUID(str(item["id"])) if item.get("id") else uuid4(),
                        code=str(item.get("code") or f"{system[:3].upper()}-1"),
                        system=system,
                        title=title,
                        description=desc,
                        severity=severity,
                        measured_value=item.get("measured_value"),
                        recommended_service=item.get("recommended_service") or f"{system}_service",
                        estimated_cost=cost,
                        photos=list(item.get("photos") or []),
                        technician_notes=str(item.get("technician_notes") or ""),
                    )
                )
        return findings

    def build_record(self, *, shop_id: UUID, **kwargs: Any) -> InspectionRecord:
        findings = self.normalize_findings(list(kwargs.get("findings") or []))
        return InspectionRecord(
            id=kwargs.get("inspection_id") or kwargs.get("id") or uuid4(),
            shop_id=shop_id,
            customer_id=kwargs.get("customer_id"),
            vehicle_id=kwargs.get("vehicle_id"),
            technician_id=kwargs.get("technician_id"),
            checklist_id=kwargs.get("checklist_id") or self.DEFAULT_CHECKLIST_ID,
            findings=findings,
            mileage=kwargs.get("mileage"),
            vehicle_summary=dict(kwargs.get("vehicle_summary") or kwargs.get("vehicle") or {}),
            raw_notes=str(kwargs.get("raw_notes") or kwargs.get("notes") or ""),
            status=kwargs.get("status") or "completed",
            metadata=dict(kwargs.get("metadata") or {}),
        )
