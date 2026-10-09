"""Readiness checks for the backing services.

Each check is an async callable that raises on failure. ``run_checks`` executes them in
parallel, each bounded by a short timeout, and never raises itself.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping

import boto3
import httpx
from botocore.config import Config as BotoConfig
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from clear_helper.config import Settings
from clear_helper.schemas import CheckResult

logger = logging.getLogger(__name__)

Check = Callable[[], Awaitable[None]]

_MAX_DETAIL_LENGTH = 200


async def check_postgres(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def check_redis(url: str, timeout_s: float) -> None:
    client = Redis.from_url(url, socket_connect_timeout=timeout_s, socket_timeout=timeout_s)
    try:
        await client.ping()
    finally:
        await client.aclose()


async def check_http(url: str, timeout_s: float) -> None:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.get(url)
        response.raise_for_status()


async def check_s3(settings: Settings, timeout_s: float) -> None:
    if settings.s3_access_key is None or settings.s3_secret_key is None:
        raise RuntimeError("S3 credentials are not configured")
    access_key = settings.s3_access_key.get_secret_value()
    secret_key = settings.s3_secret_key.get_secret_value()

    def _head_bucket() -> None:
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(
                connect_timeout=timeout_s,
                read_timeout=timeout_s,
                retries={"max_attempts": 1},
                s3={"addressing_style": "path"},
            ),
        )
        client.head_bucket(Bucket=settings.s3_bucket)

    # boto3 is synchronous; keep the event loop free.
    await asyncio.to_thread(_head_bucket)


def build_checks(settings: Settings, engine: AsyncEngine) -> dict[str, Check]:
    timeout = settings.health_timeout_seconds
    return {
        "postgres": lambda: check_postgres(engine),
        "redis": lambda: check_redis(settings.redis_url, timeout),
        "qdrant": lambda: check_http(f"{settings.qdrant_url.rstrip('/')}/readyz", timeout),
        "s3": lambda: check_s3(settings, timeout),
        "litellm": lambda: check_http(
            f"{settings.litellm_url.rstrip('/')}/health/liveliness", timeout
        ),
    }


def _describe(exc: BaseException) -> str:
    message = str(exc).strip()
    detail = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    return detail[:_MAX_DETAIL_LENGTH]


async def _run_one(name: str, check: Check, timeout_s: float) -> CheckResult:
    started = time.perf_counter()
    detail: str | None = None
    try:
        await asyncio.wait_for(check(), timeout=timeout_s)
    except TimeoutError:
        detail = f"timeout after {timeout_s}s"
    except Exception as exc:
        detail = _describe(exc)
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    if detail is None:
        return CheckResult(status="ok", latency_ms=latency_ms)
    logger.warning(
        "health.check_failed", extra={"check": name, "detail": detail, "latency_ms": latency_ms}
    )
    return CheckResult(status="error", latency_ms=latency_ms, detail=detail)


async def run_checks(checks: Mapping[str, Check], timeout_s: float) -> dict[str, CheckResult]:
    names = list(checks)
    results = await asyncio.gather(*(_run_one(name, checks[name], timeout_s) for name in names))
    return dict(zip(names, results, strict=True))
