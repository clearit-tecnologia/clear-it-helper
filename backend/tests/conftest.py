from __future__ import annotations

import os

# Must be set before importing clear_helper.main (it builds the app at import time).
os.environ.setdefault("CH_ENV", "test")
os.environ.setdefault("CH_JWT_SECRET", "test-secret-with-at-least-32-characters!")
os.environ.setdefault("CH_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from clear_helper.config import Settings, get_settings
from clear_helper.db import get_session
from clear_helper.main import create_app
from clear_helper.models import Base, Role, Tenant, User
from clear_helper.security import hash_password

JWT_SECRET = "test-secret-with-at-least-32-characters!"
ADMIN_EMAIL = "admin@clearit.example"
ADMIN_PASSWORD = "correct-horse-battery"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        jwt_secret=SecretStr(JWT_SECRET),
        jwt_expires_minutes=60,
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def admin(sessionmaker: async_sessionmaker[AsyncSession]) -> User:
    async with sessionmaker() as session:
        tenant = Tenant(name="ClearIT", slug="clearit")
        session.add(tenant)
        await session.flush()
        user = User(
            tenant_id=tenant.id,
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            role=Role.ADMIN.value,
        )
        session.add(user)
        await session.commit()
        return user


@pytest.fixture
def app(settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]) -> FastAPI:
    application = create_app(settings)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_session] = _session_override
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
