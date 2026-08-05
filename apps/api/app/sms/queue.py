"""SMS message queue with retry — in-memory + Redis adapters."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.sms.enums import SmsJobStatus
from app.sms.models import SmsJob

logger = logging.getLogger("asa.sms.queue")

JobHandler = Callable[[SmsJob], Awaitable[None]]


class MessageQueuePort(Protocol):
    async def enqueue(self, *, shop_id: UUID | None, payload: dict[str, Any]) -> SmsJob: ...

    async def process_one(self, handler: JobHandler) -> bool:
        """Process one job; return False if queue empty."""

    async def depth(self) -> int: ...


class InMemoryMessageQueue:
    """Async queue with retry + dead-letter list (production-local / tests)."""

    def __init__(self, *, max_attempts: int = 3) -> None:
        self._queue: asyncio.Queue[SmsJob] = asyncio.Queue()
        self._dead: list[SmsJob] = []
        self._max_attempts = max_attempts
        self._completed = 0
        self._failed = 0

    @property
    def dead_letter(self) -> list[SmsJob]:
        return list(self._dead)

    @property
    def stats(self) -> dict[str, int]:
        return {
            "completed": self._completed,
            "failed": self._failed,
            "dead": len(self._dead),
            "pending": self._queue.qsize(),
        }

    async def enqueue(self, *, shop_id: UUID | None, payload: dict[str, Any]) -> SmsJob:
        job = SmsJob(
            id=uuid4(),
            shop_id=shop_id,
            payload=payload,
            status=SmsJobStatus.PENDING.value,
            max_attempts=self._max_attempts,
            created_at=datetime.now(timezone.utc),
        )
        await self._queue.put(job)
        logger.info("sms.queue.enqueued job=%s", job.id)
        return job

    async def depth(self) -> int:
        return self._queue.qsize()

    async def process_one(self, handler: JobHandler) -> bool:
        try:
            job = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return False

        job.status = SmsJobStatus.PROCESSING.value
        job.attempts += 1
        try:
            await handler(job)
            job.status = SmsJobStatus.COMPLETED.value
            self._completed += 1
            logger.info("sms.queue.completed job=%s attempts=%s", job.id, job.attempts)
        except Exception as exc:  # noqa: BLE001
            job.last_error = str(exc)
            self._failed += 1
            if job.attempts < job.max_attempts:
                job.status = SmsJobStatus.PENDING.value
                await self._queue.put(job)
                logger.warning(
                    "sms.queue.retry job=%s attempt=%s error=%s",
                    job.id,
                    job.attempts,
                    exc,
                )
            else:
                job.status = SmsJobStatus.DEAD.value
                self._dead.append(job)
                logger.error("sms.queue.dead job=%s error=%s", job.id, exc)
        finally:
            self._queue.task_done()
        return True


class RedisMessageQueue:
    """Redis list-backed queue (LPUSH / RPOP)."""

    def __init__(self, redis_url: str, *, key: str = "asa:sms:jobs", max_attempts: int = 3) -> None:
        self._redis_url = redis_url
        self._key = key
        self._dead_key = f"{key}:dead"
        self._max_attempts = max_attempts
        self._client: Any = None

    async def _conn(self) -> Any:
        if self._client is None:
            import redis.asyncio as redis

            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def enqueue(self, *, shop_id: UUID | None, payload: dict[str, Any]) -> SmsJob:
        job = SmsJob(
            id=uuid4(),
            shop_id=shop_id,
            payload=payload,
            status=SmsJobStatus.PENDING.value,
            max_attempts=self._max_attempts,
            created_at=datetime.now(timezone.utc),
        )
        client = await self._conn()
        await client.lpush(self._key, json.dumps(_job_to_dict(job)))
        return job

    async def depth(self) -> int:
        client = await self._conn()
        return int(await client.llen(self._key))

    async def process_one(self, handler: JobHandler) -> bool:
        client = await self._conn()
        raw = await client.rpop(self._key)
        if not raw:
            return False
        data = json.loads(raw)
        job = _job_from_dict(data)
        job.status = SmsJobStatus.PROCESSING.value
        job.attempts += 1
        try:
            await handler(job)
            job.status = SmsJobStatus.COMPLETED.value
        except Exception as exc:  # noqa: BLE001
            job.last_error = str(exc)
            if job.attempts < job.max_attempts:
                job.status = SmsJobStatus.PENDING.value
                await client.lpush(self._key, json.dumps(_job_to_dict(job)))
            else:
                job.status = SmsJobStatus.DEAD.value
                await client.lpush(self._dead_key, json.dumps(_job_to_dict(job)))
        return True


def _job_to_dict(job: SmsJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "shop_id": str(job.shop_id) if job.shop_id else None,
        "payload": job.payload,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "last_error": job.last_error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def _job_from_dict(data: dict[str, Any]) -> SmsJob:
    return SmsJob(
        id=UUID(data["id"]),
        shop_id=UUID(data["shop_id"]) if data.get("shop_id") else None,
        payload=data.get("payload") or {},
        status=data.get("status", SmsJobStatus.PENDING.value),
        attempts=int(data.get("attempts", 0)),
        max_attempts=int(data.get("max_attempts", 3)),
        last_error=data.get("last_error"),
        created_at=(
            datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        ),
    )
