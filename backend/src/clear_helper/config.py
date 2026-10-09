"""Application settings loaded from environment variables prefixed with ``CH_``."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

JWT_ALGORITHM = "HS256"
MIN_JWT_SECRET_LENGTH = 32

_SYNC_POSTGRES_PREFIXES = ("postgresql://", "postgres://")
_ASYNC_POSTGRES_PREFIX = "postgresql+asyncpg://"


def to_async_database_url(url: str) -> str:
    """Convert a plain PostgreSQL URL (e.g. the CloudNativePG ``uri``) to the asyncpg driver."""
    for prefix in _SYNC_POSTGRES_PREFIXES:
        if url.startswith(prefix):
            return _ASYNC_POSTGRES_PREFIX + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://clearhelper:clearhelper@localhost:5432/clearhelper"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    s3_endpoint: str = "http://localhost:3900"
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_bucket: str = "clear-helper-docs"
    s3_region: str = "garage"

    litellm_url: str = "http://localhost:4000"
    litellm_api_key: SecretStr | None = None

    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None

    # Optional here so that the worker, migrations and bootstrap can run without it;
    # the API refuses to start when it is missing (see ``require_jwt_secret``).
    jwt_secret: SecretStr | None = None
    jwt_expires_minutes: int = Field(default=60, gt=0, le=60 * 24 * 7)

    bootstrap_tenant: str | None = None
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None

    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    health_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    # Phase 1: baseline RAG (see docs/arquitetura/fase-1-contrato.md).
    llm_model: str = "qwen3"
    llm_timeout_seconds: float = Field(default=300.0, gt=0, le=3600)
    embedding_model: str = "bge-m3"
    embedding_dim: int = Field(default=1024, gt=0, le=8192)
    qdrant_collection: str = Field(default="chunks_baseline_v1", min_length=1, max_length=255)
    chunk_size: int = Field(default=1000, gt=0, le=100_000)
    chunk_overlap: int = Field(default=200, ge=0)
    retrieval_top_k: int = Field(default=5, gt=0, le=50)
    retrieval_min_score: float = Field(default=0.35, ge=-1.0, le=1.0)
    upload_max_mb: int = Field(default=50, gt=0, le=1024)

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return to_async_database_url(value.strip())

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"CH_JWT_SECRET must have at least {MIN_JWT_SECRET_LENGTH} characters")
        return value

    @model_validator(mode="after")
    def _validate_chunking(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CH_CHUNK_OVERLAP must be smaller than CH_CHUNK_SIZE")
        return self

    @property
    def upload_max_bytes(self) -> int:
        return self.upload_max_mb * 1024 * 1024

    @property
    def is_dev(self) -> bool:
        return self.env.lower() in {"dev", "local", "test"}

    def require_jwt_secret(self) -> str:
        """Return the JWT secret or fail loudly if it is not configured."""
        if self.jwt_secret is None:
            raise RuntimeError("CH_JWT_SECRET is not configured")
        return self.jwt_secret.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
