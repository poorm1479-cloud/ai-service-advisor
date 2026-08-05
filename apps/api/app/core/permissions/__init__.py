"""Capability-based shop permissions (Owner / Staff / AI Agent)."""

from app.core.permissions.capabilities import (
    ALL_STAFF_CAPABILITIES,
    CAPABILITY_LABELS,
    StaffCapability,
    capability_values,
)
from app.core.permissions.permission_service import (
    PermissionDenied,
    PermissionService,
    get_permission_service,
)
from app.core.permissions.user_capabilities import (
    LEGACY_ROLE_TO_PRINCIPAL,
    default_capabilities_for_role,
    parse_capabilities,
)

__all__ = [
    "ALL_STAFF_CAPABILITIES",
    "CAPABILITY_LABELS",
    "LEGACY_ROLE_TO_PRINCIPAL",
    "PermissionDenied",
    "PermissionService",
    "StaffCapability",
    "capability_values",
    "default_capabilities_for_role",
    "get_permission_service",
    "parse_capabilities",
]
