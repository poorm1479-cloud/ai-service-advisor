"""Twilio phone number provisioning for shops.

On shop signup we (optionally) search available numbers, purchase one, point SMS/Voice
webhooks at this API, and persist E.164 on ``shops.sms_phone_e164`` /
``shops.voice_phone_e164``.

``TWILIO_PROVIDER=fake`` assigns a local number without Twilio API calls.
Platform admins can force-provision / release even when auto-provision is off.

Admin **Remove** never deletes IncomingPhoneNumber resources — only DB unassign
(and optional webhook detach). ``release_shop_number`` is reserved for deliberate
carrier release (e.g. admin reset to a newly purchased number).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

import httpx

from app.infrastructure.config import settings
from app.sms.store import normalize_phone

logger = logging.getLogger("asa.telephony.numbers")


@dataclass(slots=True, frozen=True)
class ProvisionedNumber:
    phone_e164: str
    sid: str | None = None
    provider: str = "fake"


class NumberProvisionerPort(Protocol):
    async def provision(
        self,
        *,
        shop_id: UUID,
        friendly_name: str,
    ) -> ProvisionedNumber: ...


class FakeNumberProvisioner:
    """Dev/test provisioner — E.164 without Twilio spend."""

    def __init__(self, *, randomize: bool = False) -> None:
        # When randomize=True (admin re-provision), avoid sticky same E.164 per shop.
        self._randomize = randomize

    async def provision(
        self,
        *,
        shop_id: UUID,
        friendly_name: str,
    ) -> ProvisionedNumber:
        # +1800 + 7 digits — distinct from common test owner phones (+1555…)
        if self._randomize:
            suffix = f"{uuid4().int % 10_000_000:07d}"
        else:
            suffix = f"{shop_id.int % 10_000_000:07d}"
        phone = normalize_phone(f"+1800{suffix}")
        logger.info(
            "telephony.provision.fake shop=%s phone=%s name=%s",
            shop_id,
            phone,
            friendly_name[:64],
        )
        return ProvisionedNumber(phone_e164=phone, sid=f"PNfake{suffix}", provider="fake")


class TwilioNumberProvisioner:
    """Purchase a local Twilio number and wire SMS + Voice webhooks."""

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        country: str = "US",
        area_code: str = "",
        webhook_base_url: str = "",
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._country = (country or "US").upper()
        self._area_code = (area_code or "").strip()
        self._webhook_base = (webhook_base_url or "").rstrip("/")
        self._root = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"

    def _webhook_urls(self) -> dict[str, str]:
        base = self._webhook_base
        if not base:
            return {}
        return {
            "SmsUrl": f"{base}/v1/webhooks/twilio/sms",
            "SmsMethod": "POST",
            "VoiceUrl": f"{base}/v1/webhooks/twilio/voice",
            "VoiceMethod": "POST",
            "StatusCallback": f"{base}/v1/webhooks/twilio/voice/status",
            "StatusCallbackMethod": "POST",
        }

    async def _search_available(self, client: httpx.AsyncClient) -> str:
        params: dict[str, Any] = {
            "SmsEnabled": "true",
            "VoiceEnabled": "true",
            "PageSize": 5,
        }
        if self._area_code:
            params["AreaCode"] = self._area_code
        url = f"{self._root}/AvailablePhoneNumbers/{self._country}/Local.json"
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        numbers = payload.get("available_phone_numbers") or []
        if not numbers:
            raise RuntimeError(
                f"No Twilio local numbers available country={self._country} "
                f"area_code={self._area_code or 'any'}"
            )
        phone = str(numbers[0].get("phone_number") or "")
        if not phone:
            raise RuntimeError("Twilio available-number response missing phone_number")
        return phone

    async def provision(
        self,
        *,
        shop_id: UUID,
        friendly_name: str,
    ) -> ProvisionedNumber:
        auth = (self._account_sid, self._auth_token)
        async with httpx.AsyncClient(timeout=45.0, auth=auth) as client:
            available = await self._search_available(client)
            data: dict[str, str] = {
                "PhoneNumber": available,
                "FriendlyName": (friendly_name or f"Shop {shop_id}")[:64],
            }
            data.update(self._webhook_urls())
            response = await client.post(
                f"{self._root}/IncomingPhoneNumbers.json",
                data=data,
            )
            response.raise_for_status()
            payload = response.json()
            phone = normalize_phone(str(payload.get("phone_number") or available))
            sid = str(payload.get("sid") or "") or None
            logger.info(
                "telephony.provision.twilio shop=%s phone=%s sid=%s",
                shop_id,
                phone,
                sid,
            )
            return ProvisionedNumber(phone_e164=phone, sid=sid, provider="twilio")

    async def release(self, phone_e164: str) -> bool:
        """DELETE IncomingPhoneNumber from the Twilio account (destructive).

        Hard-blocked unless ``settings.twilio_allow_number_release`` is True.
        """
        phone = normalize_phone(phone_e164)
        if not phone:
            return False
        if not settings.twilio_allow_number_release:
            logger.warning(
                "telephony.release.blocked phone=%s "
                "(set TWILIO_ALLOW_NUMBER_RELEASE=true to allow destructive delete)",
                phone,
            )
            return False
        auth = (self._account_sid, self._auth_token)
        async with httpx.AsyncClient(timeout=45.0, auth=auth) as client:
            response = await client.get(
                f"{self._root}/IncomingPhoneNumbers.json",
                params={"PhoneNumber": phone, "PageSize": 1},
            )
            response.raise_for_status()
            payload = response.json()
            numbers = payload.get("incoming_phone_numbers") or []
            if not numbers:
                logger.info("telephony.release.not_found phone=%s", phone)
                return False
            sid = str(numbers[0].get("sid") or "")
            if not sid:
                return False
            delete = await client.delete(f"{self._root}/IncomingPhoneNumbers/{sid}.json")
            delete.raise_for_status()
            logger.info("telephony.release.twilio phone=%s sid=%s", phone, sid)
            return True

    async def find_incoming_sid(self, phone_e164: str) -> str | None:
        phone = normalize_phone(phone_e164)
        if not phone:
            return None
        auth = (self._account_sid, self._auth_token)
        async with httpx.AsyncClient(timeout=45.0, auth=auth) as client:
            response = await client.get(
                f"{self._root}/IncomingPhoneNumbers.json",
                params={"PhoneNumber": phone, "PageSize": 1},
            )
            response.raise_for_status()
            numbers = response.json().get("incoming_phone_numbers") or []
            if not numbers:
                return None
            sid = str(numbers[0].get("sid") or "")
            return sid or None

    async def clear_incoming_webhooks(self, phone_e164: str) -> dict[str, Any]:
        """Stop routing SMS/Voice to this API without releasing the number.

        The IncomingPhoneNumber resource stays on the Twilio account.
        """
        phone = normalize_phone(phone_e164)
        if not phone:
            return {
                "ok": False,
                "found": False,
                "sid": None,
                "error": "invalid_phone",
            }
        sid = await self.find_incoming_sid(phone)
        if not sid:
            logger.info("telephony.clear_webhooks.not_found phone=%s", phone)
            return {
                "ok": False,
                "found": False,
                "sid": None,
                "error": "number_not_on_twilio_account",
            }
        auth = (self._account_sid, self._auth_token)
        # Empty strings clear handlers in Twilio; do NOT DELETE the PN resource.
        data = {
            "VoiceUrl": "",
            "SmsUrl": "",
            "StatusCallback": "",
        }
        async with httpx.AsyncClient(timeout=45.0, auth=auth) as client:
            response = await client.post(
                f"{self._root}/IncomingPhoneNumbers/{sid}.json",
                data=data,
            )
            response.raise_for_status()
        logger.info(
            "telephony.clear_webhooks phone=%s sid=%s (number kept on account)",
            phone,
            sid,
        )
        return {"ok": True, "found": True, "sid": sid, "error": None}

    async def configure_webhooks(self, phone_e164: str) -> dict[str, Any]:
        """Point an existing account number's SMS/Voice URLs at this API."""
        phone = normalize_phone(phone_e164)
        urls = self._webhook_urls()
        if not phone:
            return {
                "ok": False,
                "found": False,
                "sid": None,
                "voice_url": None,
                "sms_url": None,
                "error": "invalid_phone",
            }
        if not urls:
            return {
                "ok": False,
                "found": False,
                "sid": None,
                "voice_url": None,
                "sms_url": None,
                "error": "missing_webhook_base_url",
            }
        sid = await self.find_incoming_sid(phone)
        if not sid:
            logger.warning("telephony.configure.not_found phone=%s", phone)
            return {
                "ok": False,
                "found": False,
                "sid": None,
                "voice_url": None,
                "sms_url": None,
                "error": "number_not_on_twilio_account",
            }
        auth = (self._account_sid, self._auth_token)
        async with httpx.AsyncClient(timeout=45.0, auth=auth) as client:
            response = await client.post(
                f"{self._root}/IncomingPhoneNumbers/{sid}.json",
                data=urls,
            )
            response.raise_for_status()
            payload = response.json()
        logger.info(
            "telephony.configure.twilio phone=%s sid=%s voice=%s sms=%s",
            phone,
            sid,
            payload.get("voice_url"),
            payload.get("sms_url"),
        )
        return {
            "ok": True,
            "found": True,
            "sid": sid,
            "voice_url": payload.get("voice_url"),
            "sms_url": payload.get("sms_url"),
            "error": None,
        }


