from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from clear_helper.config import Settings, to_async_database_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgresql://u:p@db:5432/app", "postgresql+asyncpg://u:p@db:5432/app"),
        ("postgres://u:p@db:5432/app", "postgresql+asyncpg://u:p@db:5432/app"),
        ("postgresql+asyncpg://u:p@db/app", "postgresql+asyncpg://u:p@db/app"),
        ("sqlite+aiosqlite:///:memory:", "sqlite+aiosqlite:///:memory:"),
    ],
)
def test_to_async_database_url(raw: str, expected: str) -> None:
    assert to_async_database_url(raw) == expected


def test_settings_read_ch_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CH_DATABASE_URL", "postgresql://app:secret@clear-helper-pg-rw:5432/app")
    monkeypatch.setenv("CH_REDIS_URL", "redis://clear-helper-redis:6379/0")
    monkeypatch.setenv("CH_JWT_EXPIRES_MINUTES", "15")
    monkeypatch.setenv("CH_CORS_ORIGINS", "http://clear-helper.localhost, http://localhost:3000")
    monkeypatch.setenv("CH_S3_SECRET_KEY", "s3-secret")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://app:secret@clear-helper-pg-rw:5432/app"
    assert settings.redis_url == "redis://clear-helper-redis:6379/0"
    assert settings.jwt_expires_minutes == 15
    assert settings.cors_origins == ["http://clear-helper.localhost", "http://localhost:3000"]
    assert settings.s3_secret_key is not None
    assert "s3-secret" not in repr(settings)


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret=SecretStr("short"), _env_file=None)


def test_require_jwt_secret_fails_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CH_JWT_SECRET", raising=False)
    settings = Settings(_env_file=None)
    with pytest.raises(RuntimeError, match="CH_JWT_SECRET"):
        settings.require_jwt_secret()
