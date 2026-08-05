"""Custom AI policy evaluation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.enterprise.enums import PolicyEffect
from app.enterprise.models import AiPolicy
from app.enterprise.store import EnterpriseStorePort


class PolicyEngine:
    def __init__(self, store: EnterpriseStorePort) -> None:
        self._store = store

    def evaluate(
        self,
        org_id: UUID,
        *,
        intent: str | None = None,
        channel: str | None = None,
        location_id: UUID | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        policies = [p for p in self._store.list_policies(org_id) if p.enabled]
        matched: list[AiPolicy] = []
        for policy in policies:
            if policy.location_id and location_id and policy.location_id != location_id:
                continue
            if policy.location_id and location_id is None:
                continue
            rules = policy.rules or {}
            if rules.get("intents") and intent and intent not in rules["intents"]:
                continue
            if rules.get("channels") and channel and channel not in rules["channels"]:
                continue
            for key, expected in rules.items():
                if key in {"intents", "channels", "message"}:
                    continue
                if key in context and context[key] != expected:
                    break
            else:
                matched.append(policy)

        effect = PolicyEffect.ALLOW
        reasons: list[str] = []
        for p in matched:
            reasons.append(f"{p.name}:{p.effect.value}")
            if p.effect == PolicyEffect.DENY:
                effect = PolicyEffect.DENY
                break
            if p.effect == PolicyEffect.REQUIRE_HUMAN and effect != PolicyEffect.DENY:
                effect = PolicyEffect.REQUIRE_HUMAN

        return {
            "effect": effect.value,
            "matched_policy_ids": [str(p.id) for p in matched],
            "reasons": reasons,
            "allow_auto": effect == PolicyEffect.ALLOW,
            "require_human": effect == PolicyEffect.REQUIRE_HUMAN,
        }