def _twilio_provisioner_or_none() -> TwilioNumberProvisioner | None:
    if (
        (settings.twilio_provider or "fake").lower() == "fake"
        or not settings.twilio_account_sid
        or not settings.twilio_auth_token
    ):
        return None
    return TwilioNumberProvisioner(
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        country=settings.twilio_number_country or "US",
        area_code=settings.twilio_number_area_code or "",
        webhook_base_url=settings.twilio_public_base_url
        or settings.twilio_webhook_public_url
        or "",
    )


async def clear_shop_number_webhooks(phone_e164: str | None) -> dict[str, Any]:
    """Best-effort: detach webhooks but keep the number owned by the account.

    Never deletes IncomingPhoneNumber. Fake / no credentials → skipped.
    """
    if not phone_e164:
        return {
            "ok": False,
            "found": False,
            "sid": None,
            "error": "empty_phone",
            "skipped": False,
        }
    client = _twilio_provisioner_or_none()
    if client is None:
        logger.info(
            "telephony.clear_webhooks.skipped fake_or_unconfigured phone=%s",
            phone_e164,
        )
        return {
            "ok": True,
            "found": True,
            "sid": None,
            "error": None,
            "skipped": True,
        }
    try:
        result = await client.clear_incoming_webhooks(phone_e164)
        result["skipped"] = False
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "telephony.clear_webhooks.failed phone=%s err=%s",
            phone_e164,
            exc,
            exc_info=True,
        )
        return {
            "ok": False,
            "found": True,
            "sid": None,
            "error": str(exc),
            "skipped": False,
        }


