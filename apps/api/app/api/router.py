from fastapi import APIRouter

from app.api.routers import (
    agents,
    analytics,
    appointments,
    auth,
    capabilities,
    customers,
    enterprise,
    executive,
    health,
    imports,
    marketing,
    mcp_hub,
    memory,
    revenue,
    sms_inbox,
    tenant,
    twilio_voice_webhooks,
    twilio_webhooks,
    vehicles,
    voice_calls,
    voice_notes,
    walkins,
    workflows,
)
from app.admin.api import router as admin_router
from app.dashboard.api import router as dashboard_router
from app.integrations.api import router as integrations_router
from app.saas.api import router as billing_router
from app.saas.compliance_api import compliance_router, platform_router
from app.shop_setup.api import router as shop_setup_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(tenant.router)
api_router.include_router(shop_setup_router)
api_router.include_router(customers.router)
api_router.include_router(vehicles.router)
api_router.include_router(walkins.router)
api_router.include_router(voice_notes.router)
api_router.include_router(agents.router)
api_router.include_router(capabilities.router)
api_router.include_router(twilio_webhooks.router)
api_router.include_router(sms_inbox.router)
api_router.include_router(twilio_voice_webhooks.router)
api_router.include_router(voice_calls.router)
api_router.include_router(appointments.router)
api_router.include_router(imports.router)
api_router.include_router(workflows.router)
api_router.include_router(revenue.router)
api_router.include_router(marketing.router)
api_router.include_router(executive.router)
api_router.include_router(dashboard_router)
api_router.include_router(mcp_hub.router)
api_router.include_router(integrations_router)
api_router.include_router(memory.router)
api_router.include_router(analytics.router)
api_router.include_router(enterprise.router)
api_router.include_router(billing_router)
api_router.include_router(compliance_router)
api_router.include_router(platform_router)
api_router.include_router(admin_router)