"""API route registration — core routes load eagerly; heavy AI routes defer."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

_api_router: APIRouter | None = None
_deferred_targets: set[int] = set()


def include_core_routers(target: FastAPI | APIRouter) -> None:
    """Lightweight routes needed for health, auth, and shop bootstrap."""
    from app.api.routers import auth, capabilities, health, tenant
    from app.shop_setup.api import router as shop_setup_router

    target.include_router(health.router)
    target.include_router(auth.router)
    target.include_router(tenant.router)
    target.include_router(shop_setup_router)
    target.include_router(capabilities.router)


def include_deferred_routers(target: FastAPI | APIRouter) -> None:
    """Heavy SMS/voice/workflow/admin surface — import only when registering."""
    target_id = id(target)
    if target_id in _deferred_targets:
        return
    from app.admin.api import router as admin_router
    from app.api.routers import (
        agents,
        analytics,
        appointments,
        customers,
        enterprise,
        executive,
        imports,
        marketing,
        mcp_hub,
        memory,
        revenue,
        sms_inbox,
        twilio_voice_webhooks,
        twilio_webhooks,
        vehicles,
        voice_calls,
        voice_notes,
        walkins,
        workflows,
    )
    from app.dashboard.api import router as dashboard_router
    from app.integrations.api import router as integrations_router
    from app.saas.api import router as billing_router
    from app.saas.compliance_api import compliance_router, platform_router

    target.include_router(customers.router)
    target.include_router(vehicles.router)
    target.include_router(walkins.router)
    target.include_router(voice_notes.router)
    target.include_router(agents.router)
    target.include_router(twilio_webhooks.router)
    target.include_router(sms_inbox.router)
    target.include_router(twilio_voice_webhooks.router)
    target.include_router(voice_calls.router)
    target.include_router(appointments.router)
    target.include_router(imports.router)
    target.include_router(workflows.router)
    target.include_router(revenue.router)
    target.include_router(marketing.router)
    target.include_router(executive.router)
    target.include_router(dashboard_router)
    target.include_router(mcp_hub.router)
    target.include_router(integrations_router)
    target.include_router(memory.router)
    target.include_router(analytics.router)
    target.include_router(enterprise.router)
    target.include_router(billing_router)
    target.include_router(compliance_router)
    target.include_router(platform_router)
    target.include_router(admin_router)
    _deferred_targets.add(target_id)


def build_api_router() -> APIRouter:
    """Full router for tests and tooling."""
    router = APIRouter()
    include_core_routers(router)
    include_deferred_routers(router)
    return router


def __getattr__(name: str) -> APIRouter:
    """Lazy ``api_router`` so ``import app.main`` does not pull the AI stack."""
    global _api_router
    if name == "api_router":
        if _api_router is None:
            _api_router = build_api_router()
        return _api_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
