"""Phone / email OTP challenges for auth."""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from app.domain.exceptions import AuthenticationError, ConflictError, ValidationError
from app.infrastructure.config import settings
from app.infrastructure.security import hash_password, verify_password
from app.sms.factory import build_sms_provider
from app.sms.models import OutboundSms

logger = logging.getLogger("asa.auth.otp")

OtpPurpose = Literal["register", "login", "invite"]
OtpChannel = Literal["phone", "email"]

OTP_TTL_SECONDS = 600
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 45
OTP_LENGTH = 6

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(slots=True)
class OtpChallenge:
    id: UUID
    target: str  # normalized phone or email
    channel: str
    purpose: str
    code_hash: str
    expires_at: datetime
    attempts: int = 0
    consumed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)


class InMemoryOtpStore:
    def __init__(self) -> None:
        self._by_id: dict[UUID, OtpChallenge] = {}
        self._active: dict[tuple[str, str, str], UUID] = {}

    async def save(self, challenge: OtpChallenge) -> OtpChallenge:
        self._by_id[challenge.id] = challenge
        self._active[(challenge.channel, challenge.target, challenge.purpose)] = challenge.id
        return challenge

    async def get_active(self, channel: str, target: str, purpose: str) -> OtpChallenge | None:
        cid = self._active.get((channel, target, purpose))
        if cid is None:
            return None
        return self._by_id.get(cid)

    async def update(self, challenge: OtpChallenge) -> OtpChallenge:
        self._by_id[challenge.id] = challenge
        key = (challenge.channel, challenge.target, challenge.purpose)
        if challenge.consumed_at is None:
            self._active[key] = challenge.id
        else:
            self._active.pop(key, None)
        return challenge


_store = None
_sent_emails: list[dict[str, str]] = []


def get_otp_store():
    global _store
    if _store is None:
        backend = (settings.otp_store_backend or "db").lower()
        if backend == "memory" or settings.environment in {"test", "testing"}:
            _store = InMemoryOtpStore()
        else:
            from app.saas.otp_store import SqlAlchemyOtpStore

            _store = SqlAlchemyOtpStore()
    return _store


def reset_otp_store() -> None:
    global _store, _sent_emails
    _store = InMemoryOtpStore()
    _sent_emails = []
    try:
        from app.saas.email import clear_sent_emails

        clear_sent_emails()
    except Exception:
        pass


def get_sent_otp_emails() -> list[dict[str, str]]:
    return list(_sent_emails)


def normalize_phone(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValidationError("Phone number is required")
    digits = re.sub(r"\D", "", text)
    if text.startswith("+"):
        normalized = "+" + digits
    elif len(digits) == 10:
        normalized = "+1" + digits
    elif len(digits) == 11 and digits.startswith("1"):
        normalized = "+" + digits
    else:
        normalized = "+" + digits
    body = normalized[1:]
    if len(body) < 8 or len(body) > 15 or not body.isdigit():
        raise ValidationError("Invalid phone number")
    return normalized


def normalize_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        raise ValidationError("Valid email is required")
    return email


def _hash_code(code: str) -> str:
    pepper = hashlib.sha256(settings.jwt_secret.encode("utf-8")).hexdigest()[:16]
    return hash_password(f"{pepper}:{code}")


def _verify_code(code: str, code_hash: str) -> bool:
    pepper = hashlib.sha256(settings.jwt_secret.encode("utf-8")).hexdigest()[:16]
    try:
        return verify_password(f"{pepper}:{code}", code_hash)
    except Exception:  # noqa: BLE001
        return False


def _generate_code() -> str:
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


def _expose_dev_code() -> bool:
    return settings.twilio_provider == "fake" or settings.environment.lower() in {
        "development",
        "dev",
        "test",
        "local",
    }


@dataclass(slots=True)
class SendOtpResult:
    channel: str
    target: str
    purpose: str
    expires_in: int
    resend_after: int
    challenge_id: UUID
    phone: str | None = None
    email: str | None = None
    dev_code: str | None = None


class AuthOtpService:
    def __init__(self, store=None) -> None:
        self._store = store or get_otp_store()

    async def send_otp(
        self,
        *,
        purpose: OtpPurpose = "register",
        channel: OtpChannel = "phone",
        phone: str | None = None,
        email: str | None = None,
    ) -> SendOtpResult:
        if channel == "phone":
            target = normalize_phone(phone or "")
        else:
            target = normalize_email(email or "")

        now = datetime.now(timezone.utc)
        existing = await self._store.get_active(channel, target, purpose)
        if existing and existing.consumed_at is None:
            age = (now - existing.created_at).total_seconds()
            if age < OTP_RESEND_COOLDOWN_SECONDS:
                raise ConflictError(
                    f"Please wait {int(OTP_RESEND_COOLDOWN_SECONDS - age)}s before resending"
                )

        code = _generate_code()
        challenge = OtpChallenge(
            id=uuid4(),
            target=target,
            channel=channel,
            purpose=purpose,
            code_hash=_hash_code(code),
            expires_at=now + timedelta(seconds=OTP_TTL_SECONDS),
            created_at=now,
        )
        await self._store.save(challenge)

        if channel == "phone":
            from_number = settings.twilio_from_number or "+15005550006"
            provider = build_sms_provider()
            await provider.send(
                OutboundSms(
                    to_number=target,
                    from_number=from_number,
                    body=f"AI Service Advisor verification code: {code}",
                )
            )
            logger.info("auth.otp.sms_sent phone=%s purpose=%s", target, purpose)
        else:
            from app.saas.email import build_email_sender, get_sent_emails

            await build_email_sender().send(
                to=target,
                subject="AI Service Advisor verification code",
                body=f"Your verification code is: {code}",
            )
            # Keep local mirror for tests when fake provider is used
            _sent_emails.clear()
            _sent_emails.extend(get_sent_emails()[-1:])
            logger.info("auth.otp.email_sent email=%s purpose=%s", target, purpose)

        return SendOtpResult(
            channel=channel,
            target=target,
            purpose=purpose,
            expires_in=OTP_TTL_SECONDS,
            resend_after=OTP_RESEND_COOLDOWN_SECONDS,
            challenge_id=challenge.id,
            phone=target if channel == "phone" else None,
            email=target if channel == "email" else None,
            dev_code=code if _expose_dev_code() else None,
        )

    async def verify_otp(
        self,
        *,
        code: str,
        purpose: OtpPurpose = "register",
        channel: OtpChannel = "phone",
        phone: str | None = None,
        email: str | None = None,
        consume: bool = True,
    ) -> UUID:
        if channel == "phone":
            target = normalize_phone(phone or "")
        else:
            target = normalize_email(email or "")

        challenge = await self._store.get_active(channel, target, purpose)
        if challenge is None or challenge.consumed_at is not None:
            raise AuthenticationError("Verification code expired or not found")
        now = datetime.now(timezone.utc)
        if challenge.expires_at <= now:
            raise AuthenticationError("Verification code expired")
        if challenge.attempts >= OTP_MAX_ATTEMPTS:
            raise AuthenticationError("Too many invalid verification attempts")

        ok = _verify_code((code or "").strip(), challenge.code_hash)
        challenge.attempts += 1
        if not ok:
            await self._store.update(challenge)
            raise AuthenticationError("Invalid verification code")

        if consume:
            challenge.consumed_at = now
        await self._store.update(challenge)
        return challenge.id
