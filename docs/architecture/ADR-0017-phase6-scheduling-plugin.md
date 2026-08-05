# ADR 0017 — Architecture Refactor Phase 6: Scheduling Plugin

Status: Accepted (Architecture Refactor Phase 6)

## Context

Scheduling business logic already exists (`app/scheduling`, `app/agents/scheduling`). Workflow must not call those modules directly. Phase 5 introduced the Plugin Framework; Phase 4 wrapped CRM. Phase 6 wraps Scheduling the same way.

## Decision

Expose Scheduling as `plugins/scheduling` implementing `IPlugin` + `ISchedulingPlugin`. Workflow applies appointment decisions only through the Capability Registry (`FindAvailableSlot`, `BookAppointment`, …). Existing stores and intelligence services are wrapped, not rewritten. Public `/v1` appointment APIs and frontend remain unchanged.

## Consequences

- Workflow → Capability Registry → Plugin Registry → Scheduling Plugin → existing services
- SMS/Voice continue to resolve the agent store via Workflow coordinator → Scheduling Plugin
- Intelligence runtime attaches lazily to avoid circular imports at plugin bootstrap

## Capability mapping

| Capability | Plugin service |
|---|---|
| FindAvailableSlot | AvailabilityPluginService |
| CheckAvailability | AvailabilityPluginService |
| ValidateAppointment | AvailabilityPluginService |
| DetectConflict | AvailabilityPluginService |
| EstimateDuration | AvailabilityPluginService |
| BookAppointment | AppointmentPluginService |
| RescheduleAppointment | AppointmentPluginService |
| CancelAppointment | AppointmentPluginService |
| AppointmentHistory | AppointmentPluginService |
| WalkInCheckIn | Appointment + Availability |
| AssignMechanic | MechanicPluginService |
| AssignBay | BayPluginService |

## Package layout

```
plugins/scheduling/
  plugin.py
  interfaces.py
  factory.py
  appointment/
  calendar/
  mechanic/
  bay/
  availability/
```
