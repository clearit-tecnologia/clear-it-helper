from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clear_helper.config import Settings
from clear_helper.deps import Services
from clear_helper.extraction import NO_TEXT_PDF_MESSAGE
from clear_helper.ingestion import PIPELINE_VERSION, IngestionServices, run_ingestion
from clear_helper.models import Document, DocumentStatus, User
from clear_helper.storage import document_key
from clear_helper.worker import WorkerSettings, ingest_document
from tests.documents_factory import make_pdf
from tests.fakes import FakeLiteLLM, FakeQdrantClient, FakeStorage


@pytest.fixture
def ingestion(
    services: Services, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings
) -> IngestionServices:
    return IngestionServices(
        sessionmaker=sessionmaker,
        storage=services.storage,
        llm=services.llm,
        vector_store=services.vector_store,
        settings=settings.model_copy(update={"chunk_size": 20, "chunk_overlap": 5}),
    )


async def _create_document(
    sessionmaker: async_sessionmaker[AsyncSession],
    storage: FakeStorage,
    user: User,
    data: bytes,
    filename: str,
    content_type: str,
) -> uuid.UUID:
    document_id = uuid.uuid4()
    key = document_key(user.tenant_id, document_id)
    await storage.put(key, data, content_type)
    async with sessionmaker() as session:
        session.add(
            Document(
                id=document_id,
                tenant_id=user.tenant_id,
                filename=filename,
                content_type=content_type,
                size_bytes=len(data),
                sha256=uuid.uuid4().hex,
                s3_key=key,
            )
        )
        await session.commit()
    return document_id


async def _load(sessionmaker: async_sessionmaker[AsyncSession], document_id: uuid.UUID) -> Document:
    async with sessionmaker() as session:
        document = await session.get(Document, document_id)
        assert document is not None
        return document


async def test_pdf_is_indexed_with_pages_and_payload(
    ingestion: IngestionServices,
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_storage: FakeStorage,
    fake_qdrant: FakeQdrantClient,
    admin: User,
) -> None:
    pdf = make_pdf(["Primeira pagina com texto longo", None, "Terceira"])
    document_id = await _create_document(
        sessionmaker, fake_storage, admin, pdf, "lei.pdf", "application/pdf"
    )

    result = await run_ingestion(ingestion, tenant_id=admin.tenant_id, document_id=document_id)

    assert result is not None
    assert result.status is DocumentStatus.INDEXED
    document = await _load(sessionmaker, document_id)
    assert document.status is DocumentStatus.INDEXED
    assert document.page_count == 3
    assert document.chunk_count == len(fake_qdrant.points) == 3
    assert document.pipeline_version == PIPELINE_VERSION
    assert document.error is None
    payloads = sorted(
        (p.payload for p in fake_qdrant.points.values() if p.payload),
        key=lambda payload: payload["chunk_index"],
    )
    assert [(p["page"], p["chunk_index"]) for p in payloads] == [(1, 0), (1, 1), (3, 2)]
    assert all(p["tenant_id"] == str(admin.tenant_id) for p in payloads)
    assert all(p["embedding_model"] == "bge-m3" for p in payloads)


async def test_reprocessing_is_idempotent(
    ingestion: IngestionServices,
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_storage: FakeStorage,
    fake_qdrant: FakeQdrantClient,
    admin: User,
) -> None:
    document_id = await _create_document(
        sessionmaker, fake_storage, admin, b"a" * 50, "a.txt", "text/plain"
    )

    await run_ingestion(ingestion, tenant_id=admin.tenant_id, document_id=document_id)
    first = set(fake_qdrant.points)
    await run_ingestion(ingestion, tenant_id=admin.tenant_id, document_id=document_id)

    assert set(fake_qdrant.points) == first
    # Old points are deleted before the new upsert.
    names = [name for name, _ in fake_qdrant.calls if name in {"delete", "upsert"}]
    assert names == ["delete", "upsert", "delete", "upsert"]


async def test_scanned_pdf_fails_with_ocr_message(
    ingestion: IngestionServices,
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_storage: FakeStorage,
    fake_qdrant: FakeQdrantClient,
    admin: User,
) -> None:
    document_id = await _create_document(
        sessionmaker, fake_storage, admin, make_pdf([None]), "scan.pdf", "application/pdf"
    )

    await run_ingestion(ingestion, tenant_id=admin.tenant_id, document_id=document_id)

    document = await _load(sessionmaker, document_id)
    assert document.status is DocumentStatus.FAILED
    assert document.error == NO_TEXT_PDF_MESSAGE
    assert fake_qdrant.points == {}


async def test_embedding_failure_marks_failed(
    ingestion: IngestionServices,
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_storage: FakeStorage,
    fake_llm: FakeLiteLLM,
    admin: User,
) -> None:
    fake_llm.embed_status = 503
    document_id = await _create_document(
        sessionmaker, fake_storage, admin, b"texto", "a.txt", "text/plain"
    )

    await run_ingestion(ingestion, tenant_id=admin.tenant_id, document_id=document_id)

    document = await _load(sessionmaker, document_id)
    assert document.status is DocumentStatus.FAILED
    assert document.error is not None
    assert "LiteLLM" in document.error


async def test_missing_original_marks_failed(
    ingestion: IngestionServices,
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_storage: FakeStorage,
    admin: User,
) -> None:
    document_id = await _create_document(
        sessionmaker, fake_storage, admin, b"texto", "a.txt", "text/plain"
    )
    fake_storage.objects.clear()

    await run_ingestion(ingestion, tenant_id=admin.tenant_id, document_id=document_id)

    assert (await _load(sessionmaker, document_id)).status is DocumentStatus.FAILED


async def test_wrong_tenant_or_missing_document_is_ignored(
    ingestion: IngestionServices,
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_storage: FakeStorage,
    admin: User,
    other_user: User,
) -> None:
    document_id = await _create_document(
        sessionmaker, fake_storage, admin, b"texto", "a.txt", "text/plain"
    )

    assert (
        await run_ingestion(ingestion, tenant_id=other_user.tenant_id, document_id=document_id)
    ) is None
    assert (await _load(sessionmaker, document_id)).status is DocumentStatus.UPLOADED


async def test_worker_task_runs_ingestion(
    ingestion: IngestionServices,
    sessionmaker: async_sessionmaker[AsyncSession],
    fake_storage: FakeStorage,
    admin: User,
) -> None:
    document_id = await _create_document(
        sessionmaker, fake_storage, admin, b"texto", "a.txt", "text/plain"
    )
    ctx = {"ingestion": ingestion, "job_id": "j1"}

    status = await ingest_document(ctx, str(document_id), str(admin.tenant_id))

    assert status == "indexed"
    assert await ingest_document(ctx, "not-a-uuid", str(admin.tenant_id)) is None
    assert ingest_document in WorkerSettings.functions
