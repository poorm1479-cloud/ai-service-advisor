"""Permission service — capability checks for Owner / Staff / AI Agent."""

from __future__ import annotations

from typing import Iterable

from app.core.permissions.capabilities import StaffCapability
from app.core.permissions.user_capabilities import (
    default_capabilities_for_role,
    parse_capabilities,
)
from app.domain.enums import UserRole, normalize_user_role


class PermissionDenied(Exception):
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message)
        self.message = message


class PermissionService:
    """Authorize actions by principal role + capability set."""

    def resolve_capabilities(
        self,
        *,
        role: UserRole | str,
        stored_capabilities: list[str] | None = None,
        legacy_raw_role: str | None = None,
    ) -> list[str]:
        principal = normalize_user_role(role)
        stored = parse_capabilities(stored_capabilities)
        if principal == UserRole.OWNER:
            # Owner always has full operational surface
            return default_capabilities_for_role(UserRole.OWNER)
        if stored:
            return stored
        return default_capabilities_for_role(principal, legacy_raw=legacy_raw_role)

    def has_capability(
        self,
        *,
        role: UserRole | str,
        capabilities: list[str] | None,
        required: StaffCapability | str,
    ) -> bool:
        principal = normalize_user_role(role)
        if principal == UserRole.OWNER:
            return True
        need = required.value if isinstance(required, StaffCapability) else str(required)
        resolved = self.resolve_capabilities(role=principal, stored_capabilities=capabilities)
        return need in resolved

    def has_any(
        self,
        *,
        role: UserRole | str,
        capabilities: list[str] | None,
        required: Iterable[StaffCapability | str],
    ) -> bool:
        return any(
            self.has_capability(role=role, capabilities=capabilities, required=r) for r in required
        )

    def has_all(
        self,
        *,
        role: UserRole | str,
        capabilities: list[str] | None,
        required: Iterable[StaffCapability | str],
    ) -> bool:
        return all(
            self.has_capability(role=role, capabilities=capabilities, required=r) for r in required
        )

    def require(
        self,
        *,
        role: UserRole | str,
        capabilities: list[str] | None,
        required: StaffCapability | str | Iterable[StaffCapability | str],
        require_all: bool = False,
    ) -> None:
        if isinstance(required, (StaffCapability, str)):
            ok = self.has_capability(role=role, capabilities=capabilities, required=required)
        elif require_all:
            ok = self.has_all(role=role, capabilities=capabilities, required=required)
        else:
            ok = self.has_any(role=role, capabilities=capabilities, required=required)
        if not ok:
            raise PermissionDenied("Missing required capability")

    def is_owner(self, role: UserRole | str) -> bool:
        return normalize_user_role(role) == UserRole.OWNER

    def can_manage_tenant(self, role: UserRole | str) -> bool:
        """Tenant / membership administration — Owner only."""
        return self.is_owner(role)

    def can_access_dashboard(self, role: UserRole | str, capabilities: list[str] | None) -> bool:
        principal = normalize_user_role(role)
        if principal in {UserRole.OWNER, UserRole.STAFF}:
            return True
        # AI Agent may read ops metrics if it has communication or appointment caps
        return self.has_any(
            role=principal,
            capabilities=capabilities,
            required=(
                StaffCapability.CUSTOMER_COMMUNICATION,
                StaffCapability.APPOINTMENT_MANAGEMENT,
            ),
        )

    def can_use_workflows(self, role: UserRole | str, capabilities: list[str] | None) -> bool:
        principal = normalize_user_role(role)
        if principal == UserRole.OWNER:
            return True
        return self.has_any(
            role=principal,
            capabilities=capabilities,
            required=list(StaffCapability),
        )


_permission_service: PermissionService | None = None


def get_permission_service() -> PermissionService:
    global _permission_service
    if _permission_service is None:
        _permission_service = PermissionService()
    return _permission_service
