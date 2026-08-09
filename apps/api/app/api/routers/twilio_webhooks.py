"""Twilio SMS webhook — receive inbound messages."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse

from app.infrastructure.config import settings
from app.sms.models import InboundSms
from app.sms.runtime import get_sms_runtime
from app.sms.factory import SmsRuntime
from app.sms.twilio.provider import parse_twilio_form

logger = logging.getLogger("asa.sms.webhook")

router = APIRouter(prefix="/v1/webhooks/twilio", tags=["webhooks"])


def _runtime() -> SmsRuntime:
    return get_sms_runtime()


@router.post("/sms")
async def twilio_inbound_sms(
    request: Request,
    runtime: SmsRuntime = Depends(_runtime),
) -> Response:
    if not settings.sms_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="SMS disabled")

    form = await request.form()
    params = parse_twilio_form(form)
    signature = request.headers.get("X-Twilio-Signature")
    # Reconstruct public URL Twilio signed (prefer configured base if behind proxy)
    path = "/v1/webhooks/twilio/sms"
    url = str(request.url)
    alt_urls = [url]
    base = settings.twilio_public_base_url
    if base:
        url = base + path
        alt_urls.append(base + (request.url.path or path))
        if request.url.query:
            alt_urls.append(f"{url}?{request.url.query}")
        raw = (settings.twilio_webhook_public_url or "").rstrip("/")
        if raw and raw != base:
            alt_urls.append(raw)
            alt_urls.append(raw if raw.endswith(path) else raw + path)

    if not runtime.provider.verify_webhook(
        url=url, params=params, signature=signature, alt_urls=alt_urls
    ):
        runtime.monitor.record_webhook_rejected()
        logger.warning("sms.webhook.rejected signature url=%s has_sig=%s", url, bool(signature))
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    inbound = InboundSms(
        from_number=params.get("From", ""),
        to_number=params.get("To", ""),
        body=params.get("Body", ""),
        message_sid=params.get("MessageSid"),
        account_sid=params.get("AccountSid"),
        raw=params,
    )
    if not inbound.from_number or not inbound.body.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Missing From/Body")

    shop_id = await runtime.service.resolve_shop_id(inbound.to_number)
    job = await runtime.service.enqueue_inbound(inbound, shop_id=shop_id)

    # Process immediately (modular monolith); queue still records retries on failure
    try:
        await runtime.service.process_job(job)
    except Exception as exc:  # noqa: BLE001
        runtime.monitor.record_queue_failure()
        logger.exception("sms.webhook.process_failed job=%s err=%s", job.id, exc)
        # Re-queue for retry
        await runtime.queue.enqueue(shop_id=shop_id, payload=job.payload)

    # Empty TwiML — replies are sent via REST API asynchronously
    return PlainTextResponse(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


@router.get("/health")
async def twilio_webhook_health(runtime: SmsRuntime = Depends(_runtime)) -> dict[str, Any]:
    return {
        "sms_enabled": settings.sms_enabled,
        "provider": settings.twilio_provider,
        "queue_backend": settings.sms_queue_backend,
        "queue_depth": await runtime.queue.depth(),
        "metrics": runtime.monitor.snapshot(),
    }
