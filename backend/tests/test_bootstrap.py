from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clear_helper.cli import BootstrapError, bootstrap, slugify
from clear_helper.models import Role, Tenant, User
from clear_helper.security import verify_password


def test_slugify() -> None:
    assert slugify("ClearIT Governo São Paulo") == "clearit-governo-sao-paulo"
    with pytest.raises(BootstrapError):
        slugify("!!!")


async def test_bootstrap_is_idempotent(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    kwargs = {
        "tenant_name": "ClearIT",
        "admin_email": "Admin@ClearIT.example",
        "admin_password": "initial-password",
    }

    first = await bootstrap(sessionmaker, **kwargs)
    second = await bootstrap(sessionmaker, **{**kwargs, "admin_password": "other-password"})

    assert (first.tenant_created, first.admin_created) == (True, True)
    assert (second.tenant_created, second.admin_created) == (False, False)

    async with sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Tenant)) == 1
        user = (await session.execute(select(User))).scalar_one()
        assert user.email == "admin@clearit.example"
        assert user.role == Role.ADMIN.value
        # Existing admin is not overwritten by later runs.
        assert verify_password(user.password_hash, "initial-password")


async def test_bootstrap_rejects_short_password(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(BootstrapError):
        await bootstrap(
            sessionmaker, tenant_name="ClearIT", admin_email="a@b.example", admin_password="123"
        )


async def test_bootstrap_rejects_admin_from_other_tenant(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await bootstrap(
        sessionmaker, tenant_name="Tenant A", admin_email="a@b.example", admin_password="password-a"
    )
    with pytest.raises(BootstrapError):
        await bootstrap(
            sessionmaker,
            tenant_name="Tenant B",
            admin_email="a@b.example",
            admin_password="password-b",
        )
