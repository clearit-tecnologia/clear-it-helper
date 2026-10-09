"""FastAPI application entrypoint: ``uvicorn clear_helper.main:app``."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clear_helper import __version__
from clear_helper.config import Settings, get_settings
from clear_helper.db import dispose_engine
from clear_helper.deps import Services
from clear_helper.jobs import JobQueue
from clear_helper.llm import LiteLLMClient
from clear_helper.logging_config import configure_logging
from clear_helper.routes import auth, chat, documents, health, search
from clear_helper.storage import ObjectStorage, StorageError
from clear_helper.vectorstore import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)


def build_services(settings: Settings) -> Services:
    return Services(
        storage=ObjectStorage(settings),
        vector_store=VectorStore.from_settings(settings),
        llm=LiteLLMClient(settings),
        jobs=JobQueue(settings.redis_url),
    )


async def close_services(services: Services) -> None:
    await services.jobs.aclose()
    await services.llm.aclose()
    await services.vector_store.aclose()


def _lifespan_for(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        services: Services | None = None
        try:
            services = build_services(settings)
        except StorageError as exc:
            # Keep /health and /auth available; document routes report 500 until fixed.
            logger.error("api.services_unavailable", extra={"detail": str(exc)})
        if services is not None:
            app.state.services = services
            try:
                await services.vector_store.ensure_collection()
            except VectorStoreError as exc:
                # Retried lazily on first use; the API still starts (see /health/ready).
                logger.warning("api.qdrant_collection_not_ready", extra={"detail": str(exc)})
        logger.info("api.started", extra={"version": __version__})
        try:
            yield
        finally:
            if services is not None:
                await close_services(services)
            await dispose_engine()
            logger.info("api.stopped")

    return _lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    # Fail fast: the API cannot issue or validate tokens without a secret.
    settings.require_jwt_secret()

    app = FastAPI(
        title="clear-helper API",
        version=__version__,
        lifespan=_lifespan_for(settings),
        docs_url="/docs" if settings.is_dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_dev else None,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(search.router)
    app.include_router(chat.router)
    return app


app = create_app()
