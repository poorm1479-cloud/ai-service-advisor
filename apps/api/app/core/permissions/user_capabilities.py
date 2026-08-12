"""Map principal roles ↔ default capability sets (backward compatible)."""

from __future__ import annotations

from app.core.permissions.capabilities import (
    ALL_STAFF_CAPABILITIES,
    DEFAULT_STAFF_CAPABILITIES,
    StaffCapability,
    capability_values,
)
from app.domain.enums import UserRole, normalize_user_role


# Legacy job-title roles → modern principal
LEGACY_ROLE_TO_PRINCIPAL: dict[str, UserRole] = {
    "owner": UserRole.OWNER,
    "staff": UserRole.STAFF,
    "ai_agent": UserRole.AI_AGENT,
    # Deprecated job titles (kept for JWT / DB dual-read)
    "manager": UserRole.STAFF,
    "service_advisor": UserRole.STAFF,
    "mechanic": UserRole.STAFF,
    "receptionist": UserRole.STAFF,
    "technician": UserRole.STAFF,
    "serviceadvisor": UserRole.STAFF,
}


# Optional legacy specialty defaults (still Staff; small shops usually get all)
_LEGACY_SPECIALTY_CAPS: dict[str, tuple[StaffCapability, ...]] = {
    "mechanic": (
        StaffCapability.VEHICLE_MANAGEMENT,
        StaffCapability.INSPECTION_INPUT,
        StaffCapability.REPAIR_STATUS_UPDATE,
        StaffCapability.APPOINTMENT_MANAGEMENT,
    ),
    "technician": (
        StaffCapability.VEHICLE_MANAGEMENT,
        StaffCapability.INSPECTION_INPUT,
        StaffCapability.REPAIR_STATUS_UPDATE,
    ),
    "receptionist": (
        StaffCapability.CUSTOMER_MANAGEMENT,
        StaffCapability.APPOINTMENT_MANAGEMENT,
        StaffCapability.CUSTOMER_COMMUNICATION,
        StaffCapability.PAYMENT_HANDLING,
    ),
    "service_advisor": (
        StaffCapability.CUSTOMER_MANAGEMENT,
        StaffCapability.VEHICLE_MANAGEMENT,
        StaffCapability.APPOINTMENT_MANAGEMENT,
        StaffCapability.ESTIMATE_CREATION,
        StaffCapability.CUSTOMER_COMMUNICATION,
        StaffCapability.INSPECTION_INPUT,
    ),
    "manager": ALL_STAFF_CAPABILITIES,
}


def default_capabilities_for_role(
    role: UserRole | str,
    *,
    legacy_raw: str | None = None,
    full_staff: bool = True,
) -> list[str]:
    """Resolve default capability strings for a principal role.

    Staff defaults exclude Calls & Messages / Payments (owner opts in on invite).
    Pass full_staff=False to use legacy specialty subsets when migrating.
    """
    principal = normalize_user_role(role)
    raw = (legacy_raw or (role if isinstance(role, str) else role.value)).lower().strip()

    if principal == UserRole.OWNER:
        return capability_values(ALL_STAFF_CAPABILITIES)

    if principal == UserRole.AI_AGENT:
        return capability_values(
            (
                StaffCapability.CUSTOMER_COMMUNICATION,
                StaffCapability.APPOINTMENT_MANAGEMENT,
                StaffCapability.ESTIMATE_CREATION,
                StaffCapability.REPAIR_STATUS_UPDATE,
                StaffCapability.CUSTOMER_MANAGEMENT,
                StaffCapability.VEHICLE_MANAGEMENT,
            )
        )

    # Staff
    if not full_staff and raw in _LEGACY_SPECIALTY_CAPS:
        return capability_values(_LEGACY_SPECIALTY_CAPS[raw])
    return capability_values(DEFAULT_STAFF_CAPABILITIES)


def parse_capabilities(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    valid = {c.value for c in StaffCapability}
    out: list[str] = []
    for item in raw:
        key = str(item).strip().lower()
        if key in valid and key not in out:
            out.append(key)
    return out


def merge_capabilities(*sets: list[str] | None) -> list[str]:
    merged: list[str] = []
    for s in sets:
        for c in parse_capabilities(s):
            if c not in merged:
                merged.append(c)
    return merged
