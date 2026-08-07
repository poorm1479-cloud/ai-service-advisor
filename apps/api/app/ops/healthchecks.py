"""Liveness / readiness probes for production orchestration."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy import text

from app.infrastructure.config import settings
from app.ops.metrics import DB_UP, REDIS_UP

# Admin dashboard + SSE poll readiness often; avoid multi-second Redis connect waits.
_REDIS_CONNECT_TIMEOUT_S = 0.4
_REDIS_SOCKET_TIMEOUT_S = 0.4
_READINESS_TTL_S = 2.0
_readiness_cache: dict[str, Any] | None = None
_readiness_cached_at = 0.0
_readiness_lock: asyncio.Lock | None = None


def _readiness_guard() -> asyncio.Lock:
    global _readiness_lock
    if _readiness_lock is None:
        _readiness_lock = asyncio.Lock()
    return _readiness_lock


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

        client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=_REDIS_CONNECT_TIMEOUT_S,
            socket_timeout=_REDIS_SOCKET_TIMEOUT_S,
        )
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
    global _readiness_cache, _readiness_cached_at

    now = time.monotonic()
    cached = _readiness_cache
    if cached is not None and (now - _readiness_cached_at) < _READINESS_TTL_S:
        return cached

    async with _readiness_guard():
        now = time.monotonic()
        cached = _readiness_cache
        if cached is not None and (now - _readiness_cached_at) < _READINESS_TTL_S:
            return cached

        db, redis = await asyncio.gather(check_database(), check_redis())
        ready = db.get("status") == "up"
        if settings.ready_require_redis:
            ready = ready and redis.get("status") == "up"
        payload = {
            "status": "ready" if ready else "not_ready",
            "checks": {"database": db, "redis": redis},
            "environment": settings.environment,
        }
        _readiness_cache = payload
        _readiness_cached_at = time.monotonic()
        return payload
