"""Scenario 3 — Inspection Completed.

Flow:
  Inspection analysis → Customer explanation → Estimate recommendation → Approval request
"""

from __future__ import annotations

from uuid import UUID

from app.workflows.automotive.spec import action, build_definition, cond, meta
from app.workflows.enums import ActionType, ConditionOperator, DomainEventType
from app.workflows.models import WorkflowDefinition

WORKFLOW_ID = UUID("a1111111-1111-4111-8111-111111111103")

SPEC = meta(
    workflow_id=str(WORKFLOW_ID),
    purpose=(
        "After an inspection finishes, produce customer explanation, estimate recommendation, "
        "and route an approval request with CRM + revenue updates."
    ),
    trigger=DomainEventType.REPAIR_FINISHED.value,
    capabilities=[
        "AnalyzeConversation",
        "GenerateRepairRecommendation",
        "GenerateEstimateSummary",
        "GenerateCustomerExplanation",
        "GenerateApprovalRequest",
        "AddRepair",
        "AddCommunication",
        "AddTimeline",
    ],
    ai_decisions=[
        "RepairRecommendationDecision",
        "EstimateExplanationDecision",
        "ApprovalRequestDecision",
        "CustomerCommunicationDecision",
        "CrmUpdateDecision",
    ],
    events_published=[
        DomainEventType.ESTIMATE_SENT.value,
        DomainEventType.CRM_UPDATED.value,
        DomainEventType.REVENUE_UPDATED.value,
        DomainEventType.DASHBOARD_UPDATED.value,
        DomainEventType.HUMAN_ESCALATION_REQUESTED.value,
    ],
    failure_handling=(
        "Retry estimate/CRM steps; approval notify continue_on_error; "
        "rollback reverses CRM/revenue side-effects."
    ),
    human_escalation=(
        "Pending approvals notify owner/manager; escalate when estimate exceeds shop threshold."
    ),
)


def build() -> WorkflowDefinition:
    return build_definition(
        workflow_id=WORKFLOW_ID,
        name="Automotive: Inspection completed",
        description=SPEC["purpose"],
        trigger=DomainEventType.REPAIR_FINISHED,
        conditions=[
            cond("phase", ConditionOperator.EQ, "inspection"),
        ],
        tags=["inspection", "estimate", "approval", "scenario-3"],
        spec=SPEC,
        actions=[
            action(
                ActionType.SET_CONTEXT,
                "Bind inspection scenario",
                1,
                config={
                    "values": {
                        "scenario": "inspection_completed",
                        "expected_decisions": SPEC["ai_decisions"],
                        "required_capabilities": SPEC["required_capabilities"],
                    }
                },
            ),
            action(
                ActionType.LOG,
                "Inspection analysis",
                2,
                config={
                    "message": "Advisor AnalyzeConversation / vehicle inspection findings",
                    "capability": "AnalyzeConversation|GenerateRepairRecommendation",
                },
            ),
            action(
                ActionType.UPDATE_CRM,
                "Customer explanation on timeline",
                3,
                config={
                    "note": "Inspection completed — customer explanation prepared",
                    "fields": {
                        "capability": "GenerateCustomerExplanation",
                        "ai_decision": "CustomerCommunicationDecision",
                    },
                },
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.EMIT_EVENT,
                "Publish estimate recommendation",
                4,
                config={
                    "event_type": DomainEventType.ESTIMATE_SENT.value,
                    "payload": {"source": "inspection_completed"},
                },
            ),
            action(
                ActionType.UPDATE_CRM,
                "Estimate recommendation recorded",
                5,
                config={
                    "note": "Estimate recommendation from inspection",
                    "fields": {
                        "capability": "GenerateEstimateSummary",
                        "ai_decision": "EstimateExplanationDecision",
                    },
                },
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.UPDATE_REVENUE,
                "Open estimate revenue opportunity",
                6,
                config={"category": "inspection_estimate"},
                compensate={"type": "undo_revenue"},
            ),
            action(
                ActionType.NOTIFY,
                "Approval request to owner/manager",
                7,
                config={
                    "channel": "in_app",
                    "message": "Inspection estimate awaiting customer/owner approval",
                    "ai_decision": "ApprovalRequestDecision",
                },
            ),
            action(
                ActionType.EMIT_EVENT,
                "Human escalation for approval",
                8,
                config={
                    "event_type": DomainEventType.HUMAN_ESCALATION_REQUESTED.value,
                    "payload": {
                        "reason": "inspection_approval_request",
                        "scenario": "inspection_completed",
                    },
                },
                continue_on_error=True,
            ),
            action(
                ActionType.UPDATE_DASHBOARD,
                "Refresh approvals widget",
                9,
                config={
                    "widget": "overview",
                    "invalidate": ["approvals", "estimates", "revenue"],
                },
                continue_on_error=True,
            ),
        ],
    )
