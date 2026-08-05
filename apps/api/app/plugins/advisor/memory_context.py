"""Advisor read-only memory context — never writes memory."""

from __future__ import annotations

from typing import Any
from uuid import UUID


async def load_advisor_memory_context(
    shop_id: UUID,
    *,
    customer_id: UUID | None = None,
    vehicle_id: UUID | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Read shop/customer/vehicle/knowledge for AI Service Advisor personalization.

    AI may call this (or SearchMemory / RetrieveKnowledge capabilities).
    AI must not call SaveMemory / Update* — those are Workflow-only.
    """
    from app.plugins.framework.capability import Capability
    from app.plugins.framework.context import PluginContext
    from app.plugins.framework.factory import invoke_capability

    ctx = PluginContext.for_shop(
        shop_id, customer_id=customer_id, vehicle_id=vehicle_id
    )
    out: dict[str, Any] = {"shop_id": str(shop_id), "ai_write_allowed": False}

    try:
        out["shop_preferences"] = await invoke_capability(
            Capability.GET_SHOP_PREFERENCE.value, context=ctx, shop_id=shop_id
        )
    except Exception:  # noqa: BLE001
        out["shop_preferences"] = {}

    if customer_id is not None:
        try:
            out["customer_history"] = await invoke_capability(
                Capability.GET_CUSTOMER_HISTORY.value,
                context=ctx,
                shop_id=shop_id,
                customer_id=customer_id,
            )
        except Exception:  # noqa: BLE001
            out["customer_history"] = {"records": []}

    if vehicle_id is not None:
        try:
            out["vehicle_history"] = await invoke_capability(
                Capability.GET_VEHICLE_HISTORY.value,
                context=ctx,
                shop_id=shop_id,
                vehicle_id=vehicle_id,
            )
        except Exception:  # noqa: BLE001
            out["vehicle_history"] = {"records": []}

    try:
        out["knowledge"] = await invoke_capability(
            Capability.RETRIEVE_KNOWLEDGE.value,
            context=ctx,
            shop_id=shop_id,
            query=query,
            limit=8,
        )
    except Exception:  # noqa: BLE001
        out["knowledge"] = {"documents": []}

    if query:
        try:
            out["search"] = await invoke_capability(
                Capability.SEARCH_MEMORY.value,
                context=ctx,
                shop_id=shop_id,
                query=query,
                customer_id=customer_id,
                vehicle_id=vehicle_id,
            )
        except Exception:  # noqa: BLE001
            out["search"] = {}

    return out
