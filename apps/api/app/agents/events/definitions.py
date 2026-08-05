"""Canonical event payloads exchanged between agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


class AgentEventType(str, Enum):
    INCOMING_MESSAGE = "incoming.message"
    COMMUNICATION_NORMALIZED = "communication.normalized"
    INTENT_DETECTED = "intent.detected"
    CUSTOMER_RESOLVED = "customer.resolved"
    VEHICLE_RESOLVED = "vehicle.resolved"
    SCHEDULING_RESULT = "scheduling.result"
    APPOINTMENT_BOOKED = "appointment.booked"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    CRM_UPDATED = "crm.updated"
    REVENUE_INSIGHTS = "revenue.insights"
    MARKETING_ACTION = "marketing.action"
    SUPERVISOR_DECISION = "supervisor.decision"
    ESCALATION_REQUESTED = "escalation.requested"
    OWNER_SUMMARY = "owner.summary"
    PIPELINE_COMPLETED = "pipeline.completed"


@dataclass(slots=True)
class IncomingMessageEvent:
    channel: str
    raw_content: str
    sender_identifier: str | None = None
    subject: str | None = None
    received_at: datetime | None = None
    attachments: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CommunicationNormalizedEvent:
    channel: str
    direction: str
    body: str
    sender: str | None = None
    recipient: str | None = None
    subject: str | None = None
    received_at: datetime | None = None
    language: str = "en"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IntentDetectedEvent:
    intent: str
    confidence: float
    entities: dict[str, Any] = field(default_factory=dict)
    secondary_intents: list[str] = field(default_factory=list)
    is_emergency: bool = False
    is_complaint: bool = False
    raw_excerpt: str | None = None


@dataclass(slots=True)
class CustomerResolvedEvent:
    customer_id: UUID | None
    is_new: bool
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    merged_from: list[UUID] = field(default_factory=list)
    profile: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VehicleResolvedEvent:
    vehicle_id: UUID | None
    customer_id: UUID | None
    vin: str | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    mileage: int | None = None
    repair_history_count: int = 0
    maintenance_timeline: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SchedulingResultEvent:
    action: str
    success: bool
    appointment_id: UUID | None = None
    slot_start: datetime | None = None
    slot_end: datetime | None = None
    available_slots: list[dict[str, Any]] = field(default_factory=list)
    reminders: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None


@dataclass(slots=True)
class AppointmentBookedEvent:
    appointment_id: UUID
    customer_id: UUID | None
    vehicle_id: UUID | None
    slot_start: datetime
    slot_end: datetime


@dataclass(slots=True)
class AppointmentRescheduledEvent:
    appointment_id: UUID
    previous_start: datetime | None
    new_start: datetime
    new_end: datetime


@dataclass(slots=True)
class AppointmentCancelledEvent:
    appointment_id: UUID
    reason: str | None = None


@dataclass(slots=True)
class CrmUpdatedEvent:
    customer_id: UUID | None
    communication_recorded: bool = False
    repair_updated: bool = False
    timeline_entries: int = 0
    customer_summary: str | None = None


@dataclass(slots=True)
class RevenueInsightsEvent:
    upsell_opportunities: list[dict[str, Any]] = field(default_factory=list)
    declined_estimates: list[dict[str, Any]] = field(default_factory=list)
    maintenance_reminders: list[dict[str, Any]] = field(default_factory=list)
    lost_customer_risk: float = 0.0
    predicted_revenue: Decimal | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MarketingActionEvent:
    action_type: str
    channel: str
    customer_id: UUID | None = None
    template: str | None = None
    scheduled_at: datetime | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SupervisorDecisionEvent:
    status: str
    escalate: bool
    escalation_reason: str | None = None
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    owner_summary: str | None = None
    agent_outputs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EscalationRequestedEvent:
    reason: str
    priority: str = "normal"
    customer_id: UUID | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OwnerSummaryEvent:
    summary: str
    highlights: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PipelineCompletedEvent:
    correlation_id: str
    success: bool
    escalate: bool
    stages: list[str] = field(default_factory=list)
    summary: str | None = None
