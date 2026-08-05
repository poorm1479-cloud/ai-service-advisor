"""Bridge workflow domain events → durable admin notifications."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.admin.notifications import PLATFORM_SHOP_ID, AdminNotificationService
from app.workflows.enums import DomainEventType
from app.workflows.models import DomainEvent

logger = logging.getLogger("asa.admin.notifications")

# Event types that land in the Admin Notification Center.
_WATCHED: frozenset[str] = frozenset(
    {
        DomainEventType.SAAS_SIGNUP.value,
        DomainEventType.SAAS_MEMBER_JOINED.value,
        DomainEventType.SAAS_SHOP_DELETED.value,
        DomainEventType.SAAS_CONTACT_CHANGED.value,
        DomainEventType.BILLING_PAYMENT_SUCCEEDED.value,
        DomainEventType.BILLING_PAYMENT_FAILED.value,
        DomainEventType.BILLING_QUOTA_WARNING.value,
        DomainEventType.SYSTEM_ERROR.value,
        DomainEventType.WORKFLOW_FAILED.value,
    }
)

_META: dict[str, dict[str, str]] = {
    DomainEventType.SAAS_SIGNUP.value: {
        "severity": "info",
        "title": "New signup",
        "kind": "new_signup",
    },
    DomainEventType.SAAS_MEMBER_JOINED.value: {
        "severity": "info",
        "title": "Member joined",
        "kind": "member_joined",
    },
    DomainEventType.SAAS_SHOP_DELETED.value: {
        "severity": "major",
        "title": "Shop deleted",
        "kind": "shop_deleted",
    },
    DomainEventType.SAAS_CONTACT_CHANGED.value: {
        "severity": "info",
        "title": "Contact updated",
        "kind": "contact_changed",
    },
    DomainEventType.BILLING_PAYMENT_SUCCEEDED.value: {
        "severity": "info",
        "title": "Payment success",
        "kind": "payment_success",
    },
    DomainEventType.BILLING_PAYMENT_FAILED.value: {
        "severity": "major",
        "title": "Payment failure",
        "kind": "payment_failure",
    },
    DomainEventType.BILLING_QUOTA_WARNING.value: {
        "severity": "major",
        "title": "Token limit warning",
        "kind": "token_limit_warning",
    },
    DomainEventType.SYSTEM_ERROR.value: {
        "severity": "critical",
        "title": "System error",
        "kind": "system_error",
    },
    DomainEventType.WORKFLOW_FAILED.value: {
        "severity": "major",
        "title": "System error",
        "kind": "system_error",
    },
}


def _event_type_value(event: DomainEvent) -> str:
    et = event.event_type
    return et.value if hasattr(et, "value") else str(et)


def _message_for(event_type: str, shop_id: UUID, payload: dict[str, Any]) -> str:
    slug = str(payload.get("shop_slug") or payload.get("slug") or "").strip()
    shop = slug or (str(shop_id) if shop_id != PLATFORM_SHOP_ID else "platform")
    if event_type == DomainEventType.SAAS_SIGNUP.value:
        joined_by = payload.get("joined_by") or payload.get("owner_full_name") or ""
        contact = payload.get("owner_email") or payload.get("owner_phone") or ""
        role = payload.get("role") or "owner"
        if joined_by:
            return f"shop={shop} joined_by={joined_by} role={role} contact={contact}".strip()
        return f"shop={shop} owner={contact}".strip()
    if event_type == DomainEventType.SAAS_MEMBER_JOINED.value:
        joined_by = payload.get("joined_by") or payload.get("full_name") or ""
        role = payload.get("role") or "staff"
        via = payload.get("joined_via") or "invite"
        contact = payload.get("email") or payload.get("phone") or ""
        return (
            f"shop={shop} joined_by={joined_by} role={role} via={via} contact={contact}"
        ).strip()
    if event_type == DomainEventType.SAAS_SHOP_DELETED.value:
        owner = payload.get("owner_email") or payload.get("owner_phone") or ""
        deleted_users = payload.get("deleted_user_count")
        suffix = f" deleted_users={deleted_users}" if deleted_users is not None else ""
        return f"shop={shop} owner={owner}{suffix}".strip()
    if event_type == DomainEventType.SAAS_CONTACT_CHANGED.value:
        name = payload.get("full_name") or ""
        fields = payload.get("changed_fields") or []
        changed = "+".join(fields) if isinstance(fields, list) else str(fields or "")
        return (
            f"shop={shop} user={name} changed={changed} "
            f"phone={payload.get('old_phone') or '—'}→{payload.get('new_phone') or '—'} "
            f"email={payload.get('old_email') or '—'}→{payload.get('new_email') or '—'}"
        ).strip()
    if event_type == DomainEventType.BILLING_PAYMENT_SUCCEEDED.value:
        return f"shop={shop} plan={payload.get('plan_id', '')}".strip()
    if event_type == DomainEventType.BILLING_PAYMENT_FAILED.value:
        return f"shop={shop} status={payload.get('status', 'past_due')}".strip()
    if event_type == DomainEventType.BILLING_QUOTA_WARNING.value:
        metric = payload.get("metric", "ai_calls")
        usage = payload.get("usage")
        limit = payload.get("limit")
        pct = payload.get("percent")
        return f"shop={shop} {metric}={usage}/{limit} ({pct}%)"
    if event_type == DomainEventType.SYSTEM_ERROR.value:
        return str(payload.get("summary") or payload.get("error") or payload.get("title") or "System error")
    if event_type == DomainEventType.WORKFLOW_FAILED.value:
        return f"shop={shop} error={payload.get('error', 'workflow failed')}"
    return f"shop={shop}"


def _dedupe_key(event_type: str, shop_id: UUID, payload: dict[str, Any]) -> str | None:
    if event_type == DomainEventType.SAAS_SIGNUP.value:
        return f"saas.signup:{shop_id}"
    if event_type == DomainEventType.SAAS_MEMBER_JOINED.value:
        user_id = payload.get("user_id") or ""
        via = payload.get("joined_via") or "invite"
        if user_id:
            return f"saas.member_joined:{shop_id}:{user_id}:{via}"
        return None
    if event_type == DomainEventType.SAAS_SHOP_DELETED.value:
        return f"saas.shop_deleted:{shop_id}"
    if event_type == DomainEventType.SAAS_CONTACT_CHANGED.value:
        key = payload.get("dedupe_key")
        return str(key) if key else None
    if event_type == DomainEventType.BILLING_QUOTA_WARNING.value:
        metric = payload.get("metric", "ai_calls")
        period = payload.get("period", "")
        return f"quota_warning:{shop_id}:{metric}:{period}"
    if event_type == DomainEventType.SYSTEM_ERROR.value and payload.get("incident_id"):
        return f"system_error:incident:{payload['incident_id']}"
    if event_type == DomainEventType.WORKFLOW_FAILED.value and payload.get("run_id"):
        return f"workflow_failed:{payload['run_id']}"
    return None


async def on_domain_event(event: DomainEvent) -> None:
    event_type = _event_type_value(event)
    if event_type not in _WATCHED:
        return
    meta = _META.get(event_type) or {
        "severity": "info",
        "title": event_type,
        "kind": event_type,
    }
    payload = dict(event.payload or {})
    severity = str(payload.pop("severity", None) or meta["severity"])
    title = str(payload.pop("title", None) or meta["title"])
    stored_type = (
        DomainEventType.SYSTEM_ERROR.value
        if event_type == DomainEventType.WORKFLOW_FAILED.value
        else event_type
    )
    try:
        await AdminNotificationService().create(
            event_type=stored_type,
            title=title,
            message=_message_for(event_type, event.shop_id, payload),
            severity=severity,
            source=event.source or "workflow",
            shop_id=None if event.shop_id == PLATFORM_SHOP_ID else event.shop_id,
            payload={**payload, "kind": meta["kind"], "domain_event_type": event_type},
            dedupe_key=_dedupe_key(event_type, event.shop_id, payload),
            occurred_at=event.occurred_at,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin_notification.persist_failed type=%s err=%s", event_type, exc)


def wire_admin_notification_bridge(bus: Any) -> None:
    """Attach observer to a WorkflowEventBus (idempotent)."""
    observe = getattr(bus, "observe", None)
    if not callable(observe):
        return
    observe(on_domain_event)
