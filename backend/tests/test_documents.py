from __future__ import annotations

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clear_helper.config import Settings
from clear_helper.deps import Services
from clear_helper.models import Document, DocumentStatus, User
from clear_helper.routes.documents import QUEUE_FAILED_ERROR, content_disposition
from clear_helper.storage import document_key
from clear_helper.vectorstore import ChunkPoint
from tests.conftest import auth_headers
from tests.documents_factory import make_pdf
from tests.fakes import RELEVANT_VECTOR, FakeJobQueue, FakeQdrantClient, FakeStorage

PDF_TYPE = "application/pdf"


async def _upload(
    client: httpx.AsyncClient,
    user: User,
    data: bytes,
    filename: str = "lei.pdf",
    content_type: str = PDF_TYPE,
) -> httpx.Response:
    return await client.post(
        "/documents",
        files={"file": (filename, data, content_type)},
        headers=auth_headers(user),
    )


async def test_upload_returns_202_stores_file_and_enqueues(
    client: httpx.AsyncClient,
    admin: User,
    fake_storage: FakeStorage,
    fake_jobs: FakeJobQueue,
) -> None:
    data = make_pdf(["Lei 13.709"])

    response = await _upload(client, admin, data, filename="Lei nº 13.709 (LGPD).pdf")

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {
        "id",
        "filename",
        "content_type",
        "size_bytes",
        "status",
        "error",
        "page_count",
        "chunk_count",
        "pipeline_version",
        "created_at",
        "updated_at",
    }
    document_id = uuid.UUID(body["id"])
    assert body["filename"] == "Lei nº 13.709 (LGPD).pdf"
    assert body["content_type"] == PDF_TYPE
    assert body["size_bytes"] == len(data)
    assert body["status"] == "uploaded"
    key = document_key(admin.tenant_id, document_id)
    assert key == f"tenants/{admin.tenant_id}/documents/{document_id}/original"
    assert fake_storage.objects[key] == (data, PDF_TYPE)
    assert fake_jobs.enqueued == [(document_id, admin.tenant_id)]


async def test_duplicate_upload_returns_409_with_existing_id(
    client: httpx.AsyncClient, admin: User, fake_jobs: FakeJobQueue
) -> None:
    data = make_pdf(["Lei 14.133"])
    first = await _upload(client, admin, data)

    second = await _upload(client, admin, data, filename="copia.pdf")

    assert second.status_code == 409
    assert second.json() == {"detail": "Documento já enviado", "document_id": first.json()["id"]}
    assert len(fake_jobs.enqueued) == 1


async def test_same_file_in_another_tenant_is_not_a_duplicate(
    client: httpx.AsyncClient, admin: User, other_user: User
) -> None:
    data = make_pdf(["Lei 12.527"])
    assert (await _upload(client, admin, data)).status_code == 202
    assert (await _upload(client, other_user, data)).status_code == 202


async def test_upload_too_large_returns_413(
    client: httpx.AsyncClient, admin: User, settings: Settings, fake_storage: FakeStorage
) -> None:
    data = b"a" * (settings.upload_max_bytes + 1)

    response = await _upload(client, admin, data, filename="grande.txt", content_type="text/plain")

    assert response.status_code == 413
    assert fake_storage.objects == {}


async def test_unsupported_type_returns_415(client: httpx.AsyncClient, admin: User) -> None:
    response = await _upload(
        client, admin, b"\x89PNG\r\n", filename="foto.png", content_type="image/png"
    )
    assert response.status_code == 415


async def test_fake_pdf_returns_415(client: httpx.AsyncClient, admin: User) -> None:
    response = await _upload(client, admin, b"MZ executable", filename="virus.pdf")
    assert response.status_code == 415


async def test_empty_file_returns_400(client: httpx.AsyncClient, admin: User) -> None:
    response = await _upload(client, admin, b"", filename="vazio.txt", content_type="text/plain")
    assert response.status_code == 400


async def test_upload_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.post("/documents", files={"file": ("a.txt", b"abc", "text/plain")})
    assert response.status_code == 401


async def test_storage_failure_returns_503(
    client: httpx.AsyncClient, admin: User, fake_storage: FakeStorage
) -> None:
    fake_storage.fail = True
    response = await _upload(client, admin, b"texto", filename="a.txt", content_type="text/plain")
    assert response.status_code == 503


async def test_queue_failure_keeps_document_as_failed(
    client: httpx.AsyncClient, admin: User, fake_jobs: FakeJobQueue
) -> None:
    fake_jobs.fail = True

    response = await _upload(client, admin, b"texto", filename="a.txt", content_type="text/plain")

    assert response.status_code == 202
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == QUEUE_FAILED_ERROR


async def test_list_is_scoped_to_tenant_and_newest_first(
    client: httpx.AsyncClient, admin: User, other_user: User
) -> None:
    first = await _upload(client, admin, b"um", filename="1.txt", content_type="text/plain")
    second = await _upload(client, admin, b"dois", filename="2.txt", content_type="text/plain")
    await _upload(client, other_user, b"tres", filename="3.txt", content_type="text/plain")

    response = await client.get("/documents", headers=auth_headers(admin))

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [second.json()["id"], first.json()["id"]]


