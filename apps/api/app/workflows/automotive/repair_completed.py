"""Scenario 6 — Repair Completed.

Flow:
  Payment workflow → Review request → Maintenance reminder → Revenue update
"""

from __future__ import annotations

from uuid import UUID

from app.workflows.automotive.spec import action, build_definition, cond, meta
from app.workflows.enums import ActionType, ConditionOperator, DomainEventType
from app.workflows.models import WorkflowDefinition

WORKFLOW_ID = UUID("a1111111-1111-4111-8111-111111111106")

SPEC = meta(
    workflow_id=str(WORKFLOW_ID),
    purpose=(
        "Close out a finished repair: payment cue, review request, maintenance reminder, "
        "and final revenue/dashboard updates."
    ),
    trigger=DomainEventType.REPAIR_FINISHED.value,
    capabilities=[
        "AddRepair",
        "AddCommunication",
        "AddTimeline",
        "GenerateReviewRequest",
        "GenerateMaintenanceReminder",
        "DetectRevenueOpportunity",
        "UpdateConversation",
    ],
    ai_decisions=[
        "RepairStatusDecision",
        "ReviewRequestDecision",
        "MaintenanceReminderDecision",
        "RevenueDecision",
        "CustomerCommunicationDecision",
        "CrmUpdateDecision",
    ],
    events_published=[
        DomainEventType.INVOICE_PAID.value,
        DomainEventType.REVIEW_SUBMITTED.value,
        DomainEventType.MAINTENANCE_REMINDER_REQUESTED.value,
        DomainEventType.CRM_UPDATED.value,
        DomainEventType.REVENUE_UPDATED.value,
        DomainEventType.REMINDER_SCHEDULED.value,
        DomainEventType.DASHBOARD_UPDATED.value,
    ],
    failure_handling=(
        "Payment/review emits continue_on_error so closeout continues; "
        "CRM/revenue/reminder retried; rollback reverses CRM/revenue/reminder."
    ),
    human_escalation=(
        "Notify front desk if payment still open after repair finished."
    ),
)


def build() -> WorkflowDefinition:
    return build_definition(
        workflow_id=WORKFLOW_ID,
        name="Automotive: Repair completed",
        description=SPEC["purpose"],
        trigger=DomainEventType.REPAIR_FINISHED,
        conditions=[
            # Runs for normal repair closeout; inspection phase handled by sibling workflow.
            cond("phase", ConditionOperator.NE, "inspection"),
        ],
        tags=["repair", "payment", "review", "scenario-6"],
        spec=SPEC,
        actions=[
            action(
                ActionType.SET_CONTEXT,
                "Bind repair-completed scenario",
                1,
                config={
                    "values": {
                        "scenario": "repair_completed",
                        "expected_decisions": SPEC["ai_decisions"],
                        "required_capabilities": SPEC["required_capabilities"],
                    }
                },
            ),
            action(
                ActionType.UPDATE_CRM,
                "Repair completion timeline",
                2,
                config={
                    "note": "Repair finished — closeout started",
                    "fields": {
                        "capability": "AddRepair|AddTimeline",
                        "ai_decision": "RepairStatusDecision",
                    },
                },
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.EMIT_EVENT,
                "Payment workflow cue",
                3,
                config={
                    "event_type": DomainEventType.INVOICE_PAID.value,
                    "payload": {"source": "repair_completed", "status": "payment_due_or_paid"},
                },
                continue_on_error=True,
            ),
            action(
                ActionType.NOTIFY,
                "Front desk payment check",
                4,
                config={
                    "channel": "in_app",
                    "message": "Repair completed — confirm payment collected",
                },
                continue_on_error=True,
            ),
            action(
                ActionType.SCHEDULE_REMINDER,
                "Review request outreach",
                5,
                config={
                    "hours_before": -24,
                    "channel": "sms",
                    "template": "review_request",
                    "ai_decision": "ReviewRequestDecision",
                },
                compensate={"type": "cancel_reminder"},
            ),
            action(
                ActionType.EMIT_EVENT,
                "Review request recorded",
                6,
                config={
                    "event_type": DomainEventType.REVIEW_SUBMITTED.value,
                    "payload": {"source": "repair_completed", "status": "requested"},
                },
                continue_on_error=True,
            ),
            action(
                ActionType.EMIT_EVENT,
                "Queue maintenance reminder",
                7,
                config={
                    "event_type": DomainEventType.MAINTENANCE_REMINDER_REQUESTED.value,
                    "payload": {"source": "repair_completed"},
                },
                continue_on_error=True,
            ),
            action(
                ActionType.UPDATE_REVENUE,
                "Final revenue update",
                8,
                config={"category": "repair_completed"},
                compensate={"type": "undo_revenue"},
            ),
            action(
                ActionType.UPDATE_CRM,
                "Closeout CRM communication",
                9,
                config={
                    "note": "Repair completed — review + maintenance follow-ups scheduled",
                    "fields": {
                        "ai_decision": "CustomerCommunicationDecision|MaintenanceReminderDecision"
                    },
                },
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.UPDATE_DASHBOARD,
                "Refresh completion widgets",
                10,
                config={
                    "widget": "overview",
                    "invalidate": ["revenue", "repairs", "reviews", "marketing"],
                },
                continue_on_error=True,
            ),
        ],
    )
