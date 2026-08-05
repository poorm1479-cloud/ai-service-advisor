"""Default seeded workflows (global templates)."""

from __future__ import annotations

from uuid import uuid4

from app.workflows.automotive import automotive_workflows
from app.workflows.enums import ActionType, DomainEventType, WorkflowStatus
from app.workflows.models import RetryPolicy, WorkflowAction, WorkflowCondition, WorkflowDefinition
from app.workflows.enums import ConditionOperator
from app.workflows.store import WorkflowStorePort


def default_workflows() -> list[WorkflowDefinition]:
    """Appointment Created → Reminder → CRM → Revenue → Dashboard."""
    appointment_booked = WorkflowDefinition(
        id=uuid4(),
        shop_id=None,
        name="Appointment booked cascade",
        description="Reminder → CRM → Revenue → Dashboard on appointment.booked",
        trigger=DomainEventType.APPOINTMENT_BOOKED,
        conditions=[],
        actions=[
            WorkflowAction(
                type=ActionType.SCHEDULE_REMINDER,
                name="Schedule reminder",
                order=1,
                config={"hours_before": 24, "channel": "sms", "template": "appointment_reminder"},
                compensate={"type": "cancel_reminder"},
            ),
            WorkflowAction(
                type=ActionType.UPDATE_CRM,
                name="Update CRM",
                order=2,
                config={"note": "Appointment booked"},
                compensate={"type": "undo_crm"},
            ),
            WorkflowAction(
                type=ActionType.UPDATE_REVENUE,
                name="Update revenue",
                order=3,
                config={"category": "appointment"},
                compensate={"type": "undo_revenue"},
            ),
            WorkflowAction(
                type=ActionType.UPDATE_DASHBOARD,
                name="Refresh dashboard",
                order=4,
                config={"widget": "overview", "invalidate": ["appointments", "revenue"]},
                compensate={"type": "undo_dashboard"},
            ),
        ],
        retry=RetryPolicy(max_attempts=3, backoff_ms=500),
        status=WorkflowStatus.ACTIVE,
        tags=["default", "appointments"],
    )

    appointment_cancelled = WorkflowDefinition(
        id=uuid4(),
        shop_id=None,
        name="Appointment cancelled cascade",
        description="CRM + revenue + dashboard on cancellation",
        trigger=DomainEventType.APPOINTMENT_CANCELLED,
        actions=[
            WorkflowAction(
                type=ActionType.UPDATE_CRM,
                name="Log cancellation in CRM",
                order=1,
                config={"note": "Appointment cancelled"},
            ),
            WorkflowAction(
                type=ActionType.UPDATE_REVENUE,
                name="Adjust revenue forecast",
                order=2,
                config={"category": "cancellation"},
            ),
            WorkflowAction(
                type=ActionType.UPDATE_DASHBOARD,
                name="Refresh dashboard",
                order=3,
                config={"widget": "overview"},
            ),
        ],
        status=WorkflowStatus.ACTIVE,
        tags=["default", "appointments"],
    )

    invoice_paid = WorkflowDefinition(
        id=uuid4(),
        shop_id=None,
        name="Invoice paid cascade",
        description="Revenue + CRM + dashboard when invoice is paid",
        trigger=DomainEventType.INVOICE_PAID,
        actions=[
            WorkflowAction(type=ActionType.UPDATE_REVENUE, name="Record payment", order=1),
            WorkflowAction(type=ActionType.UPDATE_CRM, name="CRM payment note", order=2),
            WorkflowAction(type=ActionType.UPDATE_DASHBOARD, name="Refresh dashboard", order=3),
        ],
        status=WorkflowStatus.ACTIVE,
        tags=["default", "billing"],
    )

    walk_in = WorkflowDefinition(
        id=uuid4(),
        shop_id=None,
        name="Walk-in created",
        description="CRM + dashboard for new walk-ins",
        trigger=DomainEventType.WALK_IN_CREATED,
        actions=[
            WorkflowAction(type=ActionType.UPDATE_CRM, name="CRM walk-in", order=1),
            WorkflowAction(type=ActionType.UPDATE_DASHBOARD, name="Refresh dashboard", order=2),
            WorkflowAction(
                type=ActionType.NOTIFY,
                name="Notify advisors",
                order=3,
                config={"channel": "in_app", "message": "New walk-in arrived"},
            ),
        ],
        status=WorkflowStatus.ACTIVE,
        tags=["default", "walkins"],
    )

    customer_created = WorkflowDefinition(
        id=uuid4(),
        shop_id=None,
        name="Customer created welcome",
        trigger=DomainEventType.CUSTOMER_CREATED,
        conditions=[
            WorkflowCondition(field="name", operator=ConditionOperator.EXISTS),
        ],
        actions=[
            WorkflowAction(
                type=ActionType.LOG,
                name="Log new customer",
                order=1,
                config={"message": "New customer onboarded"},
            ),
            WorkflowAction(type=ActionType.UPDATE_CRM, name="Seed CRM timeline", order=2),
            WorkflowAction(type=ActionType.UPDATE_DASHBOARD, name="Refresh dashboard", order=3),
        ],
        status=WorkflowStatus.ACTIVE,
        tags=["default", "crm"],
    )

    maintenance_reminder = WorkflowDefinition(
        id=uuid4(),
        shop_id=None,
        name="Maintenance reminder requested",
        description="Log + CRM note when revenue requests a maintenance marketing action",
        trigger=DomainEventType.MAINTENANCE_REMINDER_REQUESTED,
        actions=[
            WorkflowAction(
                type=ActionType.LOG,
                name="Log maintenance reminder orchestration",
                order=1,
                config={"message": "Maintenance reminder requested via Workflow coordinator"},
            ),
            WorkflowAction(
                type=ActionType.UPDATE_CRM,
                name="CRM maintenance reminder note",
                order=2,
                config={"note": "Maintenance reminder requested"},
            ),
        ],
        status=WorkflowStatus.ACTIVE,
        tags=["default", "marketing", "orchestration"],
    )

    return [
        appointment_booked,
        appointment_cancelled,
        invoice_paid,
        walk_in,
        customer_created,
        maintenance_reminder,
        *automotive_workflows(),
    ]


async def seed_default_workflows(store: WorkflowStorePort) -> list[WorkflowDefinition]:
    existing = await store.list_workflows(shop_id=uuid4())  # lists globals + none for random shop
    # Prefer check by name among globals
    names = {w.name for w in existing if w.shop_id is None}
    seeded: list[WorkflowDefinition] = []
    for wf in default_workflows():
        if wf.name in names:
            continue
        seeded.append(await store.save_workflow(wf))
    return seeded