async def test_other_tenant_gets_404_everywhere(
    client: httpx.AsyncClient,
    admin: User,
    other_user: User,
    fake_storage: FakeStorage,
    fake_jobs: FakeJobQueue,
) -> None:
    document_id = (await _upload(client, admin, make_pdf(["x"]))).json()["id"]
    headers = auth_headers(other_user)

    assert (await client.get(f"/documents/{document_id}", headers=headers)).status_code == 404
    assert (await client.get(f"/documents/{document_id}/file", headers=headers)).status_code == 404
    assert (await client.delete(f"/documents/{document_id}", headers=headers)).status_code == 404
    reprocess = await client.post(f"/documents/{document_id}/reprocess", headers=headers)
    assert reprocess.status_code == 404
    assert len(fake_storage.objects) == 1
    assert len(fake_jobs.enqueued) == 1


async def test_get_document_and_unknown_id(client: httpx.AsyncClient, admin: User) -> None:
    document_id = (await _upload(client, admin, make_pdf(["x"]))).json()["id"]
    headers = auth_headers(admin)

    assert (await client.get(f"/documents/{document_id}", headers=headers)).json()["id"] == (
        document_id
    )
    missing = await client.get(f"/documents/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404


async def test_download_streams_original_inline(client: httpx.AsyncClient, admin: User) -> None:
    data = make_pdf(["conteúdo"])
    document_id = (await _upload(client, admin, data, filename="Lei Geral.pdf")).json()["id"]

    response = await client.get(f"/documents/{document_id}/file", headers=auth_headers(admin))

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == PDF_TYPE
    assert response.headers["content-disposition"].startswith('inline; filename="Lei Geral.pdf"')
    assert response.headers["content-security-policy"] == "sandbox"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_delete_removes_storage_vectors_and_row(
    client: httpx.AsyncClient,
    admin: User,
    fake_storage: FakeStorage,
    fake_qdrant: FakeQdrantClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    services: Services,
) -> None:
    document_id = uuid.UUID((await _upload(client, admin, make_pdf(["x"]))).json()["id"])
    await services.vector_store.upsert(
        [
            ChunkPoint(
                tenant_id=admin.tenant_id,
                document_id=document_id,
                filename="lei.pdf",
                page=1,
                chunk_index=0,
                text="x",
                char_start=0,
                char_end=1,
                pipeline_version="baseline-v1",
                embedding_model="bge-m3",
                vector=list(RELEVANT_VECTOR),
            )
        ]
    )

    response = await client.delete(f"/documents/{document_id}", headers=auth_headers(admin))

    assert response.status_code == 204
    assert fake_storage.objects == {}
    assert fake_qdrant.points == {}
    async with sessionmaker() as session:
        assert await session.get(Document, document_id) is None


async def test_delete_keeps_row_when_qdrant_fails(
    client: httpx.AsyncClient, admin: User, fake_qdrant: FakeQdrantClient
) -> None:
    document_id = (await _upload(client, admin, make_pdf(["x"]))).json()["id"]
    fake_qdrant.fail = True

    response = await client.delete(f"/documents/{document_id}", headers=auth_headers(admin))

    assert response.status_code == 503
    assert (
        await client.get(f"/documents/{document_id}", headers=auth_headers(admin))
    ).status_code == 200


async def test_reprocess_resets_status_and_enqueues(
    client: httpx.AsyncClient,
    admin: User,
    fake_jobs: FakeJobQueue,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    document_id = uuid.UUID((await _upload(client, admin, make_pdf(["x"]))).json()["id"])
    async with sessionmaker() as session:
        document = await session.get(Document, document_id)
        assert document is not None
        document.status = DocumentStatus.FAILED
        document.error = "boom"
        await session.commit()

    response = await client.post(f"/documents/{document_id}/reprocess", headers=auth_headers(admin))

    assert response.status_code == 202
    assert response.json()["status"] == "uploaded"
    assert response.json()["error"] is None
    assert fake_jobs.enqueued[-1] == (document_id, admin.tenant_id)
    assert len(fake_jobs.enqueued) == 2


def test_content_disposition_neutralizes_the_original_name() -> None:
    assert content_disposition('a"b ç.pdf') == (
        "inline; filename=\"ab c.pdf\"; filename*=UTF-8''a%22b%20%C3%A7.pdf"
    )
    header = content_disposition("x\r\nSet-Cookie: a=b.pdf")
    assert "\r" not in header
    assert "\n" not in header


async def test_content_type_with_parameters_is_accepted(
    client: httpx.AsyncClient, admin: User
) -> None:
    response = await _upload(
        client, admin, b"texto", filename="lei.txt", content_type="text/plain; charset=utf-8"
    )
    assert response.status_code == 202
    assert response.json()["content_type"] == "text/plain"


async def test_octet_stream_is_inferred_from_the_suffix(
    client: httpx.AsyncClient, admin: User
) -> None:
    response = await _upload(
        client,
        admin,
        make_pdf(["x"]),
        filename="lei.pdf",
        content_type="application/octet-stream",
    )
    assert response.status_code == 202
    assert response.json()["content_type"] == PDF_TYPE
