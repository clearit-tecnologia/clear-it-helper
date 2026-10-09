"""Background worker (arq): ``python -m clear_helper.worker``.

Tasks:
- ``ping``: validates the queue end to end.
- ``ingest_document``: baseline ingestion pipeline (see ``clear_helper.ingestion``).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, ClassVar

from arq import run_worker
from arq.connections import RedisSettings
from arq.typing import WorkerCoroutine

from clear_helper.config import get_settings
from clear_helper.db import create_engine, create_sessionmaker
from clear_helper.ingestion import IngestionServices, run_ingestion
from clear_helper.llm import LiteLLMClient
from clear_helper.logging_config import configure_logging
from clear_helper.storage import ObjectStorage
from clear_helper.vectorstore import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)

# Large PDFs embedded on CPU can take a long time; arq's default (300 s) is too short.
INGESTION_JOB_TIMEOUT_SECONDS = 60 * 60


async def ping(ctx: dict[str, Any], message: str = "pong") -> str:
    """Example task used to validate the queue end to end."""
    logger.info("worker.ping", extra={"job_id": ctx.get("job_id")})
    return message


async def ingest_document(ctx: dict[str, Any], document_id: str, tenant_id: str) -> str | None:
    """Ingest one document; returns the final status (``None`` if it no longer exists)."""
    services: IngestionServices = ctx["ingestion"]
    try:
        doc_uuid, tenant_uuid = uuid.UUID(document_id), uuid.UUID(tenant_id)
    except ValueError:
        logger.error("worker.invalid_job_args", extra={"job_id": ctx.get("job_id")})
        return None
    result = await run_ingestion(services, tenant_id=tenant_uuid, document_id=doc_uuid)
    return None if result is None else result.status.value


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings.database_url)
    vector_store = VectorStore.from_settings(settings)
    try:
        await vector_store.ensure_collection()
    except VectorStoreError as exc:
        # Retried lazily by the first ingestion.
        logger.warning("worker.qdrant_collection_not_ready", extra={"detail": str(exc)})
    ctx["engine"] = engine
    ctx["ingestion"] = IngestionServices(
        sessionmaker=create_sessionmaker(engine),
        storage=ObjectStorage(settings),
        llm=LiteLLMClient(settings),
        vector_store=vector_store,
        settings=settings,
    )
    logger.info("worker.started")


async def shutdown(ctx: dict[str, Any]) -> None:
    services: IngestionServices | None = ctx.get("ingestion")
    if services is not None:
        await services.llm.aclose()
        await services.vector_store.aclose()
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()
    logger.info("worker.stopped")


class WorkerSettings:
    functions: ClassVar[list[WorkerCoroutine]] = [ping, ingest_document]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = INGESTION_JOB_TIMEOUT_SECONDS
    handle_signals = True


def main() -> None:
    configure_logging(get_settings().log_level)
    run_worker(WorkerSettings)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
