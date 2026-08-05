"""Role hierarchy helpers."""

from __future__ import annotations

from app.enterprise.enums import ROLE_RANK, EnterpriseRole


class InsufficientRole(PermissionError):
    pass


def role_at_least(actual: EnterpriseRole, required: EnterpriseRole) -> bool:
    return ROLE_RANK.get(actual, 0) >= ROLE_RANK.get(required, 999)


def require_role(actual: EnterpriseRole, required: EnterpriseRole) -> None:
    if not role_at_least(actual, required):
        raise InsufficientRole(f"Requires {required.value}, have {actual.value}")


def hierarchy() -> list[dict[str, object]]:
    ordered = sorted(ROLE_RANK.items(), key=lambda kv: kv[1], reverse=True)
    return [{"role": r.value, "rank": rank, "label": r.value.replace("_", " ").title()} for r, rank in ordered]
