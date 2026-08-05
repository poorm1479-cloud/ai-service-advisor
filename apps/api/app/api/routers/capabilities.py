"""Capability invoke HTTP surface — expose plugin capabilities to the dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user
from app.plugins.framework.context import PluginContext
from app.plugins.framework.factory import ensure_default_plugins, invoke_capability
from app.plugins.framework.capability import get_capability_registry

router = APIRouter(prefix="/v1/capabilities", tags=["capabilities"])


class InvokeBody(BaseModel):
    capability: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_capabilities(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    _ = user
    ensure_default_plugins()
    caps = get_capability_registry().list_capabilities()
    return {"capabilities": caps, "count": len(caps)}


@router.post("/invoke")
async def invoke(
    body: InvokeBody,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_default_plugins()
    ctx = PluginContext.for_shop(user.shop_id)
    try:
        result = await invoke_capability(
            body.capability,
            context=ctx,
            shop_id=user.shop_id,
            **dict(body.arguments or {}),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "capability": body.capability,
        "result": _jsonable(result),
        "shop_id": str(user.shop_id),
    }


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "value") and not hasattr(value, "__dict__"):
        try:
            return value.value  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    try:
        from dataclasses import asdict, is_dataclass
        from uuid import UUID
        from datetime import datetime
        from decimal import Decimal
        from enum import Enum

        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value) and not isinstance(value, type):
            return _jsonable(asdict(value))
    except Exception:  # noqa: BLE001
        pass
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _jsonable(value.to_dict())
        except Exception:  # noqa: BLE001
            pass
    if hasattr(value, "__dict__"):
        return {
            k: _jsonable(v)
            for k, v in vars(value).items()
            if not k.startswith("_")
        }
    return str(value)
