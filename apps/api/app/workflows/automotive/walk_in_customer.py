"""Scenario 5 — Walk-in Customer.

Flow:
  Temporary customer → Vehicle capture → Inspection workflow → Customer merge
"""

from __future__ import annotations

from uuid import UUID

from app.workflows.automotive.spec import action, build_definition, meta
from app.workflows.enums import ActionType, DomainEventType
from app.workflows.models import WorkflowDefinition

WORKFLOW_ID = UUID("a1111111-1111-4111-8111-111111111105")

SPEC = meta(
    workflow_id=str(WORKFLOW_ID),
    purpose=(
        "Handle counter walk-ins: temporary intake without full customer, capture vehicle, "
        "kick off inspection path, and support later customer merge/convert."
    ),
    trigger=DomainEventType.WALK_IN_CREATED.value,
    capabilities=[
        "CreateVehicle",
        "FindVehicle",
        "CreateCustomer",
        "UpdateCustomer",
        "AddTimeline",
        "WalkInCheckIn",
        "AnalyzeConversation",
        "GenerateRepairRecommendation",
        "BookAppointment",
    ],
    ai_decisions=[
        "VehicleDecision",
        "CustomerDecision",
        "RepairRecommendationDecision",
        "AppointmentDecision",
        "CrmUpdateDecision",
    ],
    events_published=[
        DomainEventType.CRM_UPDATED.value,
        DomainEventType.VEHICLE_CREATED.value,
        DomainEventType.REPAIR_STARTED.value,
        DomainEventType.DASHBOARD_UPDATED.value,
        DomainEventType.HUMAN_ESCALATION_REQUESTED.value,
    ],
    failure_handling=(
        "Retry CRM updates; inspection kickoff emit continue_on_error; "
        "rollback reverses CRM/dashboard side-effects."
    ),
    human_escalation=(
        "Notify advisors of new walk-in; escalate when convert/merge is required before repair."
    ),
)


def build() -> WorkflowDefinition:
    return build_definition(
        workflow_id=WORKFLOW_ID,
        name="Automotive: Walk-in customer",
        description=SPEC["purpose"],
        trigger=DomainEventType.WALK_IN_CREATED,
        tags=["walkin", "intake", "scenario-5"],
        spec=SPEC,
        actions=[
            action(
                ActionType.SET_CONTEXT,
                "Bind walk-in scenario",
                1,
                config={
                    "values": {
                        "scenario": "walk_in_customer",
                        "temporary_customer": True,
                        "expected_decisions": SPEC["ai_decisions"],
                        "required_capabilities": SPEC["required_capabilities"],
                    }
                },
            ),
            action(
                ActionType.UPDATE_CRM,
                "Temporary customer / visit intake",
                2,
                config={
                    "note": "Walk-in created — temporary intake (customer optional)",
                    "fields": {
                        "capability": "WalkInCheckIn|CreateCustomer",
                        "ai_decision": "CustomerDecision",
                        "temporary": True,
                    },
                },
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.UPDATE_CRM,
                "Vehicle capture",
                3,
                config={
                    "note": "Walk-in vehicle captured (VIN/year/make/model/mileage)",
                    "fields": {
                        "capability": "CreateVehicle|FindVehicle",
                        "ai_decision": "VehicleDecision",
                    },
                },
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.EMIT_EVENT,
                "Acknowledge vehicle on visit",
                4,
                config={
                    "event_type": DomainEventType.VEHICLE_CREATED.value,
                    "payload": {"source": "walk_in_customer"},
                },
                continue_on_error=True,
            ),
            action(
                ActionType.EMIT_EVENT,
                "Start inspection workflow path",
                5,
                config={
                    "event_type": DomainEventType.REPAIR_STARTED.value,
                    "payload": {"phase": "inspection", "source": "walk_in"},
                },
            ),
            action(
                ActionType.NOTIFY,
                "Notify advisors — new walk-in",
                6,
                config={
                    "channel": "in_app",
                    "message": "New walk-in arrived — convert/merge customer when ready",
                },
            ),
            action(
                ActionType.UPDATE_CRM,
                "Customer merge checkpoint",
                7,
                config={
                    "note": "Awaiting convert-to-customer / merge with existing CRM record",
                    "fields": {
                        "capability": "UpdateCustomer|CreateCustomer",
                        "ai_decision": "CustomerDecision",
                        "merge_pending": True,
                    },
                },
                continue_on_error=True,
                compensate={"type": "undo_crm"},
            ),
            action(
                ActionType.EMIT_EVENT,
                "Escalate if merge blocked before repair",
                8,
                config={
                    "event_type": DomainEventType.HUMAN_ESCALATION_REQUESTED.value,
                    "payload": {
                        "reason": "walk_in_customer_merge",
                        "scenario": "walk_in_customer",
                    },
                },
                continue_on_error=True,
            ),
            action(
                ActionType.UPDATE_DASHBOARD,
                "Refresh walk-ins widget",
                9,
                config={
                    "widget": "overview",
                    "invalidate": ["walk_ins", "crm", "appointments"],
                },
                continue_on_error=True,
            ),
        ],
    )
