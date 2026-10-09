"""Liveness and readiness endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from clear_helper.db import get_engine
from clear_helper.deps import SettingsDep
from clear_helper.health import Check, build_checks, run_checks
from clear_helper.schemas import LiveResponse, ReadyResponse

router = APIRouter(prefix="/health", tags=["health"])


def get_readiness_checks(settings: SettingsDep) -> dict[str, Check]:
    return build_checks(settings, get_engine())


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse()


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
async def ready(
    response: Response,
    settings: SettingsDep,
    checks: Annotated[dict[str, Check], Depends(get_readiness_checks)],
) -> ReadyResponse:
    results = await run_checks(checks, timeout_s=settings.health_timeout_seconds)
    all_ok = all(result.status == "ok" for result in results.values())
    postgres = results.get("postgres")
    if postgres is None or postgres.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="ok" if all_ok else "degraded", checks=results)
