"""Scheduling agent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class SchedulingAction(str, Enum):
    LIST_SLOTS = "list_slots"
    BOOK = "book"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    REMINDERS = "reminders"
    NOOP = "noop"


@dataclass(slots=True)
class TimeSlot:
    start: datetime
    end: datetime
    available: bool = True


@dataclass(slots=True)
class AppointmentRecord:
    id: UUID
    shop_id: UUID
    customer_id: UUID | None
    vehicle_id: UUID | None
    start: datetime
    end: datetime
    status: str = "booked"
    notes: str | None = None
    service_id: UUID | None = None
    service_name: str | None = None


@dataclass(slots=True)
class Reminder:
    appointment_id: UUID
    channel: str
    send_at: datetime
    message: str


@dataclass(slots=True)
class SchedulingRequest:
    action: SchedulingAction
    intent: str | None = None
    appointment_id: UUID | None = None
    preferred_start: datetime | None = None
    preferred_end: datetime | None = None
    # none|day|part_of_day|clock — day/part_of_day filter openings; only clock picks a time
    time_precision: str | None = None
    # True when customer asked for the first/earliest available opening
    prefer_earliest: bool = False
    # True when customer asked for the last/latest available opening
    prefer_latest: bool = False
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    reason: str | None = None
    days_ahead: int = 7
    # True when customer confirmed an offered slot (e.g. SMS "YES")
    confirm_booking: bool = False
    # Identified / pre-resolved Service Catalog fields (AI reads; WF writes)
    requested_service: str | None = None
    service_id: UUID | None = None


@dataclass(slots=True)
class SchedulingResult:
    action: str
    success: bool
    appointment: AppointmentRecord | None = None
    available_slots: list[TimeSlot] = field(default_factory=list)
    reminders: list[Reminder] = field(default_factory=list)
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # AI Decision Layer — proposed action; Workflow executes it
    decision: Any | None = None
