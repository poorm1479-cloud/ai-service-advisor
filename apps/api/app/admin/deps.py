"""Platform admin auth gate — JWT + account_type + PLATFORM_ADMIN_USERNAMES allowlist."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.api.deps import CurrentUser, get_current_user
from app.domain.enums import AccountType
from app.infrastructure.config import settings


async def require_platform_admin(
    current: CurrentUser = Depends(get_current_user),
) -> str:
    """Require a valid access token for a platform admin account.

    Returns the normalized admin username. Unauthenticated callers get 401 from
    ``get_current_user``; authenticated non-admins get 403.
    """
    allowlist = settings.platform_admin_username_set

    # Production fail-closed: empty allowlist denies all platform admin access.
    if settings.environment.lower() in {"production", "prod"} and not allowlist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin required",
        )

    if (current.account_type or "") != AccountType.PLATFORM_ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin required",
        )

    username = (current.username or "").strip().lower()
    if not username or username not in allowlist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin required",
        )

    return username
