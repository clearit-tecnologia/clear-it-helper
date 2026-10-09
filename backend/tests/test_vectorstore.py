from __future__ import annotations

import uuid

import pytest
from qdrant_client.http import models as rest

from clear_helper.config import Settings
from clear_helper.vectorstore import ChunkPoint, VectorStoreError
from tests.fakes import EMBEDDING_DIM, RELEVANT_VECTOR, FakeQdrantClient, make_vector_store


def _point(tenant_id: uuid.UUID, document_id: uuid.UUID, index: int) -> ChunkPoint:
    return ChunkPoint(
        tenant_id=tenant_id,
        document_id=document_id,
        filename="lei.pdf",
        page=1,
        chunk_index=index,
        text=f"trecho {index}",
        char_start=0,
        char_end=8,
        pipeline_version="baseline-v1",
        embedding_model="bge-m3",
        vector=list(RELEVANT_VECTOR),
    )


def _tenant_values(filter_: rest.Filter) -> list[object]:
    conditions = filter_.must
    assert isinstance(conditions, list)
    return [
        c.match.value
        for c in conditions
        if isinstance(c, rest.FieldCondition)
        and c.key == "tenant_id"
        and isinstance(c.match, rest.MatchValue)
    ]


async def test_ensure_collection_creates_dense_cosine_and_tenant_index(settings: Settings) -> None:
    client = FakeQdrantClient()
    store = make_vector_store(client, settings)

    await store.ensure_collection()
    await store.ensure_collection()  # idempotent and cached

    [created] = client.calls_named("create_collection")
    params = created["vectors_config"]["dense"]
    assert params.size == EMBEDDING_DIM
    assert params.distance == rest.Distance.COSINE
    indexes = {
        c["field_name"]: c["field_schema"] for c in client.calls_named("create_payload_index")
    }
    assert indexes["tenant_id"].is_tenant is True
    assert indexes["tenant_id"].type == rest.KeywordIndexType.KEYWORD
    assert indexes["document_id"].type == rest.KeywordIndexType.KEYWORD
    assert len(client.calls_named("collection_exists")) == 1


async def test_existing_collection_with_other_dimension_is_rejected(settings: Settings) -> None:
    store = make_vector_store(FakeQdrantClient(exists=True, dim=EMBEDDING_DIM + 1), settings)
    with pytest.raises(VectorStoreError, match="dimensions"):
        await store.ensure_collection()


async def test_search_always_filters_by_tenant(settings: Settings) -> None:
    client = FakeQdrantClient()
    store = make_vector_store(client, settings)
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    await store.upsert([_point(tenant_a, uuid.uuid4(), 0), _point(tenant_b, uuid.uuid4(), 0)])

    hits = await store.search(
        tenant_id=tenant_a, vector=list(RELEVANT_VECTOR), limit=5, score_threshold=0.35
    )

    [query] = client.calls_named("query_points")
    assert _tenant_values(query["query_filter"]) == [str(tenant_a)]
    assert query["using"] == "dense"
    assert query["score_threshold"] == 0.35
    assert len(hits) == 1


async def test_upsert_payload_and_deterministic_ids(settings: Settings) -> None:
    client = FakeQdrantClient()
    store = make_vector_store(client, settings)
    tenant_id, document_id = uuid.uuid4(), uuid.uuid4()

    await store.upsert([_point(tenant_id, document_id, 0)])
    await store.upsert([_point(tenant_id, document_id, 0)])

    assert len(client.points) == 1
    [point] = client.points.values()
    assert point.payload == {
        "tenant_id": str(tenant_id),
        "document_id": str(document_id),
        "filename": "lei.pdf",
        "page": 1,
        "chunk_index": 0,
        "text": "trecho 0",
        "char_start": 0,
        "char_end": 8,
        "pipeline_version": "baseline-v1",
        "embedding_model": "bge-m3",
    }


async def test_upsert_rejects_wrong_dimension(settings: Settings) -> None:
    store = make_vector_store(FakeQdrantClient(), settings)
    bad = _point(uuid.uuid4(), uuid.uuid4(), 0)
    object.__setattr__(bad, "vector", [1.0])
    with pytest.raises(VectorStoreError, match="dimensions"):
        await store.upsert([bad])


async def test_delete_document_filters_by_tenant_and_document(settings: Settings) -> None:
    client = FakeQdrantClient()
    store = make_vector_store(client, settings)
    tenant_id, doc_a, doc_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await store.upsert([_point(tenant_id, doc_a, 0), _point(tenant_id, doc_b, 0)])

    # Another tenant cannot delete the document even if it knows its id.
    await store.delete_document(tenant_id=uuid.uuid4(), document_id=doc_a)
    assert len(client.points) == 2

    await store.delete_document(tenant_id=tenant_id, document_id=doc_a)
    assert [p.payload["document_id"] for p in client.points.values() if p.payload] == [str(doc_b)]


async def test_qdrant_failure_becomes_vector_store_error(settings: Settings) -> None:
    store = make_vector_store(FakeQdrantClient(fail=True), settings)
    with pytest.raises(VectorStoreError):
        await store.search(tenant_id=uuid.uuid4(), vector=[1.0], limit=1, score_threshold=None)
