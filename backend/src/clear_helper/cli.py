"""Administrative commands: ``python -m clear_helper.cli <command>``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clear_helper.config import Settings, get_settings
from clear_helper.db import create_engine, create_sessionmaker
from clear_helper.logging_config import configure_logging
from clear_helper.models import Role, Tenant, User
from clear_helper.repositories import (
    get_tenant_by_slug,
    get_user_by_email_for_login,
    normalize_email,
)
from clear_helper.security import hash_password

logger = logging.getLogger("clear_helper.cli")

MIN_BOOTSTRAP_PASSWORD_LENGTH = 8


class BootstrapError(Exception):
    """Raised when the bootstrap configuration is invalid or conflicts with existing data."""


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    tenant_created: bool
    admin_created: bool


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    if not slug:
        raise BootstrapError(f"cannot derive a slug from tenant name {value!r}")
    return slug[:100]


async def _bootstrap_once(
    session: AsyncSession, *, tenant_name: str, admin_email: str, admin_password: str
) -> BootstrapResult:
    slug = slugify(tenant_name)
    tenant = await get_tenant_by_slug(session, slug)
    tenant_created = tenant is None
    if tenant is None:
        tenant = Tenant(name=tenant_name, slug=slug)
        session.add(tenant)
        await session.flush()

    email = normalize_email(admin_email)
    user = await get_user_by_email_for_login(session, email)
    admin_created = user is None
    if user is None:
        session.add(
            User(
                tenant_id=tenant.id,
                email=email,
                password_hash=hash_password(admin_password),
                role=Role.ADMIN.value,
                is_active=True,
            )
        )
    elif user.tenant_id != tenant.id:
        raise BootstrapError("bootstrap admin email already belongs to another tenant")
    # An existing admin is left untouched (password/role changes made later are preserved).

    await session.commit()
    return BootstrapResult(tenant_created=tenant_created, admin_created=admin_created)


async def bootstrap(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    tenant_name: str,
    admin_email: str,
    admin_password: str,
) -> BootstrapResult:
    """Idempotently create the initial tenant and its admin user."""
    tenant_name = tenant_name.strip()
    if not tenant_name:
        raise BootstrapError("tenant name is empty")
    if "@" not in admin_email:
        raise BootstrapError("admin email is invalid")
    if len(admin_password) < MIN_BOOTSTRAP_PASSWORD_LENGTH:
        raise BootstrapError(
            f"admin password must have at least {MIN_BOOTSTRAP_PASSWORD_LENGTH} characters"
        )

    # A concurrent run may win the race on the unique constraints; retry once to converge.
    for attempt in (1, 2):
        async with sessionmaker() as session:
            try:
                return await _bootstrap_once(
                    session,
                    tenant_name=tenant_name,
                    admin_email=admin_email,
                    admin_password=admin_password,
                )
            except IntegrityError:
                await session.rollback()
                if attempt == 2:
                    raise
                logger.warning("bootstrap.conflict_retry")
    raise AssertionError("unreachable")


async def _run_bootstrap(settings: Settings) -> int:
    if not (
        settings.bootstrap_tenant
        and settings.bootstrap_admin_email
        and settings.bootstrap_admin_password
    ):
        logger.error(
            "bootstrap.missing_config",
            extra={
                "required": [
                    "CH_BOOTSTRAP_TENANT",
                    "CH_BOOTSTRAP_ADMIN_EMAIL",
                    "CH_BOOTSTRAP_ADMIN_PASSWORD",
                ]
            },
        )
        return 1

    engine = create_engine(settings.database_url)
    try:
        result = await bootstrap(
            create_sessionmaker(engine),
            tenant_name=settings.bootstrap_tenant,
            admin_email=settings.bootstrap_admin_email,
            admin_password=settings.bootstrap_admin_password.get_secret_value(),
        )
    except BootstrapError as exc:
        logger.error("bootstrap.failed", extra={"reason": str(exc)})
        return 1
    finally:
        await engine.dispose()

    logger.info(
        "bootstrap.done",
        extra={"tenant_created": result.tenant_created, "admin_created": result.admin_created},
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m clear_helper.cli")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("bootstrap", help="seed the initial tenant and admin (idempotent)")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)

    if args.command != "bootstrap":
        parser.error(f"unknown command {args.command!r}")
    return asyncio.run(_run_bootstrap(settings))


if __name__ == "__main__":
    sys.exit(main())
