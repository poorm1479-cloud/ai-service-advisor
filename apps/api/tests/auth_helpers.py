"""Shared auth helpers for tests (phone signup without OTP)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def register_shop_via_otp(
    client: AsyncClient,
    *,
    suffix: str | None = None,
    shop_name: str | None = None,
    shop_slug: str | None = None,
    owner_full_name: str = "Owner",
    password: str = "password123",
    email: str | None = None,
) -> dict:
    tag = (suffix or uuid.uuid4().hex[:8]).replace("-", "")[:8]
    phone = f"+1555{int(tag[:7], 16) % 10_000_000:07d}"
    # Unique name by default so parallel tests don't collide on slug/name uniqueness.
    resolved_name = (shop_name or f"Test Garage {tag}").strip()
    payload = {
        "shop_name": resolved_name,
        "auth_method": "phone",
        "owner_phone": phone,
        "owner_full_name": owner_full_name,
        "password": password,
    }
    if shop_slug:
        payload["shop_slug"] = shop_slug
    if email:
        payload["owner_email"] = email
    else:
        payload["owner_email"] = f"owner-{tag}@example.com"
    register = await client.post("/v1/auth/register", json=payload)
    assert register.status_code == 201, register.text
    body = register.json()
    body["_test_phone"] = phone
    body["_test_slug"] = body.get("shop_slug") or shop_slug or ""
    body["_test_email"] = payload["owner_email"]
    body["_test_shop_name"] = resolved_name
    return body
