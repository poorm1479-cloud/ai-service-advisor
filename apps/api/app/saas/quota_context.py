"""Shop-scoped AI quota via contextvar."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator
from uuid import UUID

from app.saas.quotas import QuotaService

_shop_id_var: ContextVar[UUID | None] = ContextVar("asa_quota_shop_id", default=None)


def set_quota_shop_id(shop_id: UUID | None):
    return _shop_id_var.set(shop_id)


def reset_quota_shop_id(token) -> None:
    _shop_id_var.reset(token)


def get_quota_shop_id() -> UUID | None:
    return _shop_id_var.get()


@contextmanager
def quota_shop_scope(shop_id: UUID | None) -> Iterator[None]:
    """Bind shop for billing-enforced ai_calls quota (see consume_ai_quota_if_scoped)."""
    token = set_quota_shop_id(shop_id)
    try:
        yield
    finally:
        reset_quota_shop_id(token)


@contextmanager
def shop_ai_scope(shop_id: UUID | None) -> Iterator[None]:
    """Scope both plan quota (ai_calls) and usage monitoring (tokens/cost)."""
    from app.saas.usage_tracking import usage_shop_scope

    with quota_shop_scope(shop_id), usage_shop_scope(shop_id):
        yield


async def consume_ai_quota_if_scoped(amount: int = 1) -> None:
    shop_id = _shop_id_var.get()
    if shop_id is None:
        return
    await QuotaService().consume(shop_id, "ai_calls", amount)
