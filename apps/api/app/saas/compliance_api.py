"""Compliance + platform admin routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.admin.deps import require_platform_admin
from app.api.deps import CurrentUser, require_owner
from app.saas.access_review import AccessReviewService
from app.saas.billing import BillingService
from app.saas.compliance import ComplianceService
from app.saas.incidents import StatusIncidentService

compliance_router = APIRouter(prefix="/v1/compliance", tags=["compliance"])
platform_router = APIRouter(prefix="/v1/platform", tags=["platform"])


class DeleteShopRequest(BaseModel):
    confirm_slug: str = Field(min_length=2, max_length=100)


class IncidentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    summary: str = ""
    severity: str = Field(default="minor", pattern=r"^(minor|major|critical)$")
    status: str = Field(default="investigating", pattern=r"^(investigating|identified|monitoring|resolved)$")
    affected_components: list[str] = Field(default_factory=list)


class IncidentUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(investigating|identified|monitoring|resolved)$")
    summary: str | None = None
    resolve: bool = False


@compliance_router.get("/export")
async def export_shop_data(current: CurrentUser = Depends(require_owner())) -> dict:
    return await ComplianceService().export_shop(current.shop_id)


@compliance_router.post("/delete-shop")
async def delete_shop(
    body: DeleteShopRequest,
    current: CurrentUser = Depends(require_owner()),
) -> dict:
    from app.infrastructure.database import SessionLocal
    from app.infrastructure.models import ShopModel

    async with SessionLocal() as session:
        shop = await session.get(ShopModel, current.shop_id)
        if shop is None:
            raise HTTPException(status_code=404, detail="Shop not found")
        if shop.slug != body.confirm_slug.strip().lower():
            raise HTTPException(status_code=400, detail="confirm_slug does not match shop slug")
    await ComplianceService().delete_shop(current.shop_id)
    return {"ok": True, "deleted_shop_id": str(current.shop_id)}


@platform_router.get("/access-review")
async def platform_access_review(_: str = Depends(require_platform_admin)) -> dict:
    return await AccessReviewService().export()


@platform_router.get("/overview")
async def platform_overview(_: str = Depends(require_platform_admin)) -> dict:
    """Server admin snapshot: readiness, tenant counts, open incidents."""
    from datetime import datetime, timezone

    from app.ops.healthchecks import readiness

    ready = await readiness()
    shops = await BillingService().list_shops_summary()
    incidents = await StatusIncidentService().list_public(limit=50)
    open_incidents = [i for i in incidents if i.status != "resolved"]
    by_status: dict[str, int] = {}
    for s in shops:
        key = str(s.get("status") or "none")
        by_status[key] = by_status.get(key, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": ready.get("environment"),
        "readiness": ready,
        "shops": {
            "total": len(shops),
            "by_status": by_status,
            "suspended": by_status.get("suspended", 0),
        },
        "incidents": {
            "open": len(open_incidents),
            "total": len(incidents),
        },
    }


@platform_router.get("/shops")
async def platform_list_shops(_: str = Depends(require_platform_admin)) -> dict:
    shops = await BillingService().list_shops_summary()
    return {"shops": shops}


async def _set_shop_subscription_status(shop_id: str, new_status: str) -> dict:
    from app.infrastructure.database import SessionLocal
    from app.saas.billing import ShopSubscriptionModel
    from sqlalchemy import select

    async with SessionLocal() as session:
        sub = await session.scalar(
            select(ShopSubscriptionModel).where(ShopSubscriptionModel.shop_id == UUID(shop_id))
        )
        if sub is None:
            raise HTTPException(status_code=404, detail="Subscription not found")
        sub.status = new_status
        await session.commit()
    return {"ok": True, "shop_id": shop_id, "status": new_status}


@platform_router.post("/shops/{shop_id}/suspend")
async def platform_suspend_shop(shop_id: str, _: str = Depends(require_platform_admin)) -> dict:
    return await _set_shop_subscription_status(shop_id, "suspended")


@platform_router.post("/shops/{shop_id}/activate")
async def platform_activate_shop(shop_id: str, _: str = Depends(require_platform_admin)) -> dict:
    return await _set_shop_subscription_status(shop_id, "active")


@platform_router.get("/incidents")
async def platform_list_incidents(_: str = Depends(require_platform_admin)) -> dict:
    items = await StatusIncidentService().list_public(limit=50)
    return {
        "incidents": [
            {
                "id": str(i.id),
                "title": i.title,
                "summary": i.summary,
                "severity": i.severity,
                "status": i.status,
                "affected_components": i.affected_components,
                "started_at": i.started_at.isoformat() if i.started_at else None,
                "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            }
            for i in items
        ]
    }


@platform_router.post("/incidents", status_code=status.HTTP_201_CREATED)
async def platform_create_incident(
    body: IncidentCreate,
    _: str = Depends(require_platform_admin),
) -> dict:
    item = await StatusIncidentService().create(
        title=body.title,
        summary=body.summary,
        severity=body.severity,
        status=body.status,
        affected_components=body.affected_components,
    )
    return {
        "id": str(item.id),
        "title": item.title,
        "status": item.status,
        "severity": item.severity,
    }


@platform_router.patch("/incidents/{incident_id}")
async def platform_update_incident(
    incident_id: UUID,
    body: IncidentUpdate,
    _: str = Depends(require_platform_admin),
) -> dict:
    item = await StatusIncidentService().update(
        incident_id,
        status=body.status,
        summary=body.summary,
        resolve=body.resolve,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {
        "id": str(item.id),
        "title": item.title,
        "status": item.status,
        "severity": item.severity,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
    }
