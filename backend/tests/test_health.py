from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI

from clear_helper.health import Check, run_checks
from clear_helper.routes.health import get_readiness_checks

SERVICES = ("postgres", "redis", "qdrant", "s3", "litellm")


async def _ok() -> None:
    return None


async def _fail() -> None:
    raise ConnectionError("connection refused")


async def _slow() -> None:
    await asyncio.sleep(5)


def _checks(**overrides: Check) -> dict[str, Check]:
    return {name: overrides.get(name, _ok) for name in SERVICES}


async def test_live(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_all_ok(app: FastAPI, client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_readiness_checks] = lambda: _checks()

    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["checks"]) == set(SERVICES)
    for check in body["checks"].values():
        assert check["status"] == "ok"
        assert check["detail"] is None
        assert isinstance(check["latency_ms"], int | float)


async def test_ready_degraded_when_optional_service_fails(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    app.dependency_overrides[get_readiness_checks] = lambda: _checks(qdrant=_fail)

    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["qdrant"]["status"] == "error"
    assert "ConnectionError" in body["checks"]["qdrant"]["detail"]


async def test_ready_returns_503_when_postgres_fails(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    app.dependency_overrides[get_readiness_checks] = lambda: _checks(postgres=_fail)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["postgres"]["status"] == "error"


async def test_run_checks_applies_timeout_in_parallel() -> None:
    loop = asyncio.get_running_loop()
    started = loop.time()

    results = await run_checks({"a": _slow, "b": _slow, "c": _ok}, timeout_s=0.05)

    assert loop.time() - started < 1
    assert results["a"].status == "error"
    assert results["a"].detail is not None
    assert "timeout" in results["a"].detail
    assert results["c"].status == "ok"
