"""Scenario 1 — New Customer Phone Repair Request.

Flow (business):
  Phone → Conversation → Customer ID → Vehicle → Repair recommendation
  → Appointment booking → SMS confirmation → CRM timeline
"""

from __future__ import annotations

from uuid import UUID

from app.workflows.automotive.spec import action, build_definition, cond, meta
from app.workflows.enums import ActionType, ConditionOperator, DomainEventType
from app.workflows.models import WorkflowDefinition

WORKFLOW_ID = UUID("a1111111-1111-4111-8111-111111111101")

SPEC = meta(
    workflow_id=str(WORKFLOW_ID),
    purpose=(
        "Orchestrate a new caller's repair request from inbound phone/voice message "
        "through identification, recommendation, booking cue, SMS confirm, and CRM timeline."
    ),
    trigger=DomainEventType.INBOUND_MESSAGE_RECEIVED.value,
    capabilities=[
        "CreateConversation",
        "FindCustomer",
        "CreateCustomer",
        "FindVehicle",
        "CreateVehicle",
        "AnalyzeConversation",
        "GenerateRepairRecommendation",
        "BookAppointment",
        "FindAvailableSlot",
        "AddCommunication",
        "AddTimeline",
        "UpdateConversation",
    ],
    ai_decisions=[
        "CustomerDecision",
        "VehicleDecision",
        "RepairRecommendationDecision",
        "EstimateExplanationDecision",
        "AppointmentDecision",
        "CustomerCommunicationDecision",
        "CrmUpdateDecision",
    ],
    events_published=[
        DomainEventType.CRM_UPDATED.value,
        DomainEventType.REMINDER_SCHEDULED.value,
        DomainEventType.REVENUE_UPDATED.value,
        DomainEventType.DASHBOARD_UPDATED.value,
        DomainEventType.HUMAN_ESCALATION_REQUESTED.value,
    ],
    failure_handling=(
        "RetryPolicy 3x with backoff on CRM/reminder/notify failures; "
        "continue_on_error on non-critical dashboard refresh; "
        "compensation undoes reminder/CRM/revenue side-effects on rollback."
    ),
    human_escalation=(
        "Notify advisors when vehicle is missing or booking cannot complete; "
        "emit human_escalation_requested for supervisor takeover."
    ),
)


def build() -> WorkflowDefinition:
    return build_definition(
        workflow_id=WORKFLOW_ID,
        name="Automotive: New customer phone repair request",
        description=SPEC["purpose"],
        trigger=DomainEventType.INBOUND_MESSAGE_RECEIVED,
        conditions=[
            # Prefer phone/voice channels; still runs if channel omitted (simulate).
            cond("channel", ConditionOperator.IN, ["phone", "voice", "call", None]),
        ],
        tags=["phone", "repair", "scenario-1"],
        spec=SPEC,
        actions=[
            action(
                ActionType.SET_CONTEXT,
                "Bind AI decision expectations",
                1,
                config={
                    "values": {
                        "scenario": "new_customer_phone_request",
                        "expected_decisions": SPEC["ai_decisions"],
                        "required_capabilities": SPEC["required_capabilities"],
                    }
                },
            ),
            action(
                ActionType.LOG,
                "Conversation creation checkpoint",
                2,
                config={
                    "message": "Ensure conversation exists (CreateConversation / phone channel)",
                    "capability": "CreateConversation",
                    "ai_decision": None,
                },
            ),
            action(
                ActionType.UPDATE_CRM,
                "Customer identification timeline",
                3,
                config={
                    "note": "Phone repair request — identify/create customer",
                    "fields": {
                        "capability": "FindCustomer|CreateCustomer",
                        "ai_decision": "CustomerDecision",
                    },
                },
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.UPDATE_CRM,
                "Vehicle identification timeline",
                4,
                config={
                    "note": "Capture or resolve vehicle for repair request",
                    "fields": {
                        "capability": "FindVehicle|CreateVehicle",
                        "ai_decision": "VehicleDecision",
                    },
                },
                continue_on_error=True,
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.UPDATE_CRM,
                "Repair recommendation recorded",
                5,
                config={
                    "note": "AI Service Advisor repair recommendation applied to CRM",
                    "fields": {
                        "capability": "AnalyzeConversation|GenerateRepairRecommendation",
                        "ai_decision": "RepairRecommendationDecision",
                    },
                },
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.UPDATE_REVENUE,
                "Seed revenue opportunity from repair intent",
                6,
                config={"category": "phone_repair_request", "amount": 0},
                compensate={"type": "undo_revenue"},
            ),
            action(
                ActionType.SCHEDULE_REMINDER,
                "SMS confirmation / booking follow-up",
                7,
                config={
                    "hours_before": 0,
                    "channel": "sms",
                    "template": "phone_repair_sms_confirmation",
                    "capability_hint": "BookAppointment + CustomerCommunicationDecision",
                },
                compensate={"type": "cancel_reminder"},
            ),
            action(
                ActionType.NOTIFY,
                "Advisor desk — confirm appointment booking",
                8,
                config={
                    "channel": "in_app",
                    "message": "New phone repair request needs appointment confirmation",
                },
                continue_on_error=True,
            ),
            action(
                ActionType.EMIT_EVENT,
                "Request human escalation if booking incomplete",
                9,
                config={
                    "event_type": DomainEventType.HUMAN_ESCALATION_REQUESTED.value,
                    "payload": {
                        "reason": "phone_repair_booking_confirmation",
                        "scenario": "new_customer_phone_request",
                    },
                },
                continue_on_error=True,
            ),
            action(
                ActionType.UPDATE_DASHBOARD,
                "Refresh operations dashboard",
                10,
                config={
                    "widget": "overview",
                    "invalidate": ["appointments", "crm", "voice", "revenue"],
                },
                continue_on_error=True,
                compensate={"type": "undo_dashboard"},
            ),
        ],
    )
