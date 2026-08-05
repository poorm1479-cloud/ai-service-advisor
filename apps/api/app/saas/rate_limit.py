"""Simple in-process rate limiter for auth endpoints."""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

ADMIN_LOGIN_FAIL_DETAIL = "Login failed"
ADMIN_LOGIN_LOCKOUT_DETAIL = "Too many failed attempts. Try again later."


class SlidingWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )
        q.append(now)


class LoginFailureLockout:
    """Lock a key after N consecutive failures for a fixed cooldown."""

    def __init__(self, *, max_failures: int = 3, lockout_seconds: int = 600) -> None:
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def reset(self) -> None:
        self._failures.clear()
        self._locked_until.clear()

    def _purge_expired(self, key: str, now: float) -> None:
        until = self._locked_until.get(key)
        if until is not None and now >= until:
            del self._locked_until[key]
            self._failures.pop(key, None)

    def remaining_seconds(self, key: str) -> int:
        now = time.monotonic()
        self._purge_expired(key, now)
        until = self._locked_until.get(key)
        if until is None or now >= until:
            return 0
        return max(1, math.ceil(until - now))

    def lockout_detail(self, key: str) -> dict[str, object]:
        return {
            "message": ADMIN_LOGIN_LOCKOUT_DETAIL,
            "retry_after": self.remaining_seconds(key),
        }

    def assert_not_locked(self, key: str) -> None:
        remaining = self.remaining_seconds(key)
        if remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=self.lockout_detail(key),
                headers={"Retry-After": str(remaining)},
            )

    def record_failure(self, key: str) -> tuple[str | dict[str, object], int | None]:
        now = time.monotonic()
        self._purge_expired(key, now)
        remaining = self.remaining_seconds(key)
        if remaining > 0:
            return self.lockout_detail(key), remaining
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        if count >= self.max_failures:
            self._locked_until[key] = now + self.lockout_seconds
            self._failures[key] = 0
            remaining = self.remaining_seconds(key)
            return self.lockout_detail(key), remaining
        return ADMIN_LOGIN_FAIL_DETAIL, None

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)


auth_rate_limiter = SlidingWindowRateLimiter(limit=30, window_seconds=60)
admin_login_lockout = LoginFailureLockout(max_failures=3, lockout_seconds=600)


def client_key(request: Request, suffix: str = "") -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = (forwarded.split(",")[0].strip() if forwarded else None) or (
        request.client.host if request.client else "unknown"
    )
    return f"{ip}:{suffix}" if suffix else ip
