"""API request/response schemas."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"


class CheckResult(BaseModel):
    status: Literal["ok", "error"]
    latency_ms: float
    detail: str | None = None


class ReadyResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckResult]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    tenant: TenantOut
