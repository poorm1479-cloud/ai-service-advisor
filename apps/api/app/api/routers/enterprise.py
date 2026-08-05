"""Enterprise HTTP API — multi-location, SSO, policies, gateway, central dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user
from app.enterprise.enums import EnterpriseRole, PolicyEffect, PolicyScope, SsoProvider
from app.enterprise.factory import EnterpriseRuntime, get_enterprise_runtime
from app.enterprise.gateway import GatewayDenied, RateLimited

router = APIRouter(prefix="/v1/enterprise", tags=["enterprise"])


def _rt() -> EnterpriseRuntime:
    return get_enterprise_runtime()


class OrgCreate(BaseModel):
    name: str
    slug: str
    franchise: bool = True


class LocationCreate(BaseModel):
    shop_id: UUID
    name: str
    code: str
    region: str | None = None
    timezone: str = "America/Los_Angeles"


class MembershipGrant(BaseModel):
    user_id: UUID
    email: str
    role: EnterpriseRole
    location_ids: list[UUID] = Field(default_factory=list)


class BrandUpdate(BaseModel):
    product_name: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None
    support_email: str | None = None
    custom_domain: str | None = None
    login_tagline: str | None = None
    hide_powered_by: bool | None = None


class PolicyCreate(BaseModel):
    name: str
    effect: PolicyEffect
    scope: PolicyScope = PolicyScope.ORGANIZATION
    rules: dict[str, Any] = Field(default_factory=dict)
    location_id: UUID | None = None
    priority: int = 100
    enabled: bool = True


class PolicyEval(BaseModel):
    intent: str | None = None
    channel: str | None = None
    location_id: UUID | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class SsoConfigure(BaseModel):
    provider: SsoProvider
    client_id: str
    issuer_url: str
    domains: list[str] = Field(default_factory=list)
    role_mapping: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    metadata_url: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None
    require_sso: bool = False


class SsoBegin(BaseModel):
    email: str | None = None


class SsoBeginPublic(BaseModel):
    org_slug: str = Field(min_length=1, max_length=128)
    email: str | None = None


class SsoComplete(BaseModel):
    state: str
    email: str | None = None
    code: str | None = None
    external_role: str | None = None


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["enterprise:read"])
    rate_limit_rpm: int = 120


class GatewayAuthorize(BaseModel):
    path: str
    api_key: str | None = None
    role: EnterpriseRole | None = None
    client_id: str = "web"


class OrgOut(BaseModel):
    id: UUID
    name: str
    slug: str
    franchise: bool
    created_at: datetime | None = None


class LocationOut(BaseModel):
    id: UUID
    organization_id: UUID
    shop_id: UUID
    name: str
    code: str
    region: str | None
    timezone: str
    active: bool


def _brand_out(brand) -> dict[str, Any]:
    return {
        "organization_id": str(brand.organization_id),
        "product_name": brand.product_name,
        "primary_color": brand.primary_color,
        "accent_color": brand.accent_color,
        "logo_url": brand.logo_url,
        "favicon_url": brand.favicon_url,
        "support_email": brand.support_email,
        "custom_domain": brand.custom_domain,
        "login_tagline": brand.login_tagline,
        "hide_powered_by": brand.hide_powered_by,
        "css_vars": brand.css_vars,
    }

@router.get("/roles")
async def role_hierarchy(user: CurrentUser = Depends(get_current_user), rt: EnterpriseRuntime = Depends(_rt)):
    _ = user
    return {"roles": rt.service.role_hierarchy()}


@router.post("/organizations", response_model=OrgOut)
async def create_org(
    body: OrgCreate,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
) -> OrgOut:
    try:
        org = rt.service.create_organization(
            name=body.name,
            slug=body.slug,
            franchise=body.franchise,
            owner_user_id=user.user_id,
            owner_email=user.email or "owner@example.com",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrgOut(id=org.id, name=org.name, slug=org.slug, franchise=org.franchise, created_at=org.created_at)


@router.post("/organizations/seed", response_model=OrgOut)
async def seed_org(
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
) -> OrgOut:
    org = rt.service.seed_demo(
        owner_user_id=user.user_id,
        owner_email=user.email or "owner@example.com",
        primary_shop_id=user.shop_id,
    )
    return OrgOut(id=org.id, name=org.name, slug=org.slug, franchise=org.franchise, created_at=org.created_at)


@router.get("/organizations", response_model=list[OrgOut])
async def list_orgs(user: CurrentUser = Depends(get_current_user), rt: EnterpriseRuntime = Depends(_rt)):
    _ = user
    return [
        OrgOut(id=o.id, name=o.name, slug=o.slug, franchise=o.franchise, created_at=o.created_at)
        for o in rt.service.list_orgs()
    ]


@router.post("/organizations/{org_id}/locations", response_model=LocationOut)
async def add_location(
    org_id: UUID,
    body: LocationCreate,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
) -> LocationOut:
    try:
        loc = rt.service.add_location(
            org_id,
            shop_id=body.shop_id,
            name=body.name,
            code=body.code,
            region=body.region,
            timezone=body.timezone,
            actor_user_id=user.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LocationOut(
        id=loc.id,
        organization_id=loc.organization_id,
        shop_id=loc.shop_id,
        name=loc.name,
        code=loc.code,
        region=loc.region,
        timezone=loc.timezone,
        active=loc.active,
    )


@router.get("/organizations/{org_id}/locations", response_model=list[LocationOut])
async def list_locations(
    org_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    try:
        locs = rt.service.list_locations(org_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        LocationOut(
            id=l.id,
            organization_id=l.organization_id,
            shop_id=l.shop_id,
            name=l.name,
            code=l.code,
            region=l.region,
            timezone=l.timezone,
            active=l.active,
        )
        for l in locs
    ]


@router.post("/organizations/{org_id}/memberships")
async def grant_membership(
    org_id: UUID,
    body: MembershipGrant,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    m = rt.service.grant_membership(
        org_id,
        user_id=body.user_id,
        email=body.email,
        role=body.role,
        location_ids=body.location_ids,
        actor_role=EnterpriseRole.FRANCHISE_OWNER,
    )
    return {
        "id": str(m.id),
        "role": m.role.value,
        "email": m.email,
        "location_ids": [str(x) for x in m.location_ids],
    }


@router.get("/organizations/{org_id}/memberships")
async def list_memberships(
    org_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    return [
        {
            "id": str(m.id),
            "user_id": str(m.user_id),
            "email": m.email,
            "role": m.role.value,
            "location_ids": [str(x) for x in m.location_ids],
        }
        for m in rt.service.list_memberships(org_id)
    ]


@router.get("/organizations/{org_id}/dashboard")
async def central_dashboard(
    org_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    try:
        dash = rt.service.central_dashboard(org_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "organization_id": str(dash.organization_id),
        "organization_name": dash.organization_name,
        "generated_at": dash.generated_at.isoformat(),
        "location_count": dash.location_count,
        "kpis": dash.kpis,
        "locations": [
            {
                "location_id": str(l.location_id),
                "location_name": l.location_name,
                "code": l.code,
                "revenue": l.revenue,
                "appointments": l.appointments,
                "ai_success_rate": l.ai_success_rate,
                "retention": l.retention,
                "customers": l.customers,
            }
            for l in dash.locations
        ],
        "brand": dash.brand,
        "policy_count": dash.policy_count,
        "audit_recent": dash.audit_recent,
        "sso_enabled": dash.sso_enabled,
    }


@router.get("/organizations/{org_id}/franchise-analytics")
async def franchise_analytics(
    org_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    fa = rt.service.franchise_analytics(org_id)
    return {
        "organization_id": str(fa.organization_id),
        "generated_at": fa.generated_at.isoformat(),
        "totals": fa.totals,
        "rankings": fa.rankings,
        "locations": [
            {
                "location_id": str(l.location_id),
                "location_name": l.location_name,
                "code": l.code,
                "revenue": l.revenue,
                "appointments": l.appointments,
                "ai_success_rate": l.ai_success_rate,
                "retention": l.retention,
                "customers": l.customers,
            }
            for l in fa.locations
        ],
    }


@router.put("/organizations/{org_id}/brand")
async def update_brand(
    org_id: UUID,
    body: BrandUpdate,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    brand = rt.service.update_brand(org_id, **body.model_dump(exclude_unset=True))
    return _brand_out(brand)


@router.get("/organizations/{org_id}/brand")
async def get_brand(
    org_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    brand = rt.service.get_brand(org_id)
    if brand is None:
        raise HTTPException(status_code=404, detail="Brand not found")
    return _brand_out(brand)


@router.post("/organizations/{org_id}/policies")
async def create_policy(
    org_id: UUID,
    body: PolicyCreate,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    p = rt.service.save_policy(
        org_id,
        name=body.name,
        effect=body.effect,
        scope=body.scope,
        rules=body.rules,
        location_id=body.location_id,
        priority=body.priority,
        enabled=body.enabled,
    )
    return {
        "id": str(p.id),
        "name": p.name,
        "effect": p.effect.value,
        "scope": p.scope.value,
        "rules": p.rules,
        "priority": p.priority,
        "enabled": p.enabled,
    }


@router.get("/organizations/{org_id}/policies")
async def list_policies(
    org_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "effect": p.effect.value,
            "scope": p.scope.value,
            "rules": p.rules,
            "priority": p.priority,
            "enabled": p.enabled,
            "location_id": str(p.location_id) if p.location_id else None,
        }
        for p in rt.service.list_policies(org_id)
    ]


@router.post("/organizations/{org_id}/policies/evaluate")
async def evaluate_policy(
    org_id: UUID,
    body: PolicyEval,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    return rt.service.evaluate_policy(
        org_id,
        intent=body.intent,
        channel=body.channel,
        location_id=body.location_id,
        context=body.context,
    )


@router.put("/organizations/{org_id}/sso")
async def configure_sso(
    org_id: UUID,
    body: SsoConfigure,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    cfg = rt.service.configure_sso(
        org_id,
        provider=body.provider,
        client_id=body.client_id,
        issuer_url=body.issuer_url,
        domains=body.domains,
        role_mapping=body.role_mapping,
        enabled=body.enabled,
        metadata_url=body.metadata_url,
        client_secret=body.client_secret,
        redirect_uri=body.redirect_uri,
        require_sso=body.require_sso,
    )
    return {
        "provider": cfg.provider.value,
        "enabled": cfg.enabled,
        "client_id": cfg.client_id,
        "issuer_url": cfg.issuer_url,
        "domains": cfg.domains,
        "oidc_ready": bool((cfg.metadata or {}).get("client_secret")),
        "require_sso": cfg.require_sso,
    }


@router.post("/organizations/{org_id}/sso/begin")
async def sso_begin(
    org_id: UUID,
    body: SsoBegin,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    try:
        return rt.service.sso_begin(org_id, email=body.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/organizations/{org_id}/sso/complete")
async def sso_complete(
    org_id: UUID,
    body: SsoComplete,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    _ = org_id
    try:
        return await rt.service.sso_complete(
            state=body.state,
            email=body.email,
            code=body.code,
            external_role=body.external_role,
            user_id=user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sso/callback")
async def sso_callback_public(
    body: SsoComplete,
    rt: EnterpriseRuntime = Depends(_rt),
):
    """IdP redirect target — no app session required (OIDC code or demo state)."""
    try:
        return await rt.service.sso_complete(
            state=body.state,
            email=body.email,
            code=body.code,
            external_role=body.external_role,
            user_id=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sso/status")
async def sso_status_public(
    org_slug: str = Query(min_length=1, max_length=128),
    rt: EnterpriseRuntime = Depends(_rt),
):
    """Public probe: whether an organization has SSO enabled (for login UI)."""
    try:
        return rt.service.sso_status_by_slug(org_slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sso/begin")
async def sso_begin_public(
    body: SsoBeginPublic,
    rt: EnterpriseRuntime = Depends(_rt),
):
    """Start SSO from login page using organization slug (no app session)."""
    try:
        return rt.service.sso_begin_by_slug(body.org_slug, email=body.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/organizations/{org_id}/audit")
async def list_audit(
    org_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    return [
        {
            "id": str(e.id),
            "action": e.action.value,
            "resource": e.resource,
            "resource_id": e.resource_id,
            "actor_email": e.actor_email,
            "details": e.details,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rt.service.list_audit(org_id, limit=limit)
    ]


@router.post("/organizations/{org_id}/api-keys")
async def create_api_key(
    org_id: UUID,
    body: ApiKeyCreate,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    _ = user
    key, raw = rt.service.create_api_key(
        org_id,
        name=body.name,
        scopes=body.scopes,
        rate_limit_rpm=body.rate_limit_rpm,
    )
    return {
        "id": str(key.id),
        "name": key.name,
        "key_prefix": key.key_prefix,
        "api_key": raw,
        "scopes": key.scopes,
        "rate_limit_rpm": key.rate_limit_rpm,
    }


@router.get("/gateway/routes")
async def gateway_routes(user: CurrentUser = Depends(get_current_user), rt: EnterpriseRuntime = Depends(_rt)):
    _ = user
    return [
        {
            "id": r.id,
            "path_prefix": r.path_prefix,
            "upstream": r.upstream,
            "auth": r.auth.value,
            "required_role": r.required_role.value if r.required_role else None,
            "rate_limit_rpm": r.rate_limit_rpm,
            "enabled": r.enabled,
            "description": r.description,
        }
        for r in rt.gateway.list_routes()
    ]


@router.post("/gateway/authorize")
async def gateway_authorize(
    body: GatewayAuthorize,
    user: CurrentUser = Depends(get_current_user),
    rt: EnterpriseRuntime = Depends(_rt),
):
    try:
        return rt.service.gateway_authorize(
            path=body.path,
            org_id=None,
            api_key=body.api_key,
            role=body.role or EnterpriseRole.ORG_ADMIN,
            client_id=body.client_id or str(user.user_id),
        )
    except GatewayDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.get("/metrics/summary")
async def metrics(user: CurrentUser = Depends(get_current_user), rt: EnterpriseRuntime = Depends(_rt)):
    _ = user
    return rt.service.metrics()
