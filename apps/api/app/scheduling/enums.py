"""Scheduling domain enums."""

from enum import Enum


class AppointmentStatus(str, Enum):
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class AppointmentPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"


class RepairType(str, Enum):
    OIL_CHANGE = "oil_change"
    BRAKES = "brakes"
    TIRES = "tires"
    DIAGNOSTIC = "diagnostic"
    INSPECTION = "inspection"
    ENGINE = "engine"
    TRANSMISSION = "transmission"
    ELECTRICAL = "electrical"
    BODY = "body"
    GENERAL = "general"
    WALK_IN = "walk_in"


class VehicleCategory(str, Enum):
    SUV = "suv"
    CROSSOVER = "crossover"
    PICKUP = "pickup"
    SEDAN = "sedan"
    TRUCK = "truck"
    MINIVAN = "minivan"
    VAN = "van"
    CARGO_VAN = "cargo_van"
    HATCHBACK = "hatchback"
    COUPE = "coupe"
    CONVERTIBLE = "convertible"
    HYBRID = "hybrid"
    PHEV = "phev"
    EV = "ev"
    MOTORCYCLE = "motorcycle"
    RV = "rv"
    TRAILER = "trailer"
    FLEET = "fleet"
    COMMERCIAL = "commercial"
    OTHER = "other"


class AppointmentSource(str, Enum):
    DASHBOARD = "dashboard"
    SMS = "sms"
    PHONE = "phone"
    WALK_IN = "walk_in"
    WEBSITE = "website"
    AGENT = "agent"
