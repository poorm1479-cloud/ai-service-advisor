"""Per-shop AI usage monitoring (non-enforcing).

Tracks requests, tokens, SMS, voice minutes, and estimated cost without
changing AI behavior or plan quota enforcement.
"""

from __future__ import annotations

import logging
import math
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator
from uuid import UUID, uuid4

from sqlalchemy import select

from app.infrastructure.config import settings
from app.infrastructure.database import SessionLocal
from app.saas.quotas import ShopUsageCounterModel, _period_ym

logger = logging.getLogger("asa.usage")

METRIC_AI_REQUESTS = "ai_requests"
METRIC_INPUT_TOKENS = "input_tokens"
METRIC_OUTPUT_TOKENS = "output_tokens"
METRIC_SMS_COUNT = "sms_count"
METRIC_VOICE_SECONDS = "voice_seconds"
METRIC_COST_MICROS = "estimated_cost_micros"

_usage_shop_id: ContextVar[UUID | None] = ContextVar("asa_usage_shop_id", default=None)


def set_usage_shop_id(shop_id: UUID | None):
    return _usage_shop_id.set(shop_id)


def reset_usage_shop_id(token) -> None:
    _usage_shop_id.reset(token)


def get_usage_shop_id() -> UUID | None:
    return _usage_shop_id.get()


@contextmanager
def usage_shop_scope(shop_id: UUID | None) -> Iterator[None]:
    token = set_usage_shop_id(shop_id)
    try:
        yield
    finally:
        reset_usage_shop_id(token)


def _micros_for_tokens(*, input_tokens: int, output_tokens: int) -> int:
    in_cost = math.ceil(max(0, input_tokens) * settings.usage_cost_input_per_1k_micros / 1000)
    out_cost = math.ceil(max(0, output_tokens) * settings.usage_cost_output_per_1k_micros / 1000)
    return in_cost + out_cost


def _micros_for_tts(char_count: int) -> int:
    return math.ceil(max(0, char_count) * settings.usage_cost_tts_per_1k_chars_micros / 1000)


class UsageTrackingService:
    """Write-only metering for observability; never raises quota errors."""

    async def get_usage(self, shop_id: UUID, *, period: str | None = None) -> dict:
        period_ym = period or _period_ym()
        async with SessionLocal() as session:
            rows = (
                await session.scalars(
                    select(ShopUsageCounterModel).where(
                        ShopUsageCounterModel.shop_id == shop_id,
                        ShopUsageCounterModel.period_ym == period_ym,
                    )
                )
            ).all()
            counts = {r.metric: int(r.count) for r in rows}

        voice_seconds = counts.get(METRIC_VOICE_SECONDS, 0)
        cost_micros = counts.get(METRIC_COST_MICROS, 0)
        return {
            "period": period_ym,
            "shop_id": str(shop_id),
            "ai_requests": counts.get(METRIC_AI_REQUESTS, 0),
            "input_tokens": counts.get(METRIC_INPUT_TOKENS, 0),
            "output_tokens": counts.get(METRIC_OUTPUT_TOKENS, 0),
            "sms_count": counts.get(METRIC_SMS_COUNT, 0),
            "voice_seconds": voice_seconds,
            "voice_minutes": round(voice_seconds / 60.0, 2),
            "estimated_cost_micros": cost_micros,
            "estimated_cost_usd": round(cost_micros / 1_000_000.0, 6),
        }

    async def record_ai(
        self,
        shop_id: UUID,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        requests: int = 1,
        cost_micros: int | None = None,
    ) -> None:
        increments: dict[str, int] = {}
        if requests:
            increments[METRIC_AI_REQUESTS] = max(0, requests)
        if input_tokens:
            increments[METRIC_INPUT_TOKENS] = max(0, input_tokens)
        if output_tokens:
            increments[METRIC_OUTPUT_TOKENS] = max(0, output_tokens)
        micros = cost_micros
        if micros is None:
            micros = _micros_for_tokens(input_tokens=input_tokens, output_tokens=output_tokens)
        if micros:
            increments[METRIC_COST_MICROS] = max(0, micros)
        await self._increment_many(shop_id, increments)

    async def record_sms(self, shop_id: UUID, *, count: int = 1) -> None:
        if count <= 0:
            return
        await self._increment_many(
            shop_id,
            {
                METRIC_SMS_COUNT: count,
                METRIC_COST_MICROS: count * settings.usage_cost_sms_micros,
            },
        )

    async def record_voice_seconds(self, shop_id: UUID, seconds: int) -> None:
        if seconds <= 0:
            return
        minutes = seconds / 60.0
        cost = math.ceil(minutes * settings.usage_cost_voice_per_minute_micros)
        await self._increment_many(
            shop_id,
            {
                METRIC_VOICE_SECONDS: seconds,
                METRIC_COST_MICROS: cost,
            },
        )

    async def _increment_many(self, shop_id: UUID, increments: dict[str, int]) -> None:
        clean = {k: int(v) for k, v in increments.items() if v and int(v) > 0}
        if not clean:
            return
        period = _period_ym()
        async with SessionLocal() as session:
            for metric, amount in clean.items():
                row = await session.scalar(
                    select(ShopUsageCounterModel).where(
                        ShopUsageCounterModel.shop_id == shop_id,
                        ShopUsageCounterModel.period_ym == period,
                        ShopUsageCounterModel.metric == metric,
                    )
                )
                if row is None:
                    row = ShopUsageCounterModel(
                        id=uuid4(),
                        shop_id=shop_id,
                        period_ym=period,
                        metric=metric,
                        count=0,
                    )
                    session.add(row)
                    await session.flush()
                row.count += amount
            await session.commit()


async def record_ai_usage_if_scoped(
    *,
    operation: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    requests: int = 1,
    cost_micros: int | None = None,
    char_count: int = 0,
) -> None:
    """Best-effort monitoring hook — never affects caller on failure."""
    shop_id = get_usage_shop_id()
    if shop_id is None:
        return
    try:
        micros = cost_micros
        if micros is None:
            if operation == "stt":
                micros = settings.usage_cost_stt_per_request_micros * max(1, requests)
            elif operation == "tts":
                micros = _micros_for_tts(char_count)
            else:
                micros = _micros_for_tokens(input_tokens=input_tokens, output_tokens=output_tokens)
        await UsageTrackingService().record_ai(
            shop_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requests=requests,
            cost_micros=micros,
        )
    except Exception:
        logger.exception("usage.record_ai failed shop=%s op=%s", shop_id, operation)


async def record_sms_usage(shop_id: UUID, *, count: int = 1) -> None:
    try:
        await UsageTrackingService().record_sms(shop_id, count=count)
    except Exception:
        logger.exception("usage.record_sms failed shop=%s", shop_id)


async def record_voice_usage(shop_id: UUID, seconds: int) -> None:
    try:
        await UsageTrackingService().record_voice_seconds(shop_id, seconds)
    except Exception:
        logger.exception("usage.record_voice failed shop=%s", shop_id)


def voice_duration_seconds(
    *,
    recording_duration_sec: int | None,
    started_at: datetime | None,
    ended_at: datetime | None,
) -> int:
    if recording_duration_sec is not None and recording_duration_sec > 0:
        return int(recording_duration_sec)
    if started_at and ended_at:
        start = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
        end = ended_at if ended_at.tzinfo else ended_at.replace(tzinfo=timezone.utc)
        return max(0, int((end - start).total_seconds()))
    return 0
