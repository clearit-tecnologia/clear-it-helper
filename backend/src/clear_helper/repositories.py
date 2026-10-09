"""Data access helpers.

Rule: every tenant-owned query receives ``tenant_id`` explicitly. The only exception is
``get_user_by_email_for_login``, which runs before the tenant is known (emails are
globally unique).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from clear_helper.models import Tenant, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_user_by_email_for_login(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == normalize_email(email))
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_user_in_tenant(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> User | None:
    stmt = (
        select(User)
        .options(joinedload(User.tenant))
        .where(User.tenant_id == tenant_id, User.id == user_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_tenant_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    stmt = select(Tenant).where(Tenant.slug == slug)
    return (await session.execute(stmt)).scalar_one_or_none()
