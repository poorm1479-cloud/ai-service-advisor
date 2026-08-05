"""InspectionPlugin — Inspection Intelligence (decide-only AI).

Transforms technician inspection results into Decision Objects.
Never mutates CRM, invoices, appointments, messages, or approvals.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.inspection.approval.service import ApprovalService
from app.plugins.inspection.checklist.service import ChecklistService
from app.plugins.inspection.diagnosis.service import DiagnosisService
from app.plugins.inspection.explanation.service import ExplanationService
from app.plugins.inspection.models import InspectionContext, InspectionPlan, InspectionRecord
from app.plugins.inspection.recommendation.service import RecommendationService
from app.plugins.inspection.store import InspectionStore


class InspectionPlugin:
    """IPlugin — Inspection Intelligence for AutoRepair OS."""

    def __init__(
        self,
        *,
        store: InspectionStore | None = None,
        checklist: ChecklistService | None = None,
        diagnosis: DiagnosisService | None = None,
        recommendation: RecommendationService | None = None,
        explanation: ExplanationService | None = None,
        approval: ApprovalService | None = None,
    ) -> None:
        self._store = store or InspectionStore()
        self._checklist = checklist or ChecklistService()
        self._diagnosis = diagnosis or DiagnosisService()
        self._recommendation = recommendation or RecommendationService()
        self._explanation = explanation or ExplanationService()
        self._approval = approval or ApprovalService()
        self._initialized = False

    def plugin_id(self) -> str:
        return "inspection"

    def plugin_name(self) -> str:
        return "Inspection Intelligence"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Transforms technician inspection results into AI-powered customer service "
            "workflows via Decision Objects only — Workflow executes business actions."
        )

    def supported_capabilities(self) -> list[str]:
        # Unique inspection capabilities. GenerateRepairRecommendation /
        # GenerateCustomerExplanation remain owned by Advisor for backward
        # compatibility; inspection fulfills them via AnalyzeInspection +
        # PrioritizeRepair / explanation submodule (aliases below).
        return [
            Capability.ANALYZE_INSPECTION.value,
            Capability.DETECT_SAFETY_ISSUE.value,
            Capability.GENERATE_ESTIMATE_SUGGESTION.value,
            Capability.CREATE_APPROVAL_REQUEST.value,
            Capability.PRIORITIZE_REPAIR.value,
            Capability.CREATE_FOLLOW_UP.value,
            # Inspection-scoped names matching Phase 13 responsibility map
            Capability.GENERATE_INSPECTION_REPAIR_RECOMMENDATION.value,
            Capability.GENERATE_INSPECTION_CUSTOMER_EXPLANATION.value,
        ]

    def capabilities(self) -> list[str]:
        return self.supported_capabilities()

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
            "capabilities": len(self.supported_capabilities()),
            "stored_inspections": len(self._store._by_id),
        }

    @property
    def store(self) -> InspectionStore:
        return self._store

    def build_context(self, **kwargs: Any) -> InspectionContext:
        shop_id = kwargs["shop_id"]
        payload = {k: v for k, v in kwargs.items() if k != "shop_id"}
        record = payload.get("inspection")
        if isinstance(record, InspectionRecord):
            inspection = record
        elif payload.get("inspection_id"):
            inspection = self._store.get(payload["inspection_id"])
        elif payload.get("findings") is not None or payload.get("store_result"):
            inspection = self._checklist.build_record(shop_id=shop_id, **payload)
            if payload.get("store_result", True):
                self._store.save(inspection)
        else:
            inspection = None

        findings = list(payload.get("findings_resolved") or [])
        if inspection and not findings:
            findings = list(inspection.findings)
        elif payload.get("findings") is not None and not findings:
            findings = self._checklist.normalize_findings(list(payload.get("findings") or []))

        return InspectionContext(
            shop_id=shop_id,
            inspection=inspection,
            inspection_id=(
                inspection.id
                if inspection
                else payload.get("inspection_id")
            ),
            customer_id=payload.get("customer_id")
            or (inspection.customer_id if inspection else None),
            vehicle_id=payload.get("vehicle_id")
            or (inspection.vehicle_id if inspection else None),
            findings=findings,
            channel=payload.get("channel") or "sms",
            metadata=dict(payload.get("metadata") or {}),
        )

    def analyze(self, ctx: InspectionContext) -> InspectionPlan:
        """Full inspection intelligence pass — Decision Objects only."""
        decisions: list[Any] = []
        notes: list[str] = []

        diagnosis = self._diagnosis.analyze(ctx)
        decisions.extend(diagnosis)
        safety = [d for d in diagnosis if d.__class__.__name__ == "SafetyAlertDecision"]
        notes.append(f"Diagnosed {len(ctx.findings)} finding(s); safety={len(safety)}")

        recs = self._recommendation.prioritize(ctx)
        decisions.extend(recs)
        notes.append(f"Prioritized {len(recs)} repair recommendation(s)")

        explanations = self._explanation.explain(ctx, safety_alerts=safety)
        decisions.extend(explanations)

        approvals = self._approval.create_approval_request(ctx, recommendations=recs)
        decisions.extend(approvals)

        followups = self._approval.create_follow_up(ctx, recommendations=recs)
        decisions.extend(followups)

        total = sum((r.estimated_cost for r in recs), Decimal("0.00"))
        safety_count = len(safety)
        recommended_count = sum(
            1 for f in ctx.findings if f.severity.value == "recommended"
        )
        optional_count = sum(1 for f in ctx.findings if f.severity.value == "optional")

        return InspectionPlan(
            inspection_id=ctx.inspection_id,
            decisions=decisions,
            advisor_notes=notes,
            safety_issue_count=safety_count,
            recommended_count=recommended_count,
            optional_count=optional_count,
            estimated_total=total,
            dashboard={
                "inspection_id": str(ctx.inspection_id) if ctx.inspection_id else None,
                "finding_count": len(ctx.findings),
                "safety_issue_count": safety_count,
                "recommended_count": recommended_count,
                "optional_count": optional_count,
                "estimated_total": str(total),
                "decision_count": len(decisions),
            },
        )

    def _decisions_payload(self, plan: InspectionPlan) -> dict[str, Any]:
        return {
            "decisions": plan.decisions,
            "advisor_notes": plan.advisor_notes,
            "dashboard": plan.dashboard,
            "inspection_id": str(plan.inspection_id) if plan.inspection_id else None,
            "estimated_total": str(plan.estimated_total),
        }

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        shop_id = kwargs.get("shop_id") or (context.shop_id if context else None)
        if shop_id is None:
            raise ValueError("shop_id required for Inspection Intelligence")
        if isinstance(shop_id, str):
            shop_id = UUID(shop_id)

        # Always allow storing raw inspection results without analysis
        if kwargs.get("store_only"):
            record = self._checklist.build_record(shop_id=shop_id, **kwargs)
            self._store.save(record)
            return {"inspection": record, "stored": True}

        ctx = self.build_context(shop_id=shop_id, **{k: v for k, v in kwargs.items() if k != "shop_id"})
        cap = capability if isinstance(capability, str) else str(capability)

        if cap in {
            Capability.ANALYZE_INSPECTION.value,
            "AnalyzeInspection",
            Capability.GENERATE_REPAIR_RECOMMENDATION.value,
            Capability.GENERATE_CUSTOMER_EXPLANATION.value,
        }:
            # GenerateRepairRecommendation / GenerateCustomerExplanation when
            # invoked on this plugin (direct) run full analysis; registry still
            # routes those names to Advisor for backward compatibility.
            plan = self.analyze(ctx)
            return self._decisions_payload(plan)

        if cap in {Capability.DETECT_SAFETY_ISSUE.value, "DetectSafetyIssue"}:
            decisions = self._diagnosis.detect_safety(ctx)
            return {"decisions": decisions, "count": len(decisions)}

        if cap in {
            Capability.GENERATE_INSPECTION_REPAIR_RECOMMENDATION.value,
            Capability.PRIORITIZE_REPAIR.value,
            "PrioritizeRepair",
            "GenerateRepairRecommendation",
        }:
            decisions = self._recommendation.prioritize(ctx)
            return {"decisions": decisions, "count": len(decisions)}

        if cap in {
            Capability.GENERATE_INSPECTION_CUSTOMER_EXPLANATION.value,
            "GenerateCustomerExplanation",
        }:
            safety = self._diagnosis.detect_safety(ctx)
            decisions = self._explanation.explain(ctx, safety_alerts=safety)
            return {"decisions": decisions, "count": len(decisions)}

        if cap in {Capability.GENERATE_ESTIMATE_SUGGESTION.value, "GenerateEstimateSuggestion"}:
            suggestion = self._recommendation.estimate_suggestion(ctx)
            return suggestion

        if cap in {Capability.CREATE_APPROVAL_REQUEST.value, "CreateApprovalRequest"}:
            recs = self._recommendation.prioritize(ctx)
            decisions = self._approval.create_approval_request(ctx, recommendations=recs)
            return {"decisions": decisions, "count": len(decisions)}

        if cap in {Capability.CREATE_FOLLOW_UP.value, "CreateFollowUp"}:
            recs = self._recommendation.prioritize(ctx)
            decisions = self._approval.create_follow_up(ctx, recommendations=recs)
            return {"decisions": decisions, "count": len(decisions)}

        raise LookupError(f"Unsupported inspection capability: {cap}")
