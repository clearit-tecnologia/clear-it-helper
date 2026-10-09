"""Shared FastAPI dependencies."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from clear_helper.config import Settings, get_settings
from clear_helper.db import get_session
from clear_helper.jobs import JobQueue
from clear_helper.llm import LiteLLMClient
from clear_helper.models import User
from clear_helper.repositories import get_user_in_tenant
from clear_helper.security import InvalidTokenError, decode_access_token
from clear_helper.storage import ObjectStorage
from clear_helper.vectorstore import VectorStore

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    settings: SettingsDep,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Resolve the authenticated user (with its tenant loaded) from the bearer token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        claims = decode_access_token(credentials.credentials, secret=settings.require_jwt_secret())
    except InvalidTokenError as exc:
        logger.info("auth.token_rejected", extra={"reason": str(exc)})
        raise _unauthorized() from exc

    user = await get_user_in_tenant(session, tenant_id=claims.tid, user_id=claims.sub)
    if user is None or not user.is_active:
        logger.info("auth.user_rejected", extra={"user_id": str(claims.sub)})
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(slots=True)
class Services:
    """Long-lived clients created in the API lifespan (``app.state.services``)."""

    storage: ObjectStorage
    vector_store: VectorStore
    llm: LiteLLMClient
    jobs: JobQueue


def _services(request: Request) -> Services:
    services = getattr(request.app.state, "services", None)
    if not isinstance(services, Services):
        raise RuntimeError("application services are not initialized")
    return services


def get_storage(request: Request) -> ObjectStorage:
    return _services(request).storage


def get_vector_store(request: Request) -> VectorStore:
    return _services(request).vector_store


def get_llm(request: Request) -> LiteLLMClient:
    return _services(request).llm


def get_job_queue(request: Request) -> JobQueue:
    return _services(request).jobs


StorageDep = Annotated[ObjectStorage, Depends(get_storage)]
VectorStoreDep = Annotated[VectorStore, Depends(get_vector_store)]
LLMDep = Annotated[LiteLLMClient, Depends(get_llm)]
JobQueueDep = Annotated[JobQueue, Depends(get_job_queue)]
