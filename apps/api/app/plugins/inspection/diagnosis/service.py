"""Diagnosis — understand vehicle condition and safety issues from inspection."""

from __future__ import annotations

from typing import Any

from app.agents.decisions.types import InspectionAnalysisDecision, SafetyAlertDecision
from app.plugins.inspection.models import FindingSeverity, InspectionContext, InspectionFinding


class DiagnosisService:
    """Analyze inspection data — Decision Objects only."""

    def analyze(self, ctx: InspectionContext) -> list[Any]:
        findings = list(ctx.findings)
        safety = [
            f
            for f in findings
            if f.severity in {FindingSeverity.SAFETY, FindingSeverity.CRITICAL}
        ]
        recommended = [f for f in findings if f.severity == FindingSeverity.RECOMMENDED]
        optional = [f for f in findings if f.severity == FindingSeverity.OPTIONAL]
        systems = sorted({f.system for f in findings})
        condition = self._condition_summary(findings, safety)

        decisions: list[Any] = [
            InspectionAnalysisDecision(
                inspection_id=ctx.inspection_id or (ctx.inspection.id if ctx.inspection else None),
                customer_id=ctx.customer_id,
                vehicle_id=ctx.vehicle_id,
                condition_summary=condition,
                finding_count=len(findings),
                safety_count=len(safety),
                recommended_count=len(recommended),
                optional_count=len(optional),
                systems=systems,
                urgency=self._urgency(safety, recommended),
                findings_snapshot=[self._snap(f) for f in findings],
                confidence=0.88 if findings else 0.4,
                rationale="Inspection analysis from technician findings",
            )
        ]
        for f in safety:
            decisions.append(
                SafetyAlertDecision(
                    inspection_id=ctx.inspection_id or (ctx.inspection.id if ctx.inspection else None),
                    customer_id=ctx.customer_id,
                    vehicle_id=ctx.vehicle_id,
                    finding_id=f.id,
                    title=f.title,
                    issue=f.description or f.title,
                    severity=f.severity.value,
                    system=f.system,
                    urgent=f.severity == FindingSeverity.CRITICAL,
                    plain_language=(
                        f"Safety concern: {f.title}. "
                        f"{'Do not defer — critical.' if f.severity == FindingSeverity.CRITICAL else 'Please address soon.'}"
                    ),
                    confidence=0.9,
                    rationale="Safety finding detected in inspection",
                )
            )
        return decisions

    def detect_safety(self, ctx: InspectionContext) -> list[Any]:
        return [d for d in self.analyze(ctx) if isinstance(d, SafetyAlertDecision)]

    def _urgency(self, safety: list[InspectionFinding], recommended: list[InspectionFinding]) -> str:
        if any(f.severity == FindingSeverity.CRITICAL for f in safety):
            return "urgent"
        if safety:
            return "high"
        if recommended:
            return "normal"
        return "low"

    def _condition_summary(
        self, findings: list[InspectionFinding], safety: list[InspectionFinding]
    ) -> str:
        if not findings:
            return "No notable inspection findings."
        if safety:
            return (
                f"Vehicle needs attention: {len(safety)} safety-related finding(s) "
                f"among {len(findings)} total."
            )
        return f"Inspection complete with {len(findings)} finding(s) requiring review."

    def _snap(self, f: InspectionFinding) -> dict[str, Any]:
        return {
            "id": str(f.id),
            "title": f.title,
            "system": f.system,
            "severity": f.severity.value,
            "estimated_cost": str(f.estimated_cost),
        }
