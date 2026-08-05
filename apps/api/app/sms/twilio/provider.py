"""Twilio SMS provider — send + signature verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.sms.models import OutboundSms

logger = logging.getLogger("asa.sms.twilio")


class SmsProviderPort(Protocol):
    async def send(self, message: OutboundSms) -> str:
        """Send SMS; return provider message id."""

    def verify_webhook(
        self, *, url: str, params: dict[str, str], signature: str | None
    ) -> bool: ...


@dataclass(slots=True)
class TwilioSettings:
    account_sid: str
    auth_token: str
    from_number: str
    status_callback_url: str | None = None
    validate_signature: bool = True


class FakeSmsProvider:
    """Test/dev provider — records outbound messages."""

    def __init__(self) -> None:
        self.sent: list[OutboundSms] = []
        self._n = 0

    async def send(self, message: OutboundSms) -> str:
        self._n += 1
        self.sent.append(message)
        sid = f"FKfake{self._n:08d}"
        logger.info("sms.fake.send to=%s sid=%s", message.to_number, sid)
        return sid

    def verify_webhook(
        self, *, url: str, params: dict[str, str], signature: str | None
    ) -> bool:
        return True


class TwilioSmsProvider:
    """Twilio REST Messages API via httpx."""

    def __init__(self, settings: TwilioSettings) -> None:
        self._settings = settings
        self._base = f"https://api.twilio.com/2010-04-01/Accounts/{settings.account_sid}/Messages.json"

    async def send(self, message: OutboundSms) -> str:
        data = {
            "To": message.to_number,
            "From": message.from_number or self._settings.from_number,
            "Body": message.body,
        }
        if self._settings.status_callback_url:
            data["StatusCallback"] = self._settings.status_callback_url

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self._base,
                data=data,
                auth=(self._settings.account_sid, self._settings.auth_token),
            )
            response.raise_for_status()
            payload = response.json()
            sid = str(payload.get("sid", ""))
            logger.info("sms.twilio.send to=%s sid=%s", message.to_number, sid)
            return sid

    def verify_webhook(
        self, *, url: str, params: dict[str, str], signature: str | None
    ) -> bool:
        if not self._settings.validate_signature:
            return True
        if not signature:
            return False
        return validate_twilio_signature(
            auth_token=self._settings.auth_token,
            url=url,
            params=params,
            signature=signature,
        )


def validate_twilio_signature(
    *,
    auth_token: str,
    url: str,
    params: dict[str, str],
    signature: str,
) -> bool:
    """Validate X-Twilio-Signature (HMAC-SHA1)."""
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    digest = hmac.new(
        auth_token.encode("utf-8"),
        s.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def parse_twilio_form(form: dict[str, Any]) -> dict[str, str]:
    return {str(k): str(v) for k, v in form.items()}
