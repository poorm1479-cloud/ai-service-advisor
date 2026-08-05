"""Phase 14 MCP Integration Hub tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.mcp_hub.adapters import list_adapters
from app.mcp_hub.enums import IntegrationProvider, InvokeStatus, PermissionAction
from app.mcp_hub.factory import build_mcp_hub_runtime, reset_mcp_hub_runtime
from app.mcp_hub.models import InvokeRequest, RetryPolicy
from app.mcp_hub.permissions import PermissionDenied
from app.mcp_hub.store import InMemoryMcpHubStore
from app.mcp_hub.versioning import VersionMismatch


@pytest.fixture(autouse=True)
def _reset():
    reset_mcp_hub_runtime()
    yield
    reset_mcp_hub_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def runtime():
    return build_mcp_hub_runtime(
        store=InMemoryMcpHubStore(),
        retry_policy=RetryPolicy(max_attempts=2, base_delay_ms=1, max_delay_ms=5),
    )


def test_all_required_integrations_registered():
    providers = {a.provider for a in list_adapters()}
    required = {
        IntegrationProvider.TEKMETRIC,
        IntegrationProvider.SHOPMONKEY,
        IntegrationProvider.AUTOLEAP,
        IntegrationProvider.MITCHELL,
        IntegrationProvider.GOOGLE_CALENDAR,
        IntegrationProvider.GOOGLE_BUSINESS,
        IntegrationProvider.TWILIO,
        IntegrationProvider.STRIPE,
        IntegrationProvider.FACEBOOK,
        IntegrationProvider.EMAIL,
        IntegrationProvider.FUTURE,
    }
    assert required.issubset(providers)


@pytest.mark.asyncio
async def test_connection_manager_auth_and_test(runtime, shop_id):
    conn = await runtime.service.create_connection(
        shop_id,
        provider=IntegrationProvider.TWILIO,
        demo=True,
        connect=True,
    )
    assert conn.status.value == "connected"
    assert conn.credentials is not None

    result = await runtime.connections.test(shop_id, conn.id)
    assert result["ok"] is True

    disconnected = await runtime.connections.disconnect(shop_id, conn.id)
    assert disconnected.status.value == "disconnected"


@pytest.mark.asyncio
async def test_invoke_with_permissions_logging_versioning(runtime, shop_id):
    await runtime.service.create_connection(
        shop_id,
        provider=IntegrationProvider.TEKMETRIC,
        demo=True,
        connect=True,
    )
    result = await runtime.service.invoke(
        InvokeRequest(
            shop_id=shop_id,
            provider=IntegrationProvider.TEKMETRIC,
            tool="tekmetric.list_customers",
            arguments={"limit": 5},
            principal="agent",
            api_version="v1",
        )
    )
    assert result.status == InvokeStatus.SUCCESS
    assert result.attempts >= 1
    assert result.api_version == "v1"
    assert runtime.service.list_logs(shop_id)
    assert runtime.service.list_invokes(shop_id)


@pytest.mark.asyncio
async def test_permission_denial(runtime, shop_id):
    await runtime.service.create_connection(
        shop_id,
        provider=IntegrationProvider.STRIPE,
        demo=True,
        connect=True,
    )
    # No grants for principal "guest"
    runtime.permissions.ensure_defaults(shop_id)
    with pytest.raises(PermissionDenied):
        runtime.permissions.check(
            shop_id,
            principal="guest",
            provider=IntegrationProvider.STRIPE,
            action=PermissionAction.INVOKE,
        )

    denied = await runtime.service.invoke(
        InvokeRequest(
            shop_id=shop_id,
            provider=IntegrationProvider.STRIPE,
            tool="stripe.list_invoices",
            principal="guest",
        )
    )
    assert denied.status == InvokeStatus.DENIED
    assert runtime.monitor.permission_denials >= 1


def test_version_negotiation(runtime):
    assert runtime.versions.resolve(IntegrationProvider.GOOGLE_CALENDAR, "v3") == "v3"
    with pytest.raises(VersionMismatch):
        runtime.versions.resolve(IntegrationProvider.GOOGLE_CALENDAR, "v99")


@pytest.mark.asyncio
async def test_mcp_tools_surface(runtime):
    tools = runtime.service.list_mcp_descriptors()
    names = {t["name"] for t in tools}
    assert "twilio.send_sms" in names
    assert "email.send" in names
    assert "future.ping" in names


def test_main_imports_mcp_hub_routes():
    from app.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/v1/mcp-hub/integrations" in paths
    assert "/v1/mcp-hub/invoke" in paths
    assert "/v1/mcp-hub/tools" in paths
