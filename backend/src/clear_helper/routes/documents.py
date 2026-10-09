"""Document upload, listing, download, deletion and re-processing (tenant of the token only)."""

from __future__ import annotations

import hashlib
import logging
import unicodedata
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError

from clear_helper.deps import (
    CurrentUser,
    JobQueueDep,
    SessionDep,
    SettingsDep,
    StorageDep,
    VectorStoreDep,
)
from clear_helper.extraction import CONTENT_TYPES, detect_format
from clear_helper.jobs import QueueError
from clear_helper.models import Document, DocumentStatus
from clear_helper.repositories import get_document, get_document_by_sha256, list_documents
from clear_helper.schemas import DocumentListResponse, DocumentOut, DuplicateDocumentResponse
from clear_helper.storage import ObjectNotFoundError, StorageError, document_key
from clear_helper.vectorstore import VectorStoreError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

DUPLICATE_DETAIL = "Documento já enviado"
QUEUE_FAILED_ERROR = "Falha ao enfileirar a ingestão; tente reprocessar"
DEFAULT_FILENAME = "documento"
_DETECTION_HEAD_BYTES = 8192


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")


def _unavailable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


def content_disposition(filename: str) -> str:
    """Inline disposition; the stored name is the original one, so neutralize it here."""
    fallback = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    fallback = "".join(ch for ch in fallback if ch.isprintable() and ch not in '"\\')
    fallback = fallback.strip() or DEFAULT_FILENAME
    return f"inline; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def _duplicate(document_id: uuid.UUID) -> JSONResponse:
    body = DuplicateDocumentResponse(detail=DUPLICATE_DETAIL, document_id=document_id)
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump(mode="json"))


async def _get_or_404(session: SessionDep, user: CurrentUser, document_id: uuid.UUID) -> Document:
    document = await get_document(session, tenant_id=user.tenant_id, document_id=document_id)
    if document is None:
        raise _not_found()
    return document


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentOut,
    responses={
        status.HTTP_409_CONFLICT: {"model": DuplicateDocumentResponse},
        status.HTTP_413_CONTENT_TOO_LARGE: {},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {},
    },
)
async def upload_document(
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    jobs: JobQueueDep,
    file: Annotated[UploadFile, File()],
) -> DocumentOut | JSONResponse:
    max_bytes = settings.upload_max_bytes
    too_large = HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail=f"Arquivo maior que o limite de {settings.upload_max_mb} MB",
    )
    if file.size is not None and file.size > max_bytes:
        raise too_large
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise too_large
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo vazio")

    # Keep the original name exactly as sent (it is only metadata: the S3 key uses the id).
    filename = file.filename or DEFAULT_FILENAME
    fmt = detect_format(filename, file.content_type, data[:_DETECTION_HEAD_BYTES])
    if fmt is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato não suportado. Envie PDF, DOCX, TXT, Markdown ou HTML",
        )

    tenant_id = user.tenant_id
    sha256 = hashlib.sha256(data).hexdigest()
    existing = await get_document_by_sha256(session, tenant_id=tenant_id, sha256=sha256)
    if existing is not None:
        return _duplicate(existing.id)

    document_id = uuid.uuid4()
    key = document_key(tenant_id, document_id)
    content_type = CONTENT_TYPES[fmt]
    log_extra = {"tenant_id": str(tenant_id), "document_id": str(document_id)}
    try:
        await storage.put(key, data, content_type)
    except StorageError as exc:
        logger.error("documents.upload_storage_failed", extra={**log_extra, "detail": str(exc)})
        raise _unavailable("Armazenamento indisponível; tente novamente") from exc

    document = Document(
        id=document_id,
        tenant_id=tenant_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        sha256=sha256,
        s3_key=key,
        status=DocumentStatus.UPLOADED,
    )
    session.add(document)
    try:
        await session.commit()
    except IntegrityError:
        # Concurrent upload of the same file won the unique (tenant_id, sha256) race.
        await session.rollback()
        try:
            await storage.delete(key)
        except StorageError as exc:
            logger.warning(
                "documents.orphan_cleanup_failed", extra={**log_extra, "detail": str(exc)}
            )
        winner = await get_document_by_sha256(session, tenant_id=tenant_id, sha256=sha256)
        if winner is None:
            raise
        return _duplicate(winner.id)

    try:
        await jobs.enqueue_ingestion(document_id=document_id, tenant_id=tenant_id)
    except QueueError as exc:
        # The upload itself succeeded; the user can trigger /reprocess later.
        logger.error("documents.enqueue_failed", extra={**log_extra, "detail": str(exc)})
        document.status = DocumentStatus.FAILED
        document.error = QUEUE_FAILED_ERROR
        await session.commit()

    logger.info(
        "documents.uploaded",
        extra={**log_extra, "format": fmt.value, "size_bytes": len(data)},
    )
    return DocumentOut.model_validate(document)


