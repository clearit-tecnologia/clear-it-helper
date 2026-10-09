"""Job queue used by the API to hand work to the arq worker."""

from __future__ import annotations

import asyncio
import uuid

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from redis.exceptions import RedisError

INGEST_DOCUMENT_TASK = "ingest_document"


class QueueError(Exception):
    """Raised when a job cannot be enqueued."""


class JobQueue:
    """Lazily connects to Redis so that the API starts even when Redis is down."""

    def __init__(self, redis_url: str) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._pool: ArqRedis | None = None
        self._lock = asyncio.Lock()

    async def _get_pool(self) -> ArqRedis:
        if self._pool is None:
            async with self._lock:
                if self._pool is None:
                    self._pool = await create_pool(self._settings)
        return self._pool

    async def enqueue_ingestion(self, *, document_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        try:
            pool = await self._get_pool()
            await pool.enqueue_job(INGEST_DOCUMENT_TASK, str(document_id), str(tenant_id))
        except (RedisError, OSError) as exc:
            raise QueueError(f"enqueue failed: {type(exc).__name__}") from exc

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None
