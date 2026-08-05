"""Liveness / readiness probes for production orchestration."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.infrastructure.config import settings
from app.ops.metrics import DB_UP, REDIS_UP


async def check_database() -> dict[str, Any]:
    try:
        from app.infrastructure.database import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        DB_UP.set(1)
        return {"status": "up"}
    except Exception as exc:
        DB_UP.set(0)
        return {"status": "down", "error": str(exc)}


async def check_redis() -> dict[str, Any]:
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            pong = await client.ping()
            ok = bool(pong)
        finally:
            await client.aclose()
        REDIS_UP.set(1 if ok else 0)
        return {"status": "up" if ok else "down"}
    except Exception as exc:
        REDIS_UP.set(0)
        return {"status": "down", "error": str(exc)}


async def readiness() -> dict[str, Any]:
    db = await check_database()
    redis = await check_redis()
    ready = db.get("status") == "up"
    if settings.ready_require_redis:
        ready = ready and redis.get("status") == "up"
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {"database": db, "redis": redis},
        "environment": settings.environment,
    }
