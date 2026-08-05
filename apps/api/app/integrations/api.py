"""External Integration Layer HTTP API.

Mounted at ``/v1/integrations``. Does not replace ``/v1/mcp-hub``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user
from app.integrations.enums import IntegrationCapability, IntegrationCategory, IntegrationProvider
from app.integrations.factory import get_integrations_runtime
from app.integrations.models import CapabilityRequest
from app.integrations.security import TenantIsolationError

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


class ConnectBody(BaseModel):
    provider: IntegrationProvider
    credentials: dict[str, str] = Field(default_factory=dict)
    demo: bool = True
    tenant_id: UUID | None = None


class ExecuteBody(BaseModel):
    capability: IntegrationCapability
    provider: IntegrationProvider | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    tenant_id: UUID | None = None
    emit_workflow: bool = True
    invoke_plugins: bool = False


def _service():
    return get_integrations_runtime().service


@router.get("/adapters")
async def list_adapters(
    category: IntegrationCategory | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user.shop_id
    return {"adapters": _service().list_adapters(category)}


@router.get("/capabilities")
async def capability_matrix(
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user.shop_id
    return {"matrix": _service().capability_matrix()}


@router.get("/connections")
async def list_connections(
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {"connections": await _service().list_connections(user.shop_id)}


@router.post("/connect", status_code=status.HTTP_201_CREATED)
async def connect(
    body: ConnectBody,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    tenant_id = body.tenant_id or user.shop_id
    if tenant_id != user.shop_id:
        raise HTTPException(
            status_code=403,
            detail="tenant_id must match authenticated shop_id (no cross-shop access)",
        )
    try:
        conn = await _service().connect(
            shop_id=user.shop_id,
            provider=body.provider,
            credentials=body.credentials,
            tenant_id=tenant_id,
            demo=body.demo,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc).strip("'\""),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": str(conn.id),
        "shop_id": str(conn.shop_id),
        "tenant_id": str(conn.tenant_id),
        "provider": conn.provider.value,
        "status": conn.status.value,
    }


@router.post("/disconnect/{provider}")
async def disconnect(
    provider: IntegrationProvider,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    ok = await _service().disconnect(shop_id=user.shop_id, provider=provider)
    return {"ok": ok, "provider": provider.value}


@router.post("/test/{provider}")
async def test_connection(
    provider: IntegrationProvider,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await _service().test_connection(shop_id=user.shop_id, provider=provider)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/execute")
async def execute_capability(
    body: ExecuteBody,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    tenant_id = body.tenant_id or user.shop_id
    if tenant_id != user.shop_id:
        raise HTTPException(
            status_code=403,
            detail="tenant_id must match authenticated shop_id (no cross-shop access)",
        )
    try:
        result = await _service().execute(
            CapabilityRequest(
                capability=body.capability,
                shop_id=user.shop_id,
                tenant_id=tenant_id,
                payload=body.payload,
                emit_workflow=body.emit_workflow,
                invoke_plugins=body.invoke_plugins,
            ),
            provider=body.provider,
        )
    except (LookupError, TenantIsolationError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.to_dict()
