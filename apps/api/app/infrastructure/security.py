from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.infrastructure.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    *,
    subject: str,
    role: str,
    shop_id: UUID | None = None,
    account_type: str = "shop",
    username: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    capabilities: list[str] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": "access",
        "account_type": (account_type or "shop").strip().lower() or "shop",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    if shop_id is not None:
        payload["shop_id"] = str(shop_id)
    if username:
        payload["username"] = username
    if email:
        payload["email"] = email
    if phone:
        payload["phone"] = phone
    if capabilities is not None:
        payload["capabilities"] = list(capabilities)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_mfa_pending_token(
    *,
    user_id: UUID,
    shop_id: UUID | None = None,
    account_type: str = "shop",
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "mfa_pending",
        "account_type": (account_type or "shop").strip().lower() or "shop",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    if shop_id is not None:
        payload["shop_id"] = str(shop_id)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
