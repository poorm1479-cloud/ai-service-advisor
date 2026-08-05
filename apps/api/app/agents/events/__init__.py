"""Typed event definitions for the agent event bus."""

from app.agents.events.definitions import (
    AgentEventType,
    AppointmentCancelledEvent,
    AppointmentBookedEvent,
    AppointmentRescheduledEvent,
    CommunicationNormalizedEvent,
    CrmUpdatedEvent,
    CustomerResolvedEvent,
    EscalationRequestedEvent,
    IncomingMessageEvent,
    IntentDetectedEvent,
    MarketingActionEvent,
    OwnerSummaryEvent,
    PipelineCompletedEvent,
    RevenueInsightsEvent,
    SchedulingResultEvent,
    SupervisorDecisionEvent,
    VehicleResolvedEvent,
)
from app.agents.events.envelope import EventEnvelope

__all__ = [
    "AgentEventType",
    "AppointmentBookedEvent",
    "AppointmentCancelledEvent",
    "AppointmentRescheduledEvent",
    "CommunicationNormalizedEvent",
    "CrmUpdatedEvent",
    "CustomerResolvedEvent",
    "EscalationRequestedEvent",
    "EventEnvelope",
    "IncomingMessageEvent",
    "IntentDetectedEvent",
    "MarketingActionEvent",
    "OwnerSummaryEvent",
    "PipelineCompletedEvent",
    "RevenueInsightsEvent",
    "SchedulingResultEvent",
    "SupervisorDecisionEvent",
    "VehicleResolvedEvent",
]