@router.get("", response_model=DocumentListResponse)
async def list_tenant_documents(user: CurrentUser, session: SessionDep) -> DocumentListResponse:
    documents = await list_documents(session, tenant_id=user.tenant_id)
    return DocumentListResponse(items=[DocumentOut.model_validate(doc) for doc in documents])


@router.get("/{document_id}", response_model=DocumentOut)
async def get_tenant_document(
    document_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> DocumentOut:
    return DocumentOut.model_validate(await _get_or_404(session, user, document_id))


@router.get("/{document_id}/file", response_class=StreamingResponse)
async def download_document(
    document_id: uuid.UUID, user: CurrentUser, session: SessionDep, storage: StorageDep
) -> StreamingResponse:
    document = await _get_or_404(session, user, document_id)
    try:
        stream = await storage.open_stream(document.s3_key)
    except ObjectNotFoundError as exc:
        logger.error("documents.file_missing", extra={"document_id": str(document_id)})
        raise _not_found() from exc
    except StorageError as exc:
        raise _unavailable("Armazenamento indisponível; tente novamente") from exc
    return StreamingResponse(
        stream,
        media_type=document.content_type,
        headers={
            "Content-Disposition": content_disposition(document.filename),
            "Content-Length": str(document.size_bytes),
            "X-Content-Type-Options": "nosniff",
            # Uploaded HTML is served from our origin: never let it run scripts.
            "Content-Security-Policy": "sandbox",
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
    vector_store: VectorStoreDep,
) -> Response:
    document = await _get_or_404(session, user, document_id)
    log_extra = {"tenant_id": str(user.tenant_id), "document_id": str(document_id)}
    # Remove derived data first so that a failure leaves the row in place for a retry.
    try:
        await vector_store.delete_document(tenant_id=user.tenant_id, document_id=document_id)
        await storage.delete(document.s3_key)
    except (VectorStoreError, StorageError) as exc:
        logger.error("documents.delete_failed", extra={**log_extra, "detail": str(exc)})
        raise _unavailable("Não foi possível remover o documento; tente novamente") from exc
    await session.delete(document)
    await session.commit()
    logger.info("documents.deleted", extra=log_extra)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentOut
)
async def reprocess_document(
    document_id: uuid.UUID, user: CurrentUser, session: SessionDep, jobs: JobQueueDep
) -> DocumentOut:
    document = await _get_or_404(session, user, document_id)
    log_extra = {"tenant_id": str(user.tenant_id), "document_id": str(document_id)}
    # Commit before enqueueing so the worker never sees (and we never overwrite) a stale state.
    document.status = DocumentStatus.UPLOADED
    document.error = None
    await session.commit()
    try:
        await jobs.enqueue_ingestion(document_id=document_id, tenant_id=user.tenant_id)
    except QueueError as exc:
        logger.error("documents.enqueue_failed", extra={**log_extra, "detail": str(exc)})
        document.status = DocumentStatus.FAILED
        document.error = QUEUE_FAILED_ERROR
        await session.commit()
        raise _unavailable("Fila de processamento indisponível; tente novamente") from exc
    logger.info("documents.reprocess_enqueued", extra=log_extra)
    return DocumentOut.model_validate(document)
