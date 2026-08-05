"""Long-Term AI Memory HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user
from app.memory.enums import MemoryCategory, MemorySource, MemoryType
from app.memory.factory import MemoryRuntime, get_memory_runtime
from app.memory.models import MemoryQuery, RememberRequest

router = APIRouter(prefix="/v1/memory", tags=["memory"])


def _runtime() -> MemoryRuntime:
    return get_memory_runtime()


class RememberBody(BaseModel):
    content: str
    memory_type: MemoryType = MemoryType.CUSTOMER
    category: MemoryCategory = MemoryCategory.GENERAL
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    conversation_id: UUID | None = None
    importance: float = Field(0.5, ge=0.0, le=1.0)
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: MemorySource = MemorySource.MANUAL
    summary: str | None = None


class RetrieveBody(BaseModel):
    text: str | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    memory_types: list[MemoryType] | None = None
    categories: list[MemoryCategory] | None = None
    limit: int = Field(12, ge=1, le=50)


class SeedBody(BaseModel):
    customer_id: UUID
    preferences: list[str] = Field(default_factory=list)
    communication_style: dict[str, Any] = Field(default_factory=dict)
    vehicle_notes: list[str] = Field(default_factory=list)
    declined_estimates: list[str] = Field(default_factory=list)
    appointment_behavior: list[str] = Field(default_factory=list)


class MemoryOut(BaseModel):
    id: UUID
    shop_id: UUID
    memory_type: str
    category: str
    content: str
    summary: str | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    conversation_id: UUID | None = None
    importance: float
    confidence: float
    tags: list[str]
    metadata: dict[str, Any]
    source: str
    access_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_accessed_at: datetime | None = None


class BundleOut(BaseModel):
    shop_id: UUID
    customer_id: UUID | None
    vehicle_id: UUID | None
    hit_count: int
    by_category: dict[str, list[str]]
    preferences: dict[str, Any]
    communication_style: dict[str, Any]
    prompt: str
    memories: list[dict[str, Any]]


def _memory_out(r) -> MemoryOut:
    return MemoryOut(
        id=r.id,
        shop_id=r.shop_id,
        memory_type=r.memory_type.value,
        category=r.category.value,
        content=r.content,
        summary=r.summary,
        customer_id=r.customer_id,
        vehicle_id=r.vehicle_id,
        conversation_id=r.conversation_id,
        importance=r.importance,
        confidence=r.confidence,
        tags=list(r.tags),
        metadata=dict(r.metadata),
        source=r.source.value,
        access_count=r.access_count,
        created_at=r.created_at,
        updated_at=r.updated_at,
        last_accessed_at=r.last_accessed_at,
    )


@router.get("/types")
async def list_types(user: CurrentUser = Depends(get_current_user), rt: MemoryRuntime = Depends(_runtime)) -> dict:
    _ = user
    return {"types": rt.service.types(), "categories": rt.service.categories()}


@router.post("/remember", response_model=MemoryOut)
async def remember(
    body: RememberBody,
    user: CurrentUser = Depends(get_current_user),
    rt: MemoryRuntime = Depends(_runtime),
) -> MemoryOut:
    rec = rt.service.remember(
        RememberRequest(
            shop_id=user.shop_id,
            content=body.content,
            memory_type=body.memory_type,
            category=body.category,
            customer_id=body.customer_id,
            vehicle_id=body.vehicle_id,
            conversation_id=body.conversation_id,
            importance=body.importance,
            confidence=body.confidence,
            tags=body.tags,
            metadata=body.metadata,
            source=body.source,
            summary=body.summary,
        )
    )
    return _memory_out(rec)


@router.post("/retrieve", response_model=BundleOut)
async def retrieve(
    body: RetrieveBody,
    user: CurrentUser = Depends(get_current_user),
    rt: MemoryRuntime = Depends(_runtime),
) -> BundleOut:
    bundle = rt.service.retrieve(
        MemoryQuery(
            shop_id=user.shop_id,
            text=body.text,
            customer_id=body.customer_id,
            vehicle_id=body.vehicle_id,
            memory_types=body.memory_types,
            categories=body.categories,
            limit=body.limit,
        )
    )
    data = bundle.to_dict()
    return BundleOut(
        shop_id=bundle.shop_id,
        customer_id=bundle.customer_id,
        vehicle_id=bundle.vehicle_id,
        hit_count=data["hit_count"],
        by_category=data["by_category"],
        preferences=data["preferences"],
        communication_style=data["communication_style"],
        prompt=data["prompt"],
        memories=data["memories"],
    )


@router.get("/memories", response_model=list[MemoryOut])
async def list_memories(
    customer_id: UUID | None = None,
    vehicle_id: UUID | None = None,
    memory_type: MemoryType | None = None,
    category: MemoryCategory | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    rt: MemoryRuntime = Depends(_runtime),
) -> list[MemoryOut]:
    rows = rt.service.list_memories(
        user.shop_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        memory_type=memory_type,
        category=category,
        limit=limit,
    )
    return [_memory_out(r) for r in rows]


@router.get("/memories/{memory_id}", response_model=MemoryOut)
async def get_memory(
    memory_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: MemoryRuntime = Depends(_runtime),
) -> MemoryOut:
    rec = rt.service.get(user.shop_id, memory_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _memory_out(rec)


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: MemoryRuntime = Depends(_runtime),
) -> dict[str, bool]:
    if not rt.service.delete(user.shop_id, memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True}


@router.post("/seed", response_model=list[MemoryOut])
async def seed_profile(
    body: SeedBody,
    user: CurrentUser = Depends(get_current_user),
    rt: MemoryRuntime = Depends(_runtime),
) -> list[MemoryOut]:
    rows = rt.service.seed_customer_profile(
        user.shop_id,
        body.customer_id,
        preferences=body.preferences,
        communication_style=body.communication_style or {"tone": "friendly"},
        vehicle_notes=body.vehicle_notes,
        declined_estimates=body.declined_estimates,
        appointment_behavior=body.appointment_behavior,
    )
    return [_memory_out(r) for r in rows]


@router.get("/metrics/summary")
async def metrics_summary(
    user: CurrentUser = Depends(get_current_user),
    rt: MemoryRuntime = Depends(_runtime),
) -> dict[str, Any]:
    _ = user
    return rt.service.metrics()
