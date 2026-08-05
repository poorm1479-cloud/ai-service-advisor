"""Workflow engine enumerations."""

from __future__ import annotations

from enum import StrEnum


class DomainEventType(StrEnum):
    CUSTOMER_CREATED = "customer.created"
    VEHICLE_CREATED = "vehicle.created"
    REPAIR_STARTED = "repair.started"
    REPAIR_FINISHED = "repair.finished"
    ESTIMATE_SENT = "estimate.sent"
    ESTIMATE_APPROVED = "estimate.approved"
    ESTIMATE_DECLINED = "estimate.declined"
    INVOICE_PAID = "invoice.paid"
    APPOINTMENT_BOOKED = "appointment.booked"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    WALK_IN_CREATED = "walk_in.created"
    CUSTOMER_RETURNED = "customer.returned"
    REVIEW_SUBMITTED = "review.submitted"
    # Cascading / system events produced by actions
    REMINDER_SCHEDULED = "reminder.scheduled"
    CRM_UPDATED = "crm.updated"
    REVENUE_UPDATED = "revenue.updated"
    DASHBOARD_UPDATED = "dashboard.updated"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_ROLLED_BACK = "workflow.rolled_back"
    # Cross-module orchestration events (Workflow Engine as coordinator)
    MAINTENANCE_REMINDER_REQUESTED = "marketing.maintenance_reminder_requested"
    MARKETING_ACTION_REQUESTED = "marketing.action_requested"
    HUMAN_ESCALATION_REQUESTED = "workflow.human_escalation_requested"
    INBOUND_MESSAGE_RECEIVED = "communication.inbound_received"
    WORKFLOW_PAUSED = "workflow.paused"
    WORKFLOW_RESUMED = "workflow.resumed"
    REVENUE_OPPORTUNITY_DETECTED = "revenue.opportunity_detected"
    # External Integration Layer
    INTEGRATION_CUSTOMER_IMPORTED = "integration.ImportCustomerData"
    INTEGRATION_VEHICLE_IMPORTED = "integration.ImportVehicleData"
    INTEGRATION_REPAIR_IMPORTED = "integration.ImportRepairHistory"
    INTEGRATION_APPOINTMENT_SYNCED = "integration.SyncAppointment"
    INTEGRATION_INVOICE_SYNCED = "integration.SyncInvoice"
    INTEGRATION_PAYMENT_SYNCED = "integration.SyncPayment"
    INTEGRATION_MESSAGE_SENT = "integration.SendCustomerMessage"
    INTEGRATION_MESSAGE_RECEIVED = "integration.ReceiveCustomerMessage"
    # Platform / SaaS admin notification center
    SAAS_SIGNUP = "saas.signup"
    SAAS_MEMBER_JOINED = "saas.member_joined"
    SAAS_SHOP_DELETED = "saas.shop_deleted"
    SAAS_CONTACT_CHANGED = "saas.contact_changed"
    BILLING_PAYMENT_SUCCEEDED = "billing.payment_succeeded"
    BILLING_PAYMENT_FAILED = "billing.payment_failed"
    BILLING_QUOTA_WARNING = "billing.quota_warning"
    SYSTEM_ERROR = "system.error"


class ConditionOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    CONTAINS = "contains"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


class ActionType(StrEnum):
    SCHEDULE_REMINDER = "schedule_reminder"
    UPDATE_CRM = "update_crm"
    UPDATE_REVENUE = "update_revenue"
    UPDATE_DASHBOARD = "update_dashboard"
    EMIT_EVENT = "emit_event"
    LOG = "log"
    NOTIFY = "notify"
    DELAY = "delay"
    SET_CONTEXT = "set_context"


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_RETRY = "waiting_retry"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"
    RETRYING = "retrying"


class RetryState(StrEnum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    EXHAUSTED = "exhausted"
    CANCELLED = "cancelled"
