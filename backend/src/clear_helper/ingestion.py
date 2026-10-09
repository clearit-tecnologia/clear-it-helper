"""Baseline ingestion pipeline (``baseline-v1``), executed by the worker.

uploaded -> processing -> indexed | failed. Re-running is idempotent: the document's
points are deleted before the new upsert, and point ids are deterministic.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clear_helper.chunking import chunk_pages
from clear_helper.config import Settings
from clear_helper.extraction import ExtractionError, detect_format, extract
from clear_helper.llm import LiteLLMClient, LLMError
from clear_helper.models import DocumentStatus
from clear_helper.repositories import get_document
from clear_helper.storage import ObjectNotFoundError, ObjectStorage, StorageError
from clear_helper.vectorstore import ChunkPoint, VectorStore, VectorStoreError

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "baseline-v1"
EMBEDDING_BATCH_SIZE = 16
_MAX_ERROR_LENGTH = 500


class IngestionError(Exception):
    """Expected failure; ``str(exc)`` is a short pt-BR message stored in ``documents.error``."""


@dataclass(frozen=True, slots=True)
class IngestionResult:
    status: DocumentStatus
    page_count: int | None = None
    chunk_count: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class IngestionServices:
    sessionmaker: async_sessionmaker[AsyncSession]
    storage: ObjectStorage
    llm: LiteLLMClient
    vector_store: VectorStore
    settings: Settings


@dataclass(frozen=True, slots=True)
class _DocumentInfo:
    filename: str
    content_type: str
    s3_key: str


def _dependency_message(exc: Exception) -> str:
    if isinstance(exc, LLMError):
        return "Falha ao gerar embeddings no LiteLLM; tente reprocessar"
    if isinstance(exc, VectorStoreError):
        return "Falha ao gravar no Qdrant; tente reprocessar"
    return "Falha ao ler o arquivo no armazenamento; tente reprocessar"


async def _start(
    services: IngestionServices, *, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> _DocumentInfo | None:
    async with services.sessionmaker() as session:
        document = await get_document(session, tenant_id=tenant_id, document_id=document_id)
        if document is None:
            return None
        document.status = DocumentStatus.PROCESSING
        document.error = None
        info = _DocumentInfo(document.filename, document.content_type, document.s3_key)
        await session.commit()
        return info


async def _finish(
    services: IngestionServices,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    result: IngestionResult,
) -> bool:
    """Persist the final state; returns ``False`` if the document was deleted meanwhile."""
    async with services.sessionmaker() as session:
        document = await get_document(session, tenant_id=tenant_id, document_id=document_id)
        if document is None:
            return False
        document.status = result.status
        document.error = result.error
        if result.status is DocumentStatus.INDEXED:
            document.page_count = result.page_count
            document.chunk_count = result.chunk_count
            document.pipeline_version = PIPELINE_VERSION
        await session.commit()
        return True


async def _index(
    services: IngestionServices,
    info: _DocumentInfo,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
) -> IngestionResult:
    settings = services.settings
    try:
        data = await services.storage.get_bytes(info.s3_key)
    except ObjectNotFoundError as exc:
        raise IngestionError("Arquivo original não encontrado no armazenamento") from exc

    fmt = detect_format(info.filename, info.content_type, data[:8192])
    if fmt is None:
        raise IngestionError("Formato de arquivo não suportado")
    try:
        extracted = await asyncio.to_thread(extract, data, fmt)
    except ExtractionError as exc:
        raise IngestionError(str(exc)) from exc

    chunks = chunk_pages(extracted.pages, size=settings.chunk_size, overlap=settings.chunk_overlap)
    if not chunks:
        raise IngestionError("Documento sem texto extraível")

    vectors = await services.llm.embed_batched(
        [chunk.text for chunk in chunks], EMBEDDING_BATCH_SIZE
    )
    points = [
        ChunkPoint(
            tenant_id=tenant_id,
            document_id=document_id,
            filename=info.filename,
            page=chunk.page,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            pipeline_version=PIPELINE_VERSION,
            embedding_model=settings.embedding_model,
            vector=vector,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    # Idempotent re-processing: drop every previous point of the document first.
    await services.vector_store.delete_document(tenant_id=tenant_id, document_id=document_id)
    await services.vector_store.upsert(points)
    return IngestionResult(
        status=DocumentStatus.INDEXED,
        page_count=extracted.page_count,
        chunk_count=len(points),
    )


async def run_ingestion(
    services: IngestionServices, *, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> IngestionResult | None:
    """Ingest one document; returns ``None`` when the document no longer exists."""
    log_extra = {"tenant_id": str(tenant_id), "document_id": str(document_id)}
    started = time.perf_counter()

    info = await _start(services, tenant_id=tenant_id, document_id=document_id)
    if info is None:
        logger.warning("ingestion.document_not_found", extra=log_extra)
        return None
    logger.info("ingestion.started", extra=log_extra)

    try:
        result = await _index(services, info, tenant_id=tenant_id, document_id=document_id)
    except IngestionError as exc:
        result = IngestionResult(status=DocumentStatus.FAILED, error=str(exc)[:_MAX_ERROR_LENGTH])
    except (LLMError, VectorStoreError, StorageError) as exc:
        logger.warning("ingestion.dependency_error", extra={**log_extra, "detail": str(exc)})
        result = IngestionResult(status=DocumentStatus.FAILED, error=_dependency_message(exc))
    except Exception:
        logger.exception("ingestion.unexpected_error", extra=log_extra)
        result = IngestionResult(status=DocumentStatus.FAILED, error="Falha inesperada na ingestão")

    if not await _finish(services, tenant_id=tenant_id, document_id=document_id, result=result):
        # Deleted while processing: remove whatever was indexed in the meantime.
        logger.info("ingestion.document_deleted_during_processing", extra=log_extra)
        try:
            await services.vector_store.delete_document(
                tenant_id=tenant_id, document_id=document_id
            )
        except VectorStoreError:
            logger.exception("ingestion.orphan_cleanup_failed", extra=log_extra)
        return None

    logger.info(
        "ingestion.finished",
        extra={
            **log_extra,
            "status": result.status.value,
            "page_count": result.page_count,
            "chunk_count": result.chunk_count,
            "error": result.error,
            "pipeline_version": PIPELINE_VERSION,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return result
