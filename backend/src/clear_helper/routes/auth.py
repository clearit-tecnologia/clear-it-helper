"""Local JWT authentication endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from clear_helper.deps import CurrentUser, SessionDep, SettingsDep
from clear_helper.models import Role
from clear_helper.repositories import get_user_by_email_for_login
from clear_helper.schemas import LoginRequest, MeResponse, TenantOut, TokenResponse
from clear_helper.security import (
    create_access_token,
    hash_password,
    password_needs_rehash,
    verify_dummy_password,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: SessionDep, settings: SettingsDep) -> TokenResponse:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = await get_user_by_email_for_login(session, body.email)
    if user is None:
        verify_dummy_password(body.password)
        logger.info("auth.login_failed", extra={"reason": "unknown_user"})
        raise invalid
    if not verify_password(user.password_hash, body.password):
        logger.info("auth.login_failed", extra={"reason": "bad_password", "user_id": str(user.id)})
        raise invalid
    if not user.is_active:
        logger.info("auth.login_failed", extra={"reason": "inactive", "user_id": str(user.id)})
        raise invalid

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        await session.commit()

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=Role(user.role),
        secret=settings.require_jwt_secret(),
        expires_minutes=settings.jwt_expires_minutes,
    )
    logger.info("auth.login_succeeded", extra={"user_id": str(user.id)})
    return TokenResponse(access_token=token, expires_in=settings.jwt_expires_minutes * 60)


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        tenant=TenantOut(id=user.tenant.id, name=user.tenant.name, slug=user.tenant.slug),
    )
