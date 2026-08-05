"""Admin Notification Center — domain events → durable feed."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.admin.event_bridge import on_domain_event
from app.admin.notifications import AdminNotificationService
from app.infrastructure.config import settings
from app.infrastructure.security import create_access_token
from app.main import app
from app.workflows.enums import DomainEventType
from app.workflows.models import DomainEvent


@pytest.fixture
def admin_username(monkeypatch: pytest.MonkeyPatch) -> str:
    username = "platform_admin"
    monkeypatch.setattr(settings, "platform_admin_usernames", username)
    return username


@pytest.fixture
def admin_email(admin_username: str) -> str:
    return admin_username


def _admin_headers(username: str) -> dict[str, str]:
    token = create_access_token(
        subject=str(uuid4()),
        shop_id=None,
        role="platform_admin",
        account_type="platform_admin",
        username=username,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_bridge_persists_signup_event() -> None:
    shop_id = uuid4()
    event = DomainEvent(
        event_type=DomainEventType.SAAS_SIGNUP,
        shop_id=shop_id,
        payload={"shop_slug": "acme-garage", "owner_email": "owner@example.com"},
        source="auth",
        occurred_at=datetime.now(timezone.utc),
    )
    await on_domain_event(event)
    await on_domain_event(event)  # dedupe by shop
    rows = await AdminNotificationService().list(limit=20, event_type="saas.signup")
    matched = [r for r in rows if r.shop_id == shop_id and "acme-garage" in r.message]
    assert len(matched) == 1
    assert matched[0].dedupe_key == f"saas.signup:{shop_id}"
    feed_item = matched[0].to_feed_item()
    assert feed_item["shop_slug"] == "acme-garage"
    assert feed_item["shop_id"] == str(shop_id)


@pytest.mark.asyncio
async def test_bridge_persists_shop_deleted_event() -> None:
    shop_id = uuid4()
    event = DomainEvent(
        event_type=DomainEventType.SAAS_SHOP_DELETED,
        shop_id=shop_id,
        payload={
            "shop_slug": "gone-garage",
            "owner_email": "owner@example.com",
            "deleted_user_count": 1,
        },
        source="compliance",
        occurred_at=datetime.now(timezone.utc),
    )
    await on_domain_event(event)
    await on_domain_event(event)  # dedupe by shop
    rows = await AdminNotificationService().list(limit=20, event_type="saas.shop_deleted")
    matched = [r for r in rows if r.shop_id == shop_id and "gone-garage" in r.message]
    assert len(matched) == 1
    assert matched[0].severity == "major"
    assert matched[0].dedupe_key == f"saas.shop_deleted:{shop_id}"


@pytest.mark.asyncio
async def test_quota_warning_dedupes() -> None:
    shop_id = uuid4()
    period = "2099-01"
    payload = {
        "metric": "ai_calls",
        "usage": 80,
        "limit": 100,
        "percent": 80,
        "period": period,
    }
    for _ in range(2):
        await on_domain_event(
            DomainEvent(
                event_type=DomainEventType.BILLING_QUOTA_WARNING,
                shop_id=shop_id,
                payload=payload,
                source="quotas",
                occurred_at=datetime.now(timezone.utc),
            )
        )
    rows = await AdminNotificationService().list(limit=50, event_type="billing.quota_warning")
    matched = [r for r in rows if r.shop_id == shop_id and r.dedupe_key and period in r.dedupe_key]
    assert len(matched) == 1


@pytest.mark.asyncio
async def test_admin_notifications_feed_shape(admin_email: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/v1/admin/notifications", headers=_admin_headers(admin_email))
    assert res.status_code == 200
    body = res.json()
    assert "notifications" in body
    assert "counts" in body
    assert "event_types" in body
    assert "saas.signup" in body["event_types"]
    assert "saas.member_joined" in body["event_types"]
    assert "saas.shop_deleted" in body["event_types"]
    assert "billing.payment_succeeded" in body["event_types"]
    assert "billing.payment_failed" in body["event_types"]
    assert "billing.quota_warning" in body["event_types"]
    assert "system.error" in body["event_types"]


@pytest.mark.asyncio
async def test_admin_mark_read(admin_email: str) -> None:
    created = await AdminNotificationService().create(
        event_type="billing.payment_failed",
        title="Payment failure",
        message="test mark read",
        severity="major",
        source="test",
        shop_id=uuid4(),
    )
    assert created is not None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/v1/admin/notifications/{created.id}/read",
            headers=_admin_headers(admin_email),
        )
    assert res.status_code == 200
    assert res.json()["status"] == "read"


@pytest.mark.asyncio
async def test_admin_delete_notification(admin_email: str) -> None:
    created = await AdminNotificationService().create(
        event_type="system.error",
        title="Delete me",
        message="test delete",
        severity="major",
        source="test",
        shop_id=uuid4(),
    )
    assert created is not None
    transport = ASGITransport(app=app)
    headers = _admin_headers(admin_email)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.delete(
            f"/v1/admin/notifications/{created.id}",
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["deleted"] is True

        missing = await client.delete(
            f"/v1/admin/notifications/{created.id}",
            headers=headers,
        )
        assert missing.status_code == 404

        bad = await client.delete(
            "/v1/admin/notifications/not-a-uuid",
            headers=headers,
        )
        assert bad.status_code == 400


@pytest.mark.asyncio
async def test_admin_bulk_delete_notifications(admin_email: str) -> None:
    store = AdminNotificationService()
    a = await store.create(
        event_type="system.error",
        title="Bulk A",
        message="bulk delete a",
        severity="info",
        source="test",
        shop_id=uuid4(),
    )
    b = await store.create(
        event_type="system.error",
        title="Bulk B",
        message="bulk delete b",
        severity="info",
        source="test",
        shop_id=uuid4(),
    )
    assert a is not None and b is not None
    transport = ASGITransport(app=app)
    headers = _admin_headers(admin_email)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/admin/notifications/delete",
            headers=headers,
            json={"ids": [str(a.id), str(b.id), str(uuid4())]},
        )
        assert res.status_code == 200
        assert res.json()["deleted"] == 2

        empty = await client.post(
            "/v1/admin/notifications/delete",
            headers=headers,
            json={"ids": []},
        )
        assert empty.status_code == 422


@pytest.mark.asyncio
async def test_register_creates_admin_signup_notification(admin_email: str) -> None:
    from app.workflows.factory import reset_workflow_runtime

    reset_workflow_runtime()
    tag = uuid4().hex[:8]
    slug = f"signup-{tag}"
    transport = ASGITransport(app=app)
    headers = _admin_headers(admin_email)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post(
            "/v1/auth/register",
            json={
                "shop_name": "Signup Garage",
                "shop_slug": slug,
                "auth_method": "phone",
                "owner_phone": f"+1555{int(tag[:7], 16) % 10_000_000:07d}",
                "owner_full_name": "Signup Owner",
                "password": "Password123!",
                "owner_email": f"signup-{tag}@example.com",
            },
        )
        assert reg.status_code == 201, reg.text
        feed = await client.get(
            "/v1/admin/notifications",
            headers=headers,
            params={"event_type": "saas.signup"},
        )
    assert feed.status_code == 200
    notes = feed.json()["notifications"]
    matched = [n for n in notes if slug in (n.get("message") or "")]
    assert matched
    assert "joined_by=Signup Owner" in (matched[0].get("message") or "")


@pytest.mark.asyncio
async def test_invite_staff_creates_member_joined_notification(admin_email: str) -> None:
    from app.workflows.factory import reset_workflow_runtime

    reset_workflow_runtime()
    tag = uuid4().hex[:8]
    slug = f"invite-{tag}"
    transport = ASGITransport(app=app)
    headers = _admin_headers(admin_email)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post(
            "/v1/auth/register",
            json={
                "shop_name": "Invite Garage",
                "shop_slug": slug,
                "auth_method": "phone",
                "owner_phone": f"+1555{int(tag[:7], 16) % 10_000_000:07d}",
                "owner_full_name": "Invite Owner",
                "password": "Password123!",
                "owner_email": f"invite-{tag}@example.com",
            },
        )
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        invited = await client.post(
            "/v1/tenant/members",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "phone": f"+1555{uuid4().int % 10_000_000:07d}",
                "full_name": "Invited Staff",
                "password": "Password123!",
            },
        )
        assert invited.status_code == 201, invited.text
        feed = await client.get(
            "/v1/admin/notifications",
            headers=headers,
            params={"event_type": "saas.member_joined"},
        )
    assert feed.status_code == 200
    notes = feed.json()["notifications"]
    matched = [
        n
        for n in notes
        if slug in (n.get("message") or "") and "Invited Staff" in (n.get("message") or "")
    ]
    assert matched
    assert "via=invite" in (matched[0].get("message") or "")


@pytest.mark.asyncio
async def test_bridge_persists_member_joined_event() -> None:
    shop_id = uuid4()
    user_id = uuid4()
    event = DomainEvent(
        event_type=DomainEventType.SAAS_MEMBER_JOINED,
        shop_id=shop_id,
        payload={
            "shop_slug": "join-garage",
            "joined_by": "Alex Staff",
            "role": "staff",
            "joined_via": "login",
            "user_id": str(user_id),
            "email": "alex@example.com",
        },
        source="auth",
        occurred_at=datetime.now(timezone.utc),
    )
    await on_domain_event(event)
    await on_domain_event(event)  # dedupe
    rows = await AdminNotificationService().list(limit=20, event_type="saas.member_joined")
    matched = [r for r in rows if r.shop_id == shop_id and "Alex Staff" in r.message]
    assert len(matched) == 1
    assert matched[0].dedupe_key == f"saas.member_joined:{shop_id}:{user_id}:login"


@pytest.mark.asyncio
async def test_delete_shop_creates_admin_notification(admin_email: str) -> None:
    from app.workflows.factory import reset_workflow_runtime

    reset_workflow_runtime()
    tag = uuid4().hex[:8]
    slug = f"del-{tag}"
    transport = ASGITransport(app=app)
    headers = _admin_headers(admin_email)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post(
            "/v1/auth/register",
            json={
                "shop_name": "Delete Garage",
                "shop_slug": slug,
                "auth_method": "phone",
                "owner_phone": f"+1555{int(tag[:7], 16) % 10_000_000:07d}",
                "owner_full_name": "Delete Owner",
                "password": "Password123!",
                "owner_email": f"del-{tag}@example.com",
            },
        )
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        deleted = await client.post(
            "/v1/compliance/delete-shop",
            headers={"Authorization": f"Bearer {token}"},
            json={"confirm_slug": slug},
        )
        assert deleted.status_code == 200, deleted.text
        feed = await client.get(
            "/v1/admin/notifications",
            headers=headers,
            params={"event_type": "saas.shop_deleted"},
        )
    assert feed.status_code == 200
    notes = feed.json()["notifications"]
    assert any(slug in (n.get("message") or "") for n in notes)
