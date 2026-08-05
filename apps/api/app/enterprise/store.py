"""Enterprise in-memory store."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from app.enterprise.models import (
    AiPolicy,
    ApiKey,
    AuditLogEntry,
    Location,
    OrgMembership,
    Organization,
    SsoConfig,
    WhiteLabelBrand,
)


class EnterpriseStorePort(Protocol):
    def save_org(self, org: Organization) -> Organization: ...
    def get_org(self, org_id: UUID) -> Organization | None: ...
    def get_org_by_slug(self, slug: str) -> Organization | None: ...
    def list_orgs(self) -> list[Organization]: ...

    def save_location(self, loc: Location) -> Location: ...
    def get_location(self, location_id: UUID) -> Location | None: ...
    def list_locations(self, org_id: UUID) -> list[Location]: ...
    def find_location_by_shop_id(self, shop_id: UUID) -> Location | None: ...

    def save_membership(self, m: OrgMembership) -> OrgMembership: ...
    def list_memberships(self, org_id: UUID) -> list[OrgMembership]: ...
    def memberships_for_user(self, user_id: UUID) -> list[OrgMembership]: ...

    def save_brand(self, brand: WhiteLabelBrand) -> WhiteLabelBrand: ...
    def get_brand(self, org_id: UUID) -> WhiteLabelBrand | None: ...

    def save_policy(self, policy: AiPolicy) -> AiPolicy: ...
    def list_policies(self, org_id: UUID) -> list[AiPolicy]: ...
    def get_policy(self, org_id: UUID, policy_id: UUID) -> AiPolicy | None: ...
    def delete_policy(self, org_id: UUID, policy_id: UUID) -> bool: ...

    def save_sso(self, cfg: SsoConfig) -> SsoConfig: ...
    def get_sso(self, org_id: UUID) -> SsoConfig | None: ...

    def append_audit(self, entry: AuditLogEntry) -> AuditLogEntry: ...
    def list_audit(self, org_id: UUID, *, limit: int = 100) -> list[AuditLogEntry]: ...

    def save_api_key(self, key: ApiKey) -> ApiKey: ...
    def list_api_keys(self, org_id: UUID) -> list[ApiKey]: ...
    def get_api_key_by_prefix(self, prefix: str) -> ApiKey | None: ...


class InMemoryEnterpriseStore:
    def __init__(self) -> None:
        self._orgs: dict[UUID, Organization] = {}
        self._locations: dict[UUID, Location] = {}
        self._memberships: dict[UUID, OrgMembership] = {}
        self._brands: dict[UUID, WhiteLabelBrand] = {}
        self._policies: dict[UUID, AiPolicy] = {}
        self._sso: dict[UUID, SsoConfig] = {}
        self._audit: list[AuditLogEntry] = []
        self._keys: dict[UUID, ApiKey] = {}

    def save_org(self, org: Organization) -> Organization:
        if org.created_at is None:
            org.created_at = datetime.now(timezone.utc)
        self._orgs[org.id] = org
        return org

    def get_org(self, org_id: UUID) -> Organization | None:
        return self._orgs.get(org_id)

    def get_org_by_slug(self, slug: str) -> Organization | None:
        for o in self._orgs.values():
            if o.slug == slug:
                return o
        return None

    def list_orgs(self) -> list[Organization]:
        return list(self._orgs.values())

    def save_location(self, loc: Location) -> Location:
        self._locations[loc.id] = loc
        return loc

    def get_location(self, location_id: UUID) -> Location | None:
        return self._locations.get(location_id)

    def list_locations(self, org_id: UUID) -> list[Location]:
        return [l for l in self._locations.values() if l.organization_id == org_id]

    def find_location_by_shop_id(self, shop_id: UUID) -> Location | None:
        for loc in self._locations.values():
            if loc.shop_id == shop_id:
                return loc
        return None

    def save_membership(self, m: OrgMembership) -> OrgMembership:
        if m.created_at is None:
            m.created_at = datetime.now(timezone.utc)
        self._memberships[m.id] = m
        return m

    def list_memberships(self, org_id: UUID) -> list[OrgMembership]:
        return [m for m in self._memberships.values() if m.organization_id == org_id]

    def memberships_for_user(self, user_id: UUID) -> list[OrgMembership]:
        return [m for m in self._memberships.values() if m.user_id == user_id]

    def save_brand(self, brand: WhiteLabelBrand) -> WhiteLabelBrand:
        self._brands[brand.organization_id] = brand
        return brand

    def get_brand(self, org_id: UUID) -> WhiteLabelBrand | None:
        return self._brands.get(org_id)

    def save_policy(self, policy: AiPolicy) -> AiPolicy:
        if policy.created_at is None:
            policy.created_at = datetime.now(timezone.utc)
        self._policies[policy.id] = policy
        return policy

    def list_policies(self, org_id: UUID) -> list[AiPolicy]:
        return sorted(
            [p for p in self._policies.values() if p.organization_id == org_id],
            key=lambda p: p.priority,
            reverse=True,
        )

    def get_policy(self, org_id: UUID, policy_id: UUID) -> AiPolicy | None:
        p = self._policies.get(policy_id)
        if p is None or p.organization_id != org_id:
            return None
        return p

    def delete_policy(self, org_id: UUID, policy_id: UUID) -> bool:
        p = self.get_policy(org_id, policy_id)
        if p is None:
            return False
        del self._policies[policy_id]
        return True

    def save_sso(self, cfg: SsoConfig) -> SsoConfig:
        self._sso[cfg.organization_id] = cfg
        return cfg

    def get_sso(self, org_id: UUID) -> SsoConfig | None:
        return self._sso.get(org_id)

    def append_audit(self, entry: AuditLogEntry) -> AuditLogEntry:
        if entry.created_at is None:
            entry.created_at = datetime.now(timezone.utc)
        self._audit.append(entry)
        if len(self._audit) > 10000:
            self._audit = self._audit[-5000:]
        return entry

    def list_audit(self, org_id: UUID, *, limit: int = 100) -> list[AuditLogEntry]:
        rows = [e for e in self._audit if e.organization_id == org_id]
        return list(reversed(rows[-limit:]))

    def save_api_key(self, key: ApiKey) -> ApiKey:
        if key.created_at is None:
            key.created_at = datetime.now(timezone.utc)
        self._keys[key.id] = key
        return key

    def list_api_keys(self, org_id: UUID) -> list[ApiKey]:
        return [k for k in self._keys.values() if k.organization_id == org_id]

    def get_api_key_by_prefix(self, prefix: str) -> ApiKey | None:
        for k in self._keys.values():
            if k.key_prefix == prefix and k.active:
                return k
        return None
