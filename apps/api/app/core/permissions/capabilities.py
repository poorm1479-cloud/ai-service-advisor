"""Staff capability catalog — function-based permissions (not job titles)."""

from __future__ import annotations

from enum import StrEnum


class StaffCapability(StrEnum):
    """Capabilities a Staff member may hold in any combination."""

    CUSTOMER_MANAGEMENT = "customer_management"
    VEHICLE_MANAGEMENT = "vehicle_management"
    APPOINTMENT_MANAGEMENT = "appointment_management"
    INSPECTION_INPUT = "inspection_input"
    ESTIMATE_CREATION = "estimate_creation"
    REPAIR_STATUS_UPDATE = "repair_status_update"
    CUSTOMER_COMMUNICATION = "customer_communication"
    PAYMENT_HANDLING = "payment_handling"


# Human-readable labels for UI / docs
CAPABILITY_LABELS: dict[StaffCapability, str] = {
    StaffCapability.CUSTOMER_MANAGEMENT: "Customer management",
    StaffCapability.VEHICLE_MANAGEMENT: "Vehicle management",
    StaffCapability.APPOINTMENT_MANAGEMENT: "Appointment management",
    StaffCapability.INSPECTION_INPUT: "Inspection input",
    StaffCapability.ESTIMATE_CREATION: "Estimate creation",
    StaffCapability.REPAIR_STATUS_UPDATE: "Repair status update",
    StaffCapability.CUSTOMER_COMMUNICATION: "Customer communication",
    StaffCapability.PAYMENT_HANDLING: "Payment handling",
}


ALL_STAFF_CAPABILITIES: tuple[StaffCapability, ...] = tuple(StaffCapability)

# Standard staff invite defaults — Calls & Messages / Payments require explicit grant.
DEFAULT_STAFF_CAPABILITIES: tuple[StaffCapability, ...] = tuple(
    c
    for c in ALL_STAFF_CAPABILITIES
    if c
    not in (
        StaffCapability.CUSTOMER_COMMUNICATION,
        StaffCapability.PAYMENT_HANDLING,
    )
)


def capability_values(caps: list[StaffCapability] | tuple[StaffCapability, ...] | None = None) -> list[str]:
    items = caps if caps is not None else ALL_STAFF_CAPABILITIES
    return [c.value for c in items]