async def configure_shop_number_webhooks(phone_e164: str | None) -> dict[str, Any]:
    """Best-effort: wire webhooks for an E.164 already on the Twilio account.

    Fake / missing credentials → skipped success (local dev).
    """
    if not phone_e164:
        return {
            "ok": False,
            "found": False,
            "sid": None,
            "voice_url": None,
            "sms_url": None,
            "error": "empty_phone",
            "skipped": False,
        }
    client = _twilio_provisioner_or_none()
    if client is None:
        logger.info("telephony.configure.skipped fake_or_unconfigured phone=%s", phone_e164)
        return {
            "ok": True,
            "found": True,
            "sid": None,
            "voice_url": None,
            "sms_url": None,
            "error": None,
            "skipped": True,
        }
    try:
        result = await client.configure_webhooks(phone_e164)
        result["skipped"] = False
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "telephony.configure.failed phone=%s err=%s",
            phone_e164,
            exc,
            exc_info=True,
        )
        return {
            "ok": False,
            "found": True,
            "sid": None,
            "voice_url": None,
            "sms_url": None,
            "error": str(exc),
            "skipped": False,
        }


def build_number_provisioner(
    *,
    force: bool = False,
    unique: bool = False,
) -> NumberProvisionerPort | None:
    """Return a provisioner when auto-assign is enabled (or force=True for admin)."""
    if not force and not settings.twilio_auto_provision_numbers:
        return None
    use_fake = (
        (settings.twilio_provider or "fake").lower() == "fake"
        or not settings.twilio_account_sid
        or not settings.twilio_auth_token
    )
    if use_fake:
        return FakeNumberProvisioner(randomize=unique)
    return _twilio_provisioner_or_none()


async def provision_shop_number(
    *,
    shop_id: UUID,
    shop_name: str,
    provisioner: NumberProvisionerPort | None = None,
    force: bool = False,
    unique: bool = False,
) -> ProvisionedNumber | None:
    """Provision one number for the shop. Never raises — logs and returns None on failure."""
    try:
        client = (
            provisioner
            if provisioner is not None
            else build_number_provisioner(force=force, unique=unique)
        )
        if client is None:
            return None
        return await client.provision(shop_id=shop_id, friendly_name=shop_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "telephony.provision.failed shop=%s err=%s",
            shop_id,
            exc,
            exc_info=True,
        )
        return None


async def release_shop_number(
    *,
    phone_e164: str | None,
) -> bool:
    """DELETE IncomingPhoneNumber from the Twilio account (destructive).

    Hard-blocked unless ``TWILIO_ALLOW_NUMBER_RELEASE=true``.
    Admin Remove never needs this — it only clears the DB mapping.
    """
    if not phone_e164:
        return False
    phone = normalize_phone(phone_e164)
    if not phone:
        return False
    use_fake = (
        (settings.twilio_provider or "fake").lower() == "fake"
        or not settings.twilio_account_sid
        or not settings.twilio_auth_token
    )
    if use_fake:
        logger.info("telephony.release.fake phone=%s", phone)
        return True
    if not settings.twilio_allow_number_release:
        logger.warning(
            "telephony.release.blocked phone=%s "
            "(set TWILIO_ALLOW_NUMBER_RELEASE=true to allow destructive delete)",
            phone,
        )
        return False
    try:
        provisioner = _twilio_provisioner_or_none()
        if provisioner is None:
            return False
        return await provisioner.release(phone)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "telephony.release.failed phone=%s err=%s",
            phone,
            exc,
            exc_info=True,
        )
        return False
