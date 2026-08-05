"""Permission checks for MCP hub invocations."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.mcp_hub.enums import IntegrationProvider, PermissionAction
from app.mcp_hub.models import PermissionGrant
from app.mcp_hub.store import McpHubStorePort


class PermissionDenied(PermissionError):
    pass


DEFAULT_AGENT_ACTIONS = [
    PermissionAction.READ,
    PermissionAction.WRITE,
    PermissionAction.INVOKE,
]


class PermissionService:
    def __init__(self, store: McpHubStorePort) -> None:
        self._store = store

    def ensure_defaults(self, shop_id: UUID) -> None:
        existing = self._store.list_permissions(shop_id)
        if existing:
            return
        for provider in IntegrationProvider:
            self._store.save_permission(
                PermissionGrant(
                    id=uuid4(),
                    shop_id=shop_id,
                    principal="agent",
                    provider=provider,
                    actions=list(DEFAULT_AGENT_ACTIONS),
                    scopes=["*"],
                )
            )
            self._store.save_permission(
                PermissionGrant(
                    id=uuid4(),
                    shop_id=shop_id,
                    principal="owner",
                    provider=provider,
                    actions=[
                        PermissionAction.READ,
                        PermissionAction.WRITE,
                        PermissionAction.ADMIN,
                        PermissionAction.INVOKE,
                    ],
                    scopes=["*"],
                )
            )

    def grant(
        self,
        shop_id: UUID,
        *,
        principal: str,
        provider: IntegrationProvider,
        actions: list[PermissionAction],
        scopes: list[str] | None = None,
    ) -> PermissionGrant:
        grant = PermissionGrant(
            id=uuid4(),
            shop_id=shop_id,
            principal=principal,
            provider=provider,
            actions=list(actions),
            scopes=list(scopes or ["*"]),
        )
        return self._store.save_permission(grant)

    def check(
        self,
        shop_id: UUID,
        *,
        principal: str,
        provider: IntegrationProvider,
        action: PermissionAction,
    ) -> None:
        self.ensure_defaults(shop_id)
        grants = self._store.list_permissions(shop_id, principal=principal, provider=provider)
        for g in grants:
            if action in g.actions or PermissionAction.ADMIN in g.actions:
                return
        # Fallback: owner always allowed
        if principal == "owner":
            return
        raise PermissionDenied(
            f"Principal '{principal}' lacks {action.value} on {provider.value}"
        )
