"""Enterprise monitoring counters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EnterpriseMonitor:
    orgs_created: int = 0
    locations_added: int = 0
    policies_saved: int = 0
    sso_logins: int = 0
    gateway_calls: int = 0
    audit_events: int = 0
    by_role: dict[str, int] = field(default_factory=dict)

    def record_org(self) -> None:
        self.orgs_created += 1

    def record_location(self) -> None:
        self.locations_added += 1

    def record_policy(self) -> None:
        self.policies_saved += 1

    def record_sso(self) -> None:
        self.sso_logins += 1

    def record_gateway(self) -> None:
        self.gateway_calls += 1

    def record_audit(self) -> None:
        self.audit_events += 1

    def record_role(self, role: str) -> None:
        self.by_role[role] = self.by_role.get(role, 0) + 1

    def snapshot(self) -> dict[str, object]:
        return {
            "orgs_created": self.orgs_created,
            "locations_added": self.locations_added,
            "policies_saved": self.policies_saved,
            "sso_logins": self.sso_logins,
            "gateway_calls": self.gateway_calls,
            "audit_events": self.audit_events,
            "by_role": dict(self.by_role),
        }
