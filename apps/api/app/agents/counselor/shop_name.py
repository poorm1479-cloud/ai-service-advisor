"""Resolve shop display name for counselor greetings (best-effort)."""

from __future__ import annotations

from uuid import UUID

# Test / in-memory overrides (shop_id → name)
_SHOP_NAMES: dict[UUID, str] = {}


def register_shop_name(shop_id: UUID, name: str) -> None:
    if name.strip():
        _SHOP_NAMES[shop_id] = name.strip()


def clear_shop_names() -> None:
    _SHOP_NAMES.clear()


async def resolve_shop_name(shop_id: UUID) -> str | None:
    cached = _SHOP_NAMES.get(shop_id)
    if cached:
        return cached
    try:
        from app.infrastructure.database import SessionLocal
        from app.infrastructure.models import ShopModel
        from sqlalchemy import select

        async with SessionLocal() as session:
            row = (
                await session.execute(select(ShopModel.name).where(ShopModel.id == shop_id))
            ).scalar_one_or_none()
            if row:
                return str(row)
    except Exception:  # pragma: no cover — unit tests / no DB
        return None
    return None
