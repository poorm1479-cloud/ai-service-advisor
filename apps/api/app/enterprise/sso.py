"""OIDC-capable SSO (falls back to demo mode without client_secret)."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx

from app.enterprise.enums import AuditAction, EnterpriseRole, SsoProvider
from app.enterprise.models import OrgMembership, SsoConfig, new_id
from app.enterprise.store import EnterpriseStorePort
from app.infrastructure.config import settings

logger = logging.getLogger("asa.enterprise.sso")


class SsoService:
    def __init__(self, store: EnterpriseStorePort, audit) -> None:
        self._store = store
        self._audit = audit
        self._pending: dict[str, dict[str, Any]] = {}

    def configure(
        self,
        org_id: UUID,
        *,
        provider: SsoProvider,
        client_id: str,
        issuer_url: str,
        domains: list[str] | None = None,
        role_mapping: dict[str, str] | None = None,
        enabled: bool = True,
        metadata_url: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        require_sso: bool = False,
    ) -> SsoConfig:
        meta: dict[str, Any] = {}
        if client_secret:
            meta["client_secret"] = client_secret
        if redirect_uri:
            meta["redirect_uri"] = redirect_uri
        cfg = SsoConfig(
            organization_id=org_id,
            provider=provider,
            enabled=enabled,
            client_id=client_id,
            issuer_url=issuer_url,
            metadata_url=metadata_url,
            domains=list(domains or []),
            role_mapping=dict(role_mapping or {"admin": EnterpriseRole.ORG_ADMIN.value}),
            metadata=meta,
            require_sso=require_sso,
        )
        saved = self._store.save_sso(cfg)
        self._audit.log(
            organization_id=org_id,
            action=AuditAction.UPDATE,
            resource="sso_config",
            details={
                "provider": provider.value,
                "enabled": enabled,
                "oidc": bool(client_secret),
                "require_sso": require_sso,
            },
        )
        return saved

    async def _discover(self, cfg: SsoConfig) -> dict[str, Any]:
        meta_url = cfg.metadata_url or f"{cfg.issuer_url.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(meta_url)
            res.raise_for_status()
            return res.json()

    def begin_login(self, org_id: UUID, *, email: str | None = None) -> dict[str, Any]:
        cfg = self._store.get_sso(org_id)
        if cfg is None or not cfg.enabled:
            raise ValueError("SSO not configured or disabled")
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(16)
        client_secret = (cfg.metadata or {}).get("client_secret") or settings.oidc_client_secret
        redirect_uri = (
            (cfg.metadata or {}).get("redirect_uri")
            or settings.oidc_redirect_uri
            or f"{settings.web_app_url.rstrip('/')}/enterprise/sso/callback"
        )
        demo_mode = not bool(client_secret)

        self._pending[state] = {
            "org_id": str(org_id),
            "email": email,
            "nonce": nonce,
            "redirect_uri": redirect_uri,
            "demo_mode": demo_mode,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if demo_mode:
            return {
                "state": state,
                "provider": cfg.provider.value,
                "authorize_url": (
                    f"{cfg.issuer_url.rstrip('/')}/authorize"
                    f"?client_id={cfg.client_id}&state={state}&response_type=code"
                ),
                "demo_mode": True,
                "redirect_uri": redirect_uri,
            }

        # Synchronous-friendly: build authorize URL without discovery when possible.
        authorize = f"{cfg.issuer_url.rstrip('/')}/authorize"
        if cfg.metadata_url and "openid-configuration" not in (cfg.metadata_url or ""):
            authorize = f"{cfg.issuer_url.rstrip('/')}/oauth2/v1/authorize"
        params = {
            "client_id": cfg.client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
        }
        if email:
            params["login_hint"] = email
        return {
            "state": state,
            "provider": cfg.provider.value,
            "authorize_url": f"{authorize}?{urlencode(params)}",
            "demo_mode": False,
            "redirect_uri": redirect_uri,
        }

    async def complete_login_async(
        self,
        *,
        state: str,
        email: str | None = None,
        code: str | None = None,
        external_role: str | None = None,
        user_id: UUID | None = None,
    ) -> dict[str, Any]:
        pending = self._pending.pop(state, None)
        if pending is None:
            raise ValueError("Invalid or expired SSO state")
        org_id = UUID(pending["org_id"])
        cfg = self._store.get_sso(org_id)
        if cfg is None:
            raise ValueError("SSO config missing")

        resolved_email = email or pending.get("email")
        demo_mode = bool(pending.get("demo_mode", True))
        client_secret = (cfg.metadata or {}).get("client_secret") or settings.oidc_client_secret
        redirect_uri = pending.get("redirect_uri") or settings.oidc_redirect_uri

        if not demo_mode and code and client_secret:
            try:
                discovery = await self._discover(cfg)
                token_url = discovery.get("token_endpoint")
                userinfo_url = discovery.get("userinfo_endpoint")
                async with httpx.AsyncClient(timeout=20) as client:
                    token_res = await client.post(
                        token_url,
                        data={
                            "grant_type": "authorization_code",
                            "code": code,
                            "redirect_uri": redirect_uri,
                            "client_id": cfg.client_id,
                            "client_secret": client_secret,
                        },
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    token_res.raise_for_status()
                    tokens = token_res.json()
                    access = tokens.get("access_token")
                    if userinfo_url and access:
                        ui = await client.get(
                            userinfo_url,
                            headers={"Authorization": f"Bearer {access}"},
                        )
                        ui.raise_for_status()
                        profile = ui.json()
                        resolved_email = profile.get("email") or resolved_email
                        external_role = external_role or profile.get("role")
            except Exception as exc:
                logger.exception("sso.oidc_exchange_failed")
                raise ValueError(f"OIDC token exchange failed: {exc}") from exc

        if not resolved_email:
            raise ValueError("email is required to complete SSO login")

        # Domain allow-list only for real OIDC completions (not demo exchange).
        if not demo_mode and cfg.domains:
            domain = resolved_email.split("@")[-1].lower()
            allowed = {d.lower() for d in cfg.domains}
            if domain not in allowed:
                raise ValueError("Email domain is not allowed for this organization")

        return self._finalize_login(
            org_id=org_id,
            cfg=cfg,
            email=resolved_email,
            external_role=external_role,
            user_id=user_id,
        )

    def complete_login(
        self,
        *,
        state: str,
        email: str,
        external_role: str | None = None,
        user_id: UUID | None = None,
        code: str | None = None,
    ) -> dict[str, Any]:
        """Sync wrapper for demo/tests; prefer complete_login_async in API."""
        pending = self._pending.get(state)
        if pending and not pending.get("demo_mode") and code:
            raise ValueError("Use async OIDC completion for real SSO code exchange")
        # Consume pending via async-compatible path without network
        pending = self._pending.pop(state, None)
        if pending is None:
            raise ValueError("Invalid or expired SSO state")
        org_id = UUID(pending["org_id"])
        cfg = self._store.get_sso(org_id)
        if cfg is None:
            raise ValueError("SSO config missing")
        return self._finalize_login(
            org_id=org_id,
            cfg=cfg,
            email=email or pending.get("email") or "",
            external_role=external_role,
            user_id=user_id,
        )

    def _finalize_login(
        self,
        *,
        org_id: UUID,
        cfg: SsoConfig,
        email: str,
        external_role: str | None,
        user_id: UUID | None,
    ) -> dict[str, Any]:
        if not email:
            raise ValueError("email is required")
        mapped = (cfg.role_mapping or {}).get(external_role or "user", EnterpriseRole.LOCATION_STAFF.value)
        try:
            role = EnterpriseRole(mapped)
        except ValueError:
            role = EnterpriseRole.LOCATION_STAFF
        uid = user_id or uuid4()
        membership = OrgMembership(
            id=new_id(),
            organization_id=org_id,
            user_id=uid,
            email=email,
            role=role,
        )
        existing = next(
            (m for m in self._store.list_memberships(org_id) if m.email.lower() == email.lower()),
            None,
        )
        if existing:
            membership = existing
        else:
            self._store.save_membership(membership)

        session_token = hashlib.sha256(f"{org_id}:{uid}:{secrets.token_hex(8)}".encode()).hexdigest()
        self._audit.log(
            organization_id=org_id,
            action=AuditAction.SSO,
            resource="sso_login",
            actor_user_id=membership.user_id,
            actor_email=email,
            details={"provider": cfg.provider.value, "role": membership.role.value},
        )
        return {
            "session_token": session_token,
            "organization_id": str(org_id),
            "user_id": str(membership.user_id),
            "email": membership.email,
            "role": membership.role.value,
            "provider": cfg.provider.value,
        }
