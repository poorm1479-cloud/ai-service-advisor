"""Revenue intelligence enumerations."""

from __future__ import annotations

from enum import StrEnum


class OpportunityKind(StrEnum):
    LOST_CUSTOMER = "lost_customer"
    LIKELY_RETURN = "likely_to_return"
    LIKELY_ACCEPT = "likely_to_accept_repairs"
    MAINTENANCE_OVERDUE = "maintenance_overdue"
    BATTERY = "battery_replacement"
    BRAKES = "brake_replacement"
    OIL_CHANGE = "oil_change"
    TIRES = "tires"
    ALIGNMENT = "alignment"
    FLUIDS = "fluids"
    DECLINED_ESTIMATE = "declined_estimate"


class OpportunityHorizon(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class OpportunityStatus(StrEnum):
    OPEN = "open"
    CONTACTED = "contacted"
    WON = "won"
    LOST = "lost"
    DISMISSED = "dismissed"


class ContactChannel(StrEnum):
    SMS = "sms"
    EMAIL = "email"
    PHONE = "phone"
    IN_APP = "in_app"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class HealthBand(StrEnum):
    CRITICAL = "critical"
    AT_RISK = "at_risk"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"
