"""Scenario 2 — Maintenance Reminder.

Flow:
  Vehicle health → Customer risk → Revenue opportunity → Marketing follow-up
"""

from __future__ import annotations

from uuid import UUID

from app.workflows.automotive.spec import action, build_definition, meta
from app.workflows.enums import ActionType, DomainEventType
from app.workflows.models import WorkflowDefinition

WORKFLOW_ID = UUID("a1111111-1111-4111-8111-111111111102")

SPEC = meta(
    workflow_id=str(WORKFLOW_ID),
    purpose=(
        "When maintenance reminder is requested, evaluate vehicle health and customer risk, "
        "surface revenue opportunity, and schedule marketing follow-up."
    ),
    trigger=DomainEventType.MAINTENANCE_REMINDER_REQUESTED.value,
    capabilities=[
        "CalculateVehicleHealth",
        "CalculateCustomerHealth",
        "DetectRevenueOpportunity",
        "GenerateUpsellRecommendations",
        "GenerateMaintenanceReminder",
        "AddTimeline",
        "AddCommunication",
    ],
    ai_decisions=[
        "MaintenanceReminderDecision",
        "RevenueDecision",
        "RetentionDecision",
        "MarketingDecision",
        "CustomerCommunicationDecision",
    ],
    events_published=[
        DomainEventType.CRM_UPDATED.value,
        DomainEventType.REVENUE_OPPORTUNITY_DETECTED.value,
        DomainEventType.REMINDER_SCHEDULED.value,
        DomainEventType.MARKETING_ACTION_REQUESTED.value,
        DomainEventType.DASHBOARD_UPDATED.value,
    ],
    failure_handling=(
        "Retry CRM/reminder steps; marketing notify is continue_on_error; "
        "rollback undoes CRM/reminder records. Revenue detect is logged/emitted "
        "without nested UPDATE_REVENUE to avoid reminder re-entry loops."
    ),
    human_escalation=(
        "High churn-risk customers trigger advisor notify for personal outreach."
    ),
)


def build() -> WorkflowDefinition:
    return build_definition(
        workflow_id=WORKFLOW_ID,
        name="Automotive: Maintenance reminder",
        description=SPEC["purpose"],
        trigger=DomainEventType.MAINTENANCE_REMINDER_REQUESTED,
        tags=["maintenance", "marketing", "scenario-2"],
        spec=SPEC,
        actions=[
            action(
                ActionType.SET_CONTEXT,
                "Bind maintenance scenario context",
                1,
                config={
                    "values": {
                        "scenario": "maintenance_reminder",
                        "expected_decisions": SPEC["ai_decisions"],
                        "required_capabilities": SPEC["required_capabilities"],
                    }
                },
            ),
            action(
                ActionType.LOG,
                "Vehicle health analysis",
                2,
                config={
                    "message": "CalculateVehicleHealth / Advisor maintenance analysis",
                    "capability": "CalculateVehicleHealth",
                },
            ),
            action(
                ActionType.LOG,
                "Customer risk scoring",
                3,
                config={
                    "message": "CalculateCustomerHealth / RetentionDecision inputs",
                    "capability": "CalculateCustomerHealth",
                    "ai_decision": "RetentionDecision",
                },
            ),
            action(
                ActionType.LOG,
                "Detect maintenance revenue opportunity",
                4,
                config={
                    "message": "Capability DetectRevenueOpportunity / GenerateUpsellRecommendations",
                    "capability": "DetectRevenueOpportunity",
                    "ai_decision": "RevenueDecision",
                },
            ),
            action(
                ActionType.EMIT_EVENT,
                "Publish revenue opportunity detected",
                5,
                config={
                    "event_type": DomainEventType.REVENUE_OPPORTUNITY_DETECTED.value,
                    "payload": {"source": "maintenance_reminder"},
                },
                continue_on_error=True,
            ),
            action(
                ActionType.UPDATE_CRM,
                "CRM maintenance follow-up note",
                6,
                config={
                    "note": "Maintenance reminder — vehicle health + risk assessed",
                    "fields": {"ai_decision": "MaintenanceReminderDecision"},
                },
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.SCHEDULE_REMINDER,
                "Schedule customer maintenance outreach",
                7,
                config={
                    "hours_before": 0,
                    "channel": "sms",
                    "template": "maintenance_due",
                },
                compensate={"type": "cancel_reminder"},
            ),
            action(
                ActionType.EMIT_EVENT,
                "Request marketing follow-up",
                8,
                config={
                    "event_type": DomainEventType.MARKETING_ACTION_REQUESTED.value,
                    "payload": {"campaign": "maintenance_reminder", "channel": "sms"},
                },
            ),
            action(
                ActionType.NOTIFY,
                "Escalate high-risk customers to advisors",
                9,
                config={
                    "channel": "in_app",
                    "message": "High-risk maintenance customer may need personal call",
                },
                continue_on_error=True,
            ),
            action(
                ActionType.UPDATE_DASHBOARD,
                "Refresh marketing/revenue widgets",
                10,
                config={
                    "widget": "overview",
                    "invalidate": ["marketing", "revenue", "retention"],
                },
                continue_on_error=True,
            ),
        ],
    )
