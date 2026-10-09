"""API request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from clear_helper.models import DocumentStatus

MAX_HISTORY_MESSAGES = 10

QueryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


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


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    error: str | None
    page_count: int | None
    chunk_count: int | None
    pipeline_version: str | None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentOut]


class DuplicateDocumentResponse(BaseModel):
    detail: str
    document_id: uuid.UUID


class Source(BaseModel):
    ref: int
    document_id: uuid.UUID
    filename: str
    page: int
    chunk_index: int
    score: float
    text: str


class SearchRequest(BaseModel):
    query: QueryText
    top_k: int | None = Field(default=None, ge=1, le=50)


class SearchResponse(BaseModel):
    results: list[Source]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20_000)


class ChatRequest(BaseModel):
    question: QueryText
    history: list[ChatMessage] = Field(default_factory=list, max_length=MAX_HISTORY_MESSAGES)
