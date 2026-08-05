"""MCP Integration Hub HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user
from app.mcp_hub.enums import IntegrationProvider, PermissionAction
from app.mcp_hub.factory import McpHubRuntime, get_mcp_hub_runtime
from app.mcp_hub.models import InvokeRequest

router = APIRouter(prefix="/v1/mcp-hub", tags=["mcp-hub"])


def _runtime() -> McpHubRuntime:
    return get_mcp_hub_runtime()


class ManifestOut(BaseModel):
    provider: str
    display_name: str
    description: str
    category: str
    auth_method: str
    api_version: str
    capabilities: list[str]
    required_scopes: list[str]
    credential_fields: list[str]
    available: bool
    future: bool
    docs_url: str | None = None


class ConnectionOut(BaseModel):
    id: UUID
    shop_id: UUID
    provider: str
    name: str
    status: str
    api_version: str
    permissions: list[str]
    credentials_masked: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_error: str | None = None
    last_tested_at: datetime | None = None
    connected_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectionCreate(BaseModel):
    provider: IntegrationProvider
    name: str | None = None
    api_version: str | None = None
    credentials: dict[str, str] = Field(default_factory=dict)
    connect: bool = True
    demo: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectBody(BaseModel):
    credentials: dict[str, str] = Field(default_factory=dict)
    scopes: list[str] | None = None
    demo: bool = False


class InvokeBody(BaseModel):
    provider: IntegrationProvider
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    connection_id: UUID | None = None
    principal: str = "agent"
    api_version: str | None = None
    idempotency_key: str | None = None


class InvokeOut(BaseModel):
    id: UUID
    shop_id: UUID
    provider: str
    connection_id: UUID | None
    tool: str
    status: str
    attempts: int
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    api_version: str
    duration_ms: int
    created_at: datetime | None = None


class LogOut(BaseModel):
    id: UUID
    shop_id: UUID
    provider: str | None
    connection_id: UUID | None
    level: str
    event: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class PermissionOut(BaseModel):
    id: UUID
    shop_id: UUID
    principal: str
    provider: str
    actions: list[str]
    scopes: list[str]
    created_at: datetime | None = None


class PermissionGrantBody(BaseModel):
    principal: str
    provider: IntegrationProvider
    actions: list[PermissionAction]
    scopes: list[str] = Field(default_factory=lambda: ["*"])


class McpToolOut(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any]
    annotations: dict[str, Any] = Field(default_factory=dict)


def _connection_out(c) -> ConnectionOut:
    return ConnectionOut(
        id=c.id,
        shop_id=c.shop_id,
        provider=c.provider.value,
        name=c.name,
        status=c.status.value,
        api_version=c.api_version,
        permissions=list(c.permissions),
        credentials_masked=c.credentials.masked() if c.credentials else {},
        metadata=c.metadata,
        last_error=c.last_error,
        last_tested_at=c.last_tested_at,
        connected_at=c.connected_at,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _invoke_out(r) -> InvokeOut:
    return InvokeOut(
        id=r.id,
        shop_id=r.shop_id,
        provider=r.provider.value,
        connection_id=r.connection_id,
        tool=r.tool,
        status=r.status.value,
        attempts=r.attempts,
        data=r.data,
        error=r.error,
        api_version=r.api_version,
        duration_ms=r.duration_ms,
        created_at=r.created_at,
    )


@router.get("/integrations", response_model=list[ManifestOut])
async def list_integrations(
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> list[ManifestOut]:
    _ = user
    return [
        ManifestOut(
            provider=m.provider.value,
            display_name=m.display_name,
            description=m.description,
            category=m.category.value,
            auth_method=m.auth_method.value,
            api_version=m.api_version,
            capabilities=m.capabilities,
            required_scopes=m.required_scopes,
            credential_fields=m.credential_fields,
            available=m.available,
            future=m.future,
            docs_url=m.docs_url,
        )
        for m in rt.service.list_integrations()
    ]


@router.get("/tools", response_model=list[McpToolOut])
async def list_mcp_tools(
    provider: IntegrationProvider | None = None,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> list[McpToolOut]:
    _ = user
    return [McpToolOut(**d) for d in rt.service.list_mcp_descriptors(provider=provider)]


@router.get("/connections", response_model=list[ConnectionOut])
async def list_connections(
    provider: IntegrationProvider | None = None,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> list[ConnectionOut]:
    return [_connection_out(c) for c in rt.service.connections.list(user.shop_id, provider=provider)]


@router.post("/connections", response_model=ConnectionOut)
async def create_connection(
    body: ConnectionCreate,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> ConnectionOut:
    try:
        conn = await rt.service.create_connection(
            user.shop_id,
            provider=body.provider,
            name=body.name,
            api_version=body.api_version,
            credentials=body.credentials or None,
            connect=body.connect,
            demo=body.demo,
        )
        if body.metadata:
            conn.metadata.update(body.metadata)
            rt.store.save_connection(conn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _connection_out(conn)


@router.get("/connections/{connection_id}", response_model=ConnectionOut)
async def get_connection(
    connection_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> ConnectionOut:
    conn = rt.service.connections.get(user.shop_id, connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return _connection_out(conn)


@router.post("/connections/{connection_id}/connect", response_model=ConnectionOut)
async def connect_connection(
    connection_id: UUID,
    body: ConnectBody,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> ConnectionOut:
    try:
        conn = await rt.service.connections.connect(
            user.shop_id,
            connection_id,
            fields=body.credentials,
            scopes=body.scopes,
            demo=body.demo,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _connection_out(conn)


@router.post("/connections/{connection_id}/disconnect", response_model=ConnectionOut)
async def disconnect_connection(
    connection_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> ConnectionOut:
    try:
        conn = await rt.service.connections.disconnect(user.shop_id, connection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _connection_out(conn)


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        return await rt.service.connections.test(user.shop_id, connection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> dict[str, bool]:
    ok = rt.service.connections.delete(user.shop_id, connection_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"deleted": True}


@router.post("/invoke", response_model=InvokeOut)
async def invoke_tool(
    body: InvokeBody,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> InvokeOut:
    try:
        result = await rt.service.invoke(
            InvokeRequest(
                shop_id=user.shop_id,
                provider=body.provider,
                connection_id=body.connection_id,
                tool=body.tool,
                arguments=body.arguments,
                principal=body.principal,
                api_version=body.api_version,
                idempotency_key=body.idempotency_key,
            )
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _invoke_out(result)


@router.get("/invokes", response_model=list[InvokeOut])
async def list_invokes(
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> list[InvokeOut]:
    return [_invoke_out(r) for r in rt.service.list_invokes(user.shop_id, limit=limit)]


@router.get("/logs", response_model=list[LogOut])
async def list_logs(
    limit: int = Query(100, ge=1, le=500),
    provider: IntegrationProvider | None = None,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> list[LogOut]:
    return [
        LogOut(
            id=e.id,
            shop_id=e.shop_id,
            provider=e.provider.value if e.provider else None,
            connection_id=e.connection_id,
            level=e.level.value,
            event=e.event,
            message=e.message,
            details=e.details,
            created_at=e.created_at,
        )
        for e in rt.service.list_logs(user.shop_id, limit=limit, provider=provider)
    ]


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> list[PermissionOut]:
    return [
        PermissionOut(
            id=p.id,
            shop_id=p.shop_id,
            principal=p.principal,
            provider=p.provider.value,
            actions=[a.value for a in p.actions],
            scopes=p.scopes,
            created_at=p.created_at,
        )
        for p in rt.service.list_permissions(user.shop_id)
    ]


@router.post("/permissions", response_model=PermissionOut)
async def grant_permission(
    body: PermissionGrantBody,
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> PermissionOut:
    p = rt.service.grant_permission(
        user.shop_id,
        principal=body.principal,
        provider=body.provider,
        actions=body.actions,
        scopes=body.scopes,
    )
    return PermissionOut(
        id=p.id,
        shop_id=p.shop_id,
        principal=p.principal,
        provider=p.provider.value,
        actions=[a.value for a in p.actions],
        scopes=p.scopes,
        created_at=p.created_at,
    )


@router.get("/versions")
async def version_matrix(
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> dict[str, list[str]]:
    _ = user
    return rt.service.version_matrix()


@router.get("/metrics/summary")
async def metrics_summary(
    user: CurrentUser = Depends(get_current_user),
    rt: McpHubRuntime = Depends(_runtime),
) -> dict[str, Any]:
    _ = user
    return rt.service.metrics()
