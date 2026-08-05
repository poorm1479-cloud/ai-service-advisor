"""Phase 18 Enterprise features tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.enterprise.enums import EnterpriseRole, PolicyEffect
from app.enterprise.factory import build_enterprise_runtime, reset_enterprise_runtime
from app.enterprise.gateway import GatewayDenied
from app.enterprise.roles import role_at_least
from app.enterprise.store import InMemoryEnterpriseStore


@pytest.fixture(autouse=True)
def _reset():
    reset_enterprise_runtime()
    yield
    reset_enterprise_runtime()


@pytest.fixture
def runtime():
    return build_enterprise_runtime(store=InMemoryEnterpriseStore())


@pytest.fixture
def owner():
    return uuid4(), "owner@franchise.test"


def test_role_hierarchy():
    assert role_at_least(EnterpriseRole.FRANCHISE_OWNER, EnterpriseRole.ORG_ADMIN)
    assert not role_at_least(EnterpriseRole.LOCATION_STAFF, EnterpriseRole.ORG_ADMIN)


def test_multi_location_central_dashboard(runtime, owner):
    user_id, email = owner
    org = runtime.service.seed_demo(
        owner_user_id=user_id,
        owner_email=email,
        primary_shop_id=uuid4(),
    )
    locs = runtime.service.list_locations(org.id)
    assert len(locs) >= 3
    dash = runtime.service.central_dashboard(org.id)
    assert dash.location_count >= 3
    assert dash.kpis
    assert dash.brand.get("product_name")
    fa = runtime.service.franchise_analytics(org.id)
    # Empty shops stay at zero — no invented demo franchise metrics.
    assert fa.totals.get("revenue", 0) == 0
    assert fa.rankings.get("revenue")


def test_ai_policies_and_white_label(runtime, owner):
    user_id, email = owner
    org = runtime.service.create_organization(
        name="Policy Co",
        slug=f"policy-{uuid4().hex[:6]}",
        owner_user_id=user_id,
        owner_email=email,
    )
    runtime.service.save_policy(
        org.id,
        name="Human for complaints",
        effect=PolicyEffect.REQUIRE_HUMAN,
        rules={"intents": ["complaint"]},
        priority=50,
    )
    result = runtime.service.evaluate_policy(org.id, intent="complaint", channel="sms")
    assert result["require_human"] is True

    brand = runtime.service.update_brand(org.id, product_name="PolicyOS", primary_color="#111827")
    assert brand.product_name == "PolicyOS"


@pytest.mark.asyncio
async def test_sso_audit_and_gateway(runtime, owner):
    user_id, email = owner
    org = runtime.service.seed_demo(
        owner_user_id=user_id,
        owner_email=email,
        primary_shop_id=uuid4(),
    )
    begin = runtime.service.sso_begin(org.id, email=email)
    done = await runtime.service.sso_complete(
        state=begin["state"],
        email=email,
        external_role="admin",
        user_id=user_id,
    )
    assert done["role"] in {r.value for r in EnterpriseRole}
    assert runtime.service.list_audit(org.id)

    key, raw = runtime.service.create_api_key(org.id, name="bots")
    assert raw.startswith("asa_")
    allowed = runtime.service.gateway_authorize(
        path="/v1/agents/run",
        api_key=raw,
        client_id="test",
    )
    assert allowed["allowed"] is True

    with pytest.raises(GatewayDenied):
        runtime.service.gateway_authorize(path="/v1/agents/run", client_id="no-key")


def test_main_imports_enterprise_routes():
    from app.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/v1/enterprise/organizations" in paths
    assert "/v1/enterprise/gateway/routes" in paths
    assert "/v1/enterprise/organizations/{org_id}/dashboard" in paths
