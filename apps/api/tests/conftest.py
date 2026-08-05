import os

import pytest

# Ensure test runs use NullPool-friendly settings before app imports.
os.environ.setdefault("ENVIRONMENT", "test")

# Exact shop names created by integration tests (shared local DB).
_TEST_SHOP_NAMES = {
    "Phase1 Garage",
    "RLS A",
    "RLS B",
    "Logout Shop",
    "Alpha Auto",
    "Beta Auto",
    "Signup Notify Garage",
    "Test Garage",
    "Setup Garage",
    "Fix Test",
    "No OTP Garage",
    "Cors Test",
    "UI Test",
    "Demo Auto",
    "Shop A",
    "Shop B",
}

# Prefixed names like "CRM Shop a-1096df5c", "Walkin Shop b6f8e1ac".
_TEST_SHOP_PREFIXES = (
    "CRM Shop ",
    "Walkin Shop ",
    "Voice Shop ",
    "Other ",
)


def _is_test_shop_name(name: str) -> bool:
    if name in _TEST_SHOP_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in _TEST_SHOP_PREFIXES)


async def _purge_test_shops() -> None:
    """Remove pytest leftover tenants so the admin UI reflects real signups."""
    from sqlalchemy import text

    from app.infrastructure.database import SessionLocal

    async with SessionLocal() as session:
        rows = (await session.execute(text("SELECT id, name FROM shops"))).all()
        victim_ids = [row[0] for row in rows if _is_test_shop_name(str(row[1]))]
        if not victim_ids:
            return
        orphan_users = (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT m.user_id
                    FROM shop_memberships m
                    WHERE m.shop_id = ANY(:shop_ids)
                      AND m.user_id NOT IN (
                        SELECT m2.user_id
                        FROM shop_memberships m2
                        WHERE m2.shop_id <> ALL(:shop_ids)
                      )
                    """
                ),
                {"shop_ids": victim_ids},
            )
        ).scalars().all()
        await session.execute(
            text("DELETE FROM shops WHERE id = ANY(:shop_ids)"),
            {"shop_ids": victim_ids},
        )
        if orphan_users:
            await session.execute(
                text("DELETE FROM users WHERE id = ANY(:user_ids)"),
                {"user_ids": list(orphan_users)},
            )
        await session.commit()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_shops_around_session():
    """Purge test tenants before/after the suite so admin dashboards stay accurate."""
    import asyncio

    try:
        asyncio.run(_purge_test_shops())
    except Exception:
        # DB may be down for unit-only runs.
        pass
    yield
    try:
        asyncio.run(_purge_test_shops())
    except Exception:
        pass


@pytest.fixture(autouse=True)
async def _dispose_engine():
    yield
    from app.infrastructure.database import engine

    await engine.dispose()
