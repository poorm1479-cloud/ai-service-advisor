"""Ensure the default platform admin account exists on first boot."""

from __future__ import annotations

import logging
from uuid import uuid4

from app.domain.entities import User
from app.domain.enums import AccountType
from app.infrastructure.config import settings
from app.infrastructure.database import SessionLocal
from app.infrastructure.security import hash_password
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

logger = logging.getLogger(__name__)

_WEAK_BOOTSTRAP_PASSWORDS = frozenset({"admin", "password", "changeme"})


async def ensure_platform_admin() -> None:
    """Create the first PLATFORM_ADMIN_USERNAMES account if it is missing.

    Creates a platform_admin user with no shop / membership.
    Bootstrap password is used only for initial create — never overwrite an
    existing admin password (Settings → Change password must survive restart).
    Production skips weak default passwords like ``admin``.
    """
    env = settings.environment.lower()
    if env in {"test", "testing"}:
        return

    allowlist = sorted(settings.platform_admin_username_set)
    if not allowlist:
        return

    username = allowlist[0]
    password = (settings.platform_admin_bootstrap_password or "").strip()
    if not password:
        logger.warning("platform admin bootstrap skipped: empty PLATFORM_ADMIN_BOOTSTRAP_PASSWORD")
        return
    if env in {"production", "prod"} and password.lower() in _WEAK_BOOTSTRAP_PASSWORDS:
        logger.warning(
            "platform admin bootstrap skipped in production: set a strong "
            "PLATFORM_ADMIN_BOOTSTRAP_PASSWORD (not a default like 'admin')"
        )
        return

    try:
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            existing = await uow.users.get_by_username(username)
            if existing is None:
                await uow.users.add(
                    User(
                        id=uuid4(),
                        username=username,
                        phone=None,
                        email=None,
                        full_name=username,
                        password_hash=hash_password(password),
                        phone_verified=False,
                        email_verified=False,
                        primary_auth_method="username",
                        account_type=AccountType.PLATFORM_ADMIN.value,
                    )
                )
                await uow.commit()
                logger.info("platform admin bootstrap: created user=%s (no shop)", username)
                return

            if (existing.account_type or AccountType.SHOP.value) != AccountType.PLATFORM_ADMIN.value:
                await uow.users.update_account_type(
                    existing.id, account_type=AccountType.PLATFORM_ADMIN.value
                )
                await uow.commit()
                logger.info("platform admin bootstrap: promoted account_type user=%s", username)
            else:
                logger.debug("platform admin bootstrap: ok user=%s", username)
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform admin bootstrap failed: %s", exc)
