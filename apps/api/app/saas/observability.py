"""Optional Sentry error tracking."""

from __future__ import annotations

import logging

from app.infrastructure.config import settings

logger = logging.getLogger("asa.observability")


def init_observability() -> None:
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=settings.environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
            ],
        )
        logger.info("sentry.enabled environment=%s", settings.environment)
    except Exception as exc:
        logger.warning("sentry.init_failed err=%s", exc)
