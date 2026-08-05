"""Enterprise domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.enterprise.enums import (
    AuditAction,
    EnterpriseRole,
    GatewayAuthType,
    PolicyEffect,
    PolicyScope,
    SsoProvider,
)


@dataclass(slots=True)
class Organization:
    id: UUID
    name: str
    slug: str
    franchise: bool = False
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Location:
    id: UUID
    organization_id: UUID
    shop_id: UUID
    name: str
    code: str
    region: str | None = None
    timezone: str = "America/Los_Angeles"
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrgMembership:
    id: UUID
    organization_id: UUID
    user_id: UUID
    email: str
    role: EnterpriseRole
    location_ids: list[UUID] = field(default_factory=list)  # empty = all locations
    created_at: datetime | None = None


@dataclass(slots=True)
class WhiteLabelBrand:
    organization_id: UUID
    product_name: str = "AI Service Advisor"
    primary_color: str = "#0F766E"
    accent_color: str = "#134E4A"
    logo_url: str | None = None
    favicon_url: str | None = None
    support_email: str | None = None
    custom_domain: str | None = None
    login_tagline: str | None = None
    hide_powered_by: bool = False
    css_vars: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AiPolicy:
    id: UUID
    organization_id: UUID
    name: str
    scope: PolicyScope
    effect: PolicyEffect
    location_id: UUID | None = None
    rules: dict[str, Any] = field(default_factory=dict)
    # e.g. {"intents": ["emergency"], "channels": ["sms"], "max_auto_book": true}
    priority: int = 100
    enabled: bool = True
    created_at: datetime | None = None


@dataclass(slots=True)
class SsoConfig:
    organization_id: UUID
    provider: SsoProvider
    enabled: bool = True
    client_id: str = ""
    issuer_url: str = ""
    metadata_url: str | None = None
    domains: list[str] = field(default_factory=list)
    role_mapping: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    require_sso: bool = False


@dataclass(slots=True)
class AuditLogEntry:
    id: UUID
    organization_id: UUID | None
    actor_user_id: UUID | None
    actor_email: str | None
    action: AuditAction
    resource: str
    resource_id: str | None = None
    location_id: UUID | None = None
    ip: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(slots=True)
class ApiKey:
    id: UUID
    organization_id: UUID
    name: str
    key_prefix: str
    key_hash: str
    scopes: list[str] = field(default_factory=list)
    rate_limit_rpm: int = 120
    active: bool = True
    created_at: datetime | None = None
    last_used_at: datetime | None = None


@dataclass(slots=True)
class GatewayRoute:
    id: str
    path_prefix: str
    upstream: str
    auth: GatewayAuthType = GatewayAuthType.JWT
    required_role: EnterpriseRole | None = None
    rate_limit_rpm: int = 300
    enabled: bool = True
    description: str = ""


@dataclass(slots=True)
class LocationMetrics:
    location_id: UUID
    location_name: str
    code: str
    revenue: float
    appointments: int
    ai_success_rate: float
    retention: float
    customers: int


@dataclass(slots=True)
class FranchiseAnalytics:
    organization_id: UUID
    generated_at: datetime
    locations: list[LocationMetrics] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)
    rankings: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class CentralDashboard:
    organization_id: UUID
    organization_name: str
    generated_at: datetime
    location_count: int
    kpis: list[dict[str, Any]] = field(default_factory=list)
    locations: list[LocationMetrics] = field(default_factory=list)
    brand: dict[str, Any] = field(default_factory=dict)
    policy_count: int = 0
    audit_recent: int = 0
    sso_enabled: bool = False


def new_id() -> UUID:
    return uuid4()
