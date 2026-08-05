"""Shared helpers: emit SaaS domain events + durable admin notification fallback."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger("asa.admin.notifications")


async def notify_member_joined(
    *,
    shop_id: UUID,
    shop_slug: str,
    shop_name: str,
    user_id: UUID,
    full_name: str,
    role: str,
    phone: str | None = None,
    email: str | None = None,
    joined_via: str = "invite",
    source: str = "tenant",
) -> None:
    """Notify Admin Notification Center that a shop member joined (invite or first login)."""
    from app.admin.notifications import AdminNotificationService
    from app.workflows.emitter import emit_domain_event
    from app.workflows.enums import DomainEventType

    contact = email or phone or ""
    payload: dict[str, Any] = {
        "shop_slug": shop_slug,
        "shop_name": shop_name,
        "user_id": str(user_id),
        "joined_by": full_name,
        "role": role,
        "phone": phone,
        "email": email,
        "joined_via": joined_via,
    }
    message = (
        f"shop={shop_slug} joined_by={full_name} role={role} via={joined_via} contact={contact}"
    ).strip()
    dedupe = f"saas.member_joined:{shop_id}:{user_id}:{joined_via}"

    try:
        await emit_domain_event(
            shop_id=shop_id,
            event_type=DomainEventType.SAAS_MEMBER_JOINED,
            payload=payload,
            source=source,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("saas.member_joined.emit_failed shop=%s err=%s", shop_slug, exc)

    try:
        await AdminNotificationService().create(
            event_type=DomainEventType.SAAS_MEMBER_JOINED.value,
            title="Member joined",
            message=message,
            severity="info",
            source=source,
            shop_id=shop_id,
            payload={
                **payload,
                "kind": "member_joined",
                "domain_event_type": "saas.member_joined",
            },
            dedupe_key=dedupe,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("saas.member_joined.notify_failed shop=%s err=%s", shop_slug, exc)


async def notify_contact_changed(
    *,
    shop_id: UUID,
    shop_slug: str,
    shop_name: str,
    user_id: UUID,
    full_name: str,
    role: str,
    old_phone: str | None,
    new_phone: str | None,
    old_email: str | None,
    new_email: str | None,
    source: str = "tenant",
) -> None:
    """Notify Admin Notification Center that a member changed phone and/or email."""
    from uuid import uuid4

    from app.admin.notifications import AdminNotificationService
    from app.workflows.emitter import emit_domain_event
    from app.workflows.enums import DomainEventType

    changed: list[str] = []
    if (old_phone or None) != (new_phone or None):
        changed.append("phone")
    if (old_email or None) != (new_email or None):
        changed.append("email")
    if not changed:
        return

    dedupe = f"saas.contact_changed:{user_id}:{uuid4()}"
    payload: dict[str, Any] = {
        "shop_slug": shop_slug,
        "shop_name": shop_name,
        "user_id": str(user_id),
        "full_name": full_name,
        "role": role,
        "changed_fields": changed,
        "old_phone": old_phone,
        "new_phone": new_phone,
        "old_email": old_email,
        "new_email": new_email,
        "dedupe_key": dedupe,
    }
    fields = "+".join(changed)
    message = (
        f"shop={shop_slug} user={full_name} role={role} changed={fields} "
        f"phone={old_phone or '—'}→{new_phone or '—'} "
        f"email={old_email or '—'}→{new_email or '—'}"
    ).strip()

    try:
        await emit_domain_event(
            shop_id=shop_id,
            event_type=DomainEventType.SAAS_CONTACT_CHANGED,
            payload=payload,
            source=source,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("saas.contact_changed.emit_failed shop=%s err=%s", shop_slug, exc)

    try:
        await AdminNotificationService().create(
            event_type=DomainEventType.SAAS_CONTACT_CHANGED.value,
            title="Contact updated",
            message=message,
            severity="info",
            source=source,
            shop_id=shop_id,
            payload={
                **payload,
                "kind": "contact_changed",
                "domain_event_type": "saas.contact_changed",
            },
            dedupe_key=dedupe,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("saas.contact_changed.notify_failed shop=%s err=%s", shop_slug, exc)
