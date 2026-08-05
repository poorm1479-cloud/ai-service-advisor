"""Audit logging."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.enterprise.enums import AuditAction
from app.enterprise.models import AuditLogEntry
from app.enterprise.store import EnterpriseStorePort


class AuditLogger:
    def __init__(self, store: EnterpriseStorePort) -> None:
        self._store = store

    def log(
        self,
        *,
        organization_id: UUID | None,
        action: AuditAction,
        resource: str,
        actor_user_id: UUID | None = None,
        actor_email: str | None = None,
        resource_id: str | None = None,
        location_id: UUID | None = None,
        ip: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            id=uuid4(),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            action=action,
            resource=resource,
            resource_id=resource_id,
            location_id=location_id,
            ip=ip,
            details=details or {},
        )
        return self._store.append_audit(entry)
