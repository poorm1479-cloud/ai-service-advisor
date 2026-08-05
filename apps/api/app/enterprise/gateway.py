"""API Gateway — route registry, API keys, rate limiting."""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict
from typing import Any
from uuid import UUID, uuid4

from app.enterprise.enums import AuditAction, EnterpriseRole, GatewayAuthType
from app.enterprise.models import ApiKey, GatewayRoute
from app.enterprise.roles import role_at_least
from app.enterprise.store import EnterpriseStorePort


DEFAULT_ROUTES: list[GatewayRoute] = [
    GatewayRoute("health", "/health", "api", GatewayAuthType.JWT, None, 600, True, "Health probes"),
    GatewayRoute("enterprise", "/v1/enterprise", "api", GatewayAuthType.JWT, EnterpriseRole.LOCATION_STAFF, 120, True, "Enterprise APIs"),
    GatewayRoute("analytics", "/v1/analytics", "api", GatewayAuthType.JWT, EnterpriseRole.LOCATION_MANAGER, 60, True, "Analytics"),
    GatewayRoute("agents", "/v1/agents", "api", GatewayAuthType.API_KEY, EnterpriseRole.API_CLIENT, 90, True, "Agent automation"),
    GatewayRoute("mcp", "/v1/mcp-hub", "api", GatewayAuthType.API_KEY, EnterpriseRole.API_CLIENT, 60, True, "MCP integrations"),
]


class RateLimited(Exception):
    pass


class GatewayDenied(PermissionError):
    pass


class ApiGateway:
    def __init__(self, store: EnterpriseStorePort, audit) -> None:
        self._store = store
        self._audit = audit
        self._routes = {r.id: r for r in DEFAULT_ROUTES}
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def list_routes(self) -> list[GatewayRoute]:
        return list(self._routes.values())

    def upsert_route(self, route: GatewayRoute) -> GatewayRoute:
        self._routes[route.id] = route
        return route

    def create_api_key(
        self,
        org_id: UUID,
        *,
        name: str,
        scopes: list[str] | None = None,
        rate_limit_rpm: int = 120,
    ) -> tuple[ApiKey, str]:
        raw = f"asa_{secrets.token_urlsafe(24)}"
        prefix = raw[:12]
        key = ApiKey(
            id=uuid4(),
            organization_id=org_id,
            name=name,
            key_prefix=prefix,
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            scopes=list(scopes or ["enterprise:read"]),
            rate_limit_rpm=rate_limit_rpm,
        )
        self._store.save_api_key(key)
        self._audit.log(
            organization_id=org_id,
            action=AuditAction.CREATE,
            resource="api_key",
            resource_id=str(key.id),
            details={"name": name, "prefix": prefix},
        )
        return key, raw

    def authorize(
        self,
        *,
        path: str,
        org_id: UUID | None = None,
        api_key: str | None = None,
        role: EnterpriseRole | None = None,
        client_id: str = "anonymous",
    ) -> dict[str, Any]:
        route = self._match(path)
        if route is None:
            raise GatewayDenied(f"No gateway route for {path}")
        if not route.enabled:
            raise GatewayDenied("Route disabled")

        limit = route.rate_limit_rpm
        auth_role = role

        if route.auth == GatewayAuthType.API_KEY:
            if not api_key:
                raise GatewayDenied("API key required")
            prefix = api_key[:12]
            record = self._store.get_api_key_by_prefix(prefix)
            if record is None or record.key_hash != hashlib.sha256(api_key.encode()).hexdigest():
                raise GatewayDenied("Invalid API key")
            if org_id and record.organization_id != org_id:
                raise GatewayDenied("API key org mismatch")
            org_id = record.organization_id
            limit = min(limit, record.rate_limit_rpm)
            auth_role = EnterpriseRole.API_CLIENT
            record.last_used_at = record.last_used_at  # touch placeholder
            self._store.save_api_key(record)

        if route.required_role and auth_role and not role_at_least(auth_role, route.required_role):
            raise GatewayDenied(f"Requires role {route.required_role.value}")

        self._rate_limit(f"{route.id}:{client_id}:{org_id}", limit)

        self._audit.log(
            organization_id=org_id,
            action=AuditAction.GATEWAY,
            resource="gateway",
            details={"path": path, "route": route.id, "auth": route.auth.value},
        )
        return {
            "allowed": True,
            "route_id": route.id,
            "upstream": route.upstream,
            "organization_id": str(org_id) if org_id else None,
            "rate_limit_rpm": limit,
        }

    def _match(self, path: str) -> GatewayRoute | None:
        candidates = sorted(self._routes.values(), key=lambda r: len(r.path_prefix), reverse=True)
        for r in candidates:
            if path == r.path_prefix or path.startswith(r.path_prefix.rstrip("/") + "/") or path.startswith(r.path_prefix):
                return r
        return None

    def _rate_limit(self, key: str, rpm: int) -> None:
        now = time.time()
        window = self._buckets[key]
        self._buckets[key] = [t for t in window if now - t < 60]
        if len(self._buckets[key]) >= rpm:
            raise RateLimited(f"Rate limit exceeded ({rpm}/min)")
        self._buckets[key].append(now)
