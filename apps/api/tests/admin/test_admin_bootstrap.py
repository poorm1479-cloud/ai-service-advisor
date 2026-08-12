"""Platform admin bootstrap must not reset passwords on restart."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.admin.bootstrap import ensure_platform_admin
from app.domain.enums import AccountType
from app.infrastructure.config import settings
from app.infrastructure.database import SessionLocal
from app.infrastructure.models import UserModel
from app.infrastructure.security import hash_password, verify_password


@pytest.fixture
def admin_username(monkeypatch: pytest.MonkeyPatch) -> str:
    username = f"padmin_{uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "platform_admin_usernames", username)
    monkeypatch.setattr(settings, "platform_admin_bootstrap_password", "BootstrapPass123!")
    # Bootstrap is skipped for test/prod; exercise the local-dev path.
    monkeypatch.setattr(settings, "environment", "development")
    return username


async def _seed_platform_admin(username: str, password: str) -> None:
    async with SessionLocal() as session:
        session.add(
            UserModel(
                id=uuid4(),
                username=username,
                phone=None,
                full_name=username,
                password_hash=hash_password(password),
                primary_auth_method="username",
                account_type=AccountType.PLATFORM_ADMIN.value,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_bootstrap_does_not_reset_changed_password(admin_username: str) -> None:
    changed = "ChangedPass456!"
    await _seed_platform_admin(admin_username, changed)

    await ensure_platform_admin()

    async with SessionLocal() as session:
        row = (
            await session.execute(select(UserModel).where(UserModel.username == admin_username))
        ).scalar_one()
        assert verify_password(changed, row.password_hash)
        assert not verify_password("BootstrapPass123!", row.password_hash)


@pytest.mark.asyncio
async def test_bootstrap_creates_missing_admin(admin_username: str) -> None:
    await ensure_platform_admin()

    async with SessionLocal() as session:
        row = (
            await session.execute(select(UserModel).where(UserModel.username == admin_username))
        ).scalar_one_or_none()
        assert row is not None
        assert row.account_type == AccountType.PLATFORM_ADMIN.value
        assert verify_password("BootstrapPass123!", row.password_hash)
