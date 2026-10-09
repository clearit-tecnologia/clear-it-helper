from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clear_helper import cli
from clear_helper.cli import BootstrapError, ensure_user, main
from clear_helper.config import Settings
from clear_helper.models import Role, Tenant, User
from clear_helper.security import verify_password


async def test_ensure_user_creates_tenant_and_member_idempotently(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    kwargs: dict[str, Any] = {
        "tenant_name": "Avaliação RAG",
        "email": "Eval@ClearIT.example",
        "password": "eval-password",
        "role": Role.MEMBER,
    }

    first = await ensure_user(sessionmaker, **kwargs)
    second = await ensure_user(sessionmaker, **{**kwargs, "password": "another-password"})

    assert (first.tenant_created, first.user_created) == (True, True)
    assert (second.tenant_created, second.user_created) == (False, False)
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant))).scalar_one()
        assert (tenant.name, tenant.slug) == ("Avaliação RAG", "avaliacao-rag")
        user = (await session.execute(select(User))).scalar_one()
        assert user.email == "eval@clearit.example"
        assert user.role == Role.MEMBER.value
        assert user.tenant_id == tenant.id
        assert verify_password(user.password_hash, "eval-password")


async def test_ensure_user_reuses_existing_tenant(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await ensure_user(
        sessionmaker,
        tenant_name="Eval",
        email="a@x.example",
        password="password-a",
        role=Role.ADMIN,
    )
    result = await ensure_user(
        sessionmaker,
        tenant_name="eval",
        email="b@x.example",
        password="password-b",
        role=Role.ADMIN,
    )

    assert (result.tenant_created, result.user_created) == (False, True)
    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Tenant)) == 1


async def test_ensure_user_rejects_email_from_other_tenant(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await ensure_user(
        sessionmaker, tenant_name="A", email="a@x.example", password="password-a", role=Role.MEMBER
    )
    with pytest.raises(BootstrapError):
        await ensure_user(
            sessionmaker,
            tenant_name="B",
            email="a@x.example",
            password="password-a",
            role=Role.MEMBER,
        )


class _FakeEngine:
    async def dispose(self) -> None:
        return None


@pytest.fixture
def cli_db(
    monkeypatch: pytest.MonkeyPatch, sessionmaker: async_sessionmaker[AsyncSession]
) -> async_sessionmaker[AsyncSession]:
    """Point the CLI at the in-memory test database."""
    monkeypatch.setattr(cli, "create_engine", lambda _url: _FakeEngine())
    monkeypatch.setattr(cli, "create_sessionmaker", lambda _engine: sessionmaker)
    return sessionmaker


async def test_create_user_command_reads_password_from_env(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    cli_db: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setenv("EVAL_PASSWORD", "super-secret-eval")
    kwargs: dict[str, Any] = {
        "tenant": "Eval",
        "email": "eval@clearit.example",
        "password_env": "EVAL_PASSWORD",
        "role": Role.ADMIN,
    }

    assert await cli._run_create_user(settings, **kwargs) == 0
    assert await cli._run_create_user(settings, **kwargs) == 0  # idempotent

    async with cli_db() as session:
        user = (await session.execute(select(User))).scalar_one()
    assert user.role == Role.ADMIN.value
    assert verify_password(user.password_hash, "super-secret-eval")


async def test_create_user_command_fails_without_password_env(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    cli_db: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.delenv("MISSING_PASSWORD", raising=False)
    code = await cli._run_create_user(
        settings,
        tenant="Eval",
        email="e@x.example",
        password_env="MISSING_PASSWORD",
        role=Role.MEMBER,
    )
    assert code == 1


@pytest.mark.parametrize(
    "extra",
    [
        ["--password", "inline-secret"],  # must not be taken as an abbreviation
        ["--password-env", "V", "--role", "root"],
        [],  # --password-env is required
    ],
)
def test_create_user_command_rejects_invalid_arguments(extra: list[str]) -> None:
    with pytest.raises(SystemExit):
        main(["create-user", "--tenant", "T", "--email", "e@x.example", *extra])
