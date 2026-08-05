"""Enterprise service facade."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.enterprise.audit import AuditLogger
from app.enterprise.dashboard import CentralDashboardBuilder
from app.enterprise.enums import AuditAction, EnterpriseRole, PolicyEffect, PolicyScope, SsoProvider
from app.enterprise.franchise import FranchiseAnalyticsEngine
from app.enterprise.gateway import ApiGateway, GatewayDenied, RateLimited
from app.enterprise.models import (
    AiPolicy,
    ApiKey,
    CentralDashboard,
    FranchiseAnalytics,
    Location,
    OrgMembership,
    Organization,
    SsoConfig,
    WhiteLabelBrand,
    new_id,
)
from app.enterprise.monitoring import EnterpriseMonitor
from app.enterprise.policies import PolicyEngine
from app.enterprise.roles import hierarchy, require_role
from app.enterprise.sso import SsoService
from app.enterprise.store import EnterpriseStorePort


class EnterpriseService:
    def __init__(
        self,
        store: EnterpriseStorePort,
        *,
        audit: AuditLogger,
        policies: PolicyEngine,
        sso: SsoService,
        gateway: ApiGateway,
        franchise: FranchiseAnalyticsEngine,
        dashboard: CentralDashboardBuilder,
        monitor: EnterpriseMonitor,
    ) -> None:
        self._store = store
        self.audit = audit
        self.policies = policies
        self.sso = sso
        self.gateway = gateway
        self.franchise = franchise
        self.dashboard = dashboard
        self.monitor = monitor

    # --- Org / locations ---
    def create_organization(
        self,
        *,
        name: str,
        slug: str,
        franchise: bool = True,
        owner_user_id: UUID,
        owner_email: str,
    ) -> Organization:
        if self._store.get_org_by_slug(slug):
            raise ValueError(f"Slug already exists: {slug}")
        org = Organization(id=new_id(), name=name, slug=slug, franchise=franchise)
        self._store.save_org(org)
        self._store.save_membership(
            OrgMembership(
                id=new_id(),
                organization_id=org.id,
                user_id=owner_user_id,
                email=owner_email,
                role=EnterpriseRole.FRANCHISE_OWNER,
            )
        )
        self._store.save_brand(
            WhiteLabelBrand(
                organization_id=org.id,
                product_name=name,
                login_tagline=f"Welcome to {name}",
            )
        )
        self.audit.log(
            organization_id=org.id,
            action=AuditAction.CREATE,
            resource="organization",
            resource_id=str(org.id),
            actor_user_id=owner_user_id,
            actor_email=owner_email,
            details={"slug": slug, "franchise": franchise},
        )
        self.monitor.record_org()
        self.monitor.record_role(EnterpriseRole.FRANCHISE_OWNER.value)
        self.monitor.record_audit()
        return org

    def add_location(
        self,
        org_id: UUID,
        *,
        shop_id: UUID,
        name: str,
        code: str,
        region: str | None = None,
        timezone: str = "America/Los_Angeles",
        actor_user_id: UUID | None = None,
    ) -> Location:
        org = self._require_org(org_id)
        loc = Location(
            id=new_id(),
            organization_id=org.id,
            shop_id=shop_id,
            name=name,
            code=code.upper(),
            region=region,
            timezone=timezone,
        )
        self._store.save_location(loc)
        self.audit.log(
            organization_id=org_id,
            action=AuditAction.CREATE,
            resource="location",
            resource_id=str(loc.id),
            actor_user_id=actor_user_id,
            location_id=loc.id,
            details={"code": loc.code, "shop_id": str(shop_id)},
        )
        self.monitor.record_location()
        self.monitor.record_audit()
        return loc

    def list_locations(self, org_id: UUID) -> list[Location]:
        self._require_org(org_id)
        return self._store.list_locations(org_id)

    def list_memberships(self, org_id: UUID) -> list[OrgMembership]:
        return self._store.list_memberships(org_id)

    def grant_membership(
        self,
        org_id: UUID,
        *,
        user_id: UUID,
        email: str,
        role: EnterpriseRole,
        location_ids: list[UUID] | None = None,
        actor_role: EnterpriseRole | None = None,
    ) -> OrgMembership:
        if actor_role:
            require_role(actor_role, EnterpriseRole.ORG_ADMIN)
        m = OrgMembership(
            id=new_id(),
            organization_id=org_id,
            user_id=user_id,
            email=email,
            role=role,
            location_ids=list(location_ids or []),
        )
        saved = self._store.save_membership(m)
        self.monitor.record_role(role.value)
        self.audit.log(
            organization_id=org_id,
            action=AuditAction.CREATE,
            resource="membership",
            resource_id=str(saved.id),
            details={"role": role.value, "email": email},
        )
        self.monitor.record_audit()
        return saved

    def role_hierarchy(self) -> list[dict[str, object]]:
        return hierarchy()

    # --- White label ---
    def update_brand(self, org_id: UUID, **fields: Any) -> WhiteLabelBrand:
        brand = self._store.get_brand(org_id) or WhiteLabelBrand(organization_id=org_id)
        for k, v in fields.items():
            if v is not None and hasattr(brand, k):
                setattr(brand, k, v)
        saved = self._store.save_brand(brand)
        self.audit.log(
            organization_id=org_id,
            action=AuditAction.UPDATE,
            resource="white_label",
            details={k: fields[k] for k in fields if fields[k] is not None},
        )
        self.monitor.record_audit()
        return saved

    def get_brand(self, org_id: UUID) -> WhiteLabelBrand | None:
        return self._store.get_brand(org_id)

    # --- AI policies ---
    def save_policy(
        self,
        org_id: UUID,
        *,
        name: str,
        effect: PolicyEffect,
        scope: PolicyScope = PolicyScope.ORGANIZATION,
        rules: dict[str, Any] | None = None,
        location_id: UUID | None = None,
        priority: int = 100,
        policy_id: UUID | None = None,
        enabled: bool = True,
    ) -> AiPolicy:
        policy = AiPolicy(
            id=policy_id or new_id(),
            organization_id=org_id,
            name=name,
            scope=scope,
            effect=effect,
            location_id=location_id,
            rules=rules or {},
            priority=priority,
            enabled=enabled,
        )
        saved = self._store.save_policy(policy)
        self.monitor.record_policy()
        self.audit.log(
            organization_id=org_id,
            action=AuditAction.UPDATE if policy_id else AuditAction.CREATE,
            resource="ai_policy",
            resource_id=str(saved.id),
            details={"name": name, "effect": effect.value},
        )
        self.monitor.record_audit()
        return saved

    def list_policies(self, org_id: UUID) -> list[AiPolicy]:
        return self._store.list_policies(org_id)

    def evaluate_policy(self, org_id: UUID, **kwargs: Any) -> dict[str, Any]:
        result = self.policies.evaluate(org_id, **kwargs)
        self.audit.log(
            organization_id=org_id,
            action=AuditAction.POLICY_EVAL,
            resource="ai_policy",
            details={"result": result.get("effect"), "kwargs": {k: str(v) for k, v in kwargs.items()}},
        )
        self.monitor.record_audit()
        return result

    # --- SSO / gateway / analytics / dashboard ---
    def configure_sso(self, org_id: UUID, **kwargs: Any) -> SsoConfig:
        return self.sso.configure(org_id, **kwargs)

    def sso_begin(self, org_id: UUID, email: str | None = None) -> dict[str, Any]:
        return self.sso.begin_login(org_id, email=email)

    def sso_begin_by_slug(self, org_slug: str, email: str | None = None) -> dict[str, Any]:
        org = self._store.get_org_by_slug(org_slug.strip().lower())
        if org is None:
            raise ValueError("Organization not found")
        result = self.sso.begin_login(org.id, email=email)
        result["organization_id"] = str(org.id)
        result["organization_slug"] = org.slug
        return result

    def sso_status_by_slug(self, org_slug: str) -> dict[str, Any]:
        org = self._store.get_org_by_slug(org_slug.strip().lower())
        if org is None:
            raise ValueError("Organization not found")
        cfg = self._store.get_sso(org.id)
        enabled = bool(cfg and cfg.enabled)
        return {
            "organization_id": str(org.id),
            "organization_slug": org.slug,
            "sso_enabled": enabled,
            "require_sso": bool(cfg.require_sso) if cfg else False,
            "provider": cfg.provider.value if cfg and enabled else None,
        }

    async def sso_complete(self, **kwargs: Any) -> dict[str, Any]:
        result = await self.sso.complete_login_async(**kwargs)
        self.monitor.record_sso()
        return result

    def create_api_key(self, org_id: UUID, **kwargs: Any) -> tuple[ApiKey, str]:
        return self.gateway.create_api_key(org_id, **kwargs)

    def gateway_authorize(self, **kwargs: Any) -> dict[str, Any]:
        try:
            result = self.gateway.authorize(**kwargs)
            self.monitor.record_gateway()
            return result
        except (GatewayDenied, RateLimited):
            self.monitor.record_gateway()
            raise

    def franchise_analytics(self, org_id: UUID) -> FranchiseAnalytics:
        return self.franchise.build(org_id)

    def central_dashboard(self, org_id: UUID) -> CentralDashboard:
        return self.dashboard.build(org_id)

    def list_audit(self, org_id: UUID, *, limit: int = 100):
        return self._store.list_audit(org_id, limit=limit)

    def seed_demo(
        self,
        *,
        owner_user_id: UUID,
        owner_email: str,
        primary_shop_id: UUID,
    ) -> Organization:
        org = self.create_organization(
            name="ASA Franchise Network",
            slug=f"asa-franchise-{str(uuid4())[:8]}",
            franchise=True,
            owner_user_id=owner_user_id,
            owner_email=owner_email,
        )
        self.add_location(
            org.id,
            shop_id=primary_shop_id,
            name="Downtown Flagship",
            code="DTN",
            region="West",
            actor_user_id=owner_user_id,
        )
        self.add_location(
            org.id,
            shop_id=uuid4(),
            name="Northside Express",
            code="NTH",
            region="West",
            actor_user_id=owner_user_id,
        )
        self.add_location(
            org.id,
            shop_id=uuid4(),
            name="East Bay Service",
            code="EBY",
            region="East",
            actor_user_id=owner_user_id,
        )
        self.save_policy(
            org.id,
            name="Escalate emergencies",
            effect=PolicyEffect.REQUIRE_HUMAN,
            rules={"intents": ["emergency", "complaint"]},
            priority=200,
        )
        self.save_policy(
            org.id,
            name="Block auto-discount",
            effect=PolicyEffect.DENY,
            rules={"intents": ["price_question"], "auto_discount": True},
            priority=150,
        )
        self.configure_sso(
            org.id,
            provider=SsoProvider.OIDC,
            client_id="asa-enterprise-demo",
            issuer_url="https://sso.example.com",
            domains=["example.com"],
            role_mapping={"admin": EnterpriseRole.ORG_ADMIN.value, "user": EnterpriseRole.LOCATION_STAFF.value},
        )
        self.update_brand(
            org.id,
            product_name="ASA Franchise OS",
            primary_color="#0F766E",
            accent_color="#115E59",
            login_tagline="One network. Every location.",
            hide_powered_by=True,
        )
        self.create_api_key(org.id, name="Franchise automation", scopes=["enterprise:read", "agents:invoke"])
        return org

    def metrics(self) -> dict[str, object]:
        return self.monitor.snapshot()

    def get_org(self, org_id: UUID) -> Organization | None:
        return self._store.get_org(org_id)

    def list_orgs(self) -> list[Organization]:
        return self._store.list_orgs()

    def _require_org(self, org_id: UUID) -> Organization:
        org = self._store.get_org(org_id)
        if org is None:
            raise KeyError(f"Organization not found: {org_id}")
        return org
