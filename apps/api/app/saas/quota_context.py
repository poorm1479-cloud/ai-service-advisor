"""Shop-scoped AI quota via contextvar."""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

from app.saas.quotas import QuotaService

_shop_id_var: ContextVar[UUID | None] = ContextVar("asa_quota_shop_id", default=None)


def set_quota_shop_id(shop_id: UUID | None):
    return _shop_id_var.set(shop_id)


def reset_quota_shop_id(token) -> None:
    _shop_id_var.reset(token)


async def consume_ai_quota_if_scoped(amount: int = 1) -> None:
    shop_id = _shop_id_var.get()
    if shop_id is None:
        return
    await QuotaService().consume(shop_id, "ai_calls", amount)
