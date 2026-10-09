"""FastAPI application entrypoint: ``uvicorn clear_helper.main:app``."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clear_helper import __version__
from clear_helper.config import Settings, get_settings
from clear_helper.db import dispose_engine
from clear_helper.logging_config import configure_logging
from clear_helper.routes import auth, health

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("api.started", extra={"version": __version__})
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("api.stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    # Fail fast: the API cannot issue or validate tokens without a secret.
    settings.require_jwt_secret()

    app = FastAPI(
        title="clear-helper API",
        version=__version__,
        lifespan=_lifespan,
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
    return app


app = create_app()
