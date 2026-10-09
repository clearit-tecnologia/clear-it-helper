from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from qdrant_client.http import models as rest

from clear_helper.deps import Services
from clear_helper.models import User
from clear_helper.rag import REFUSAL_TEXT
from clear_helper.vectorstore import ChunkPoint
from tests.conftest import auth_headers
from tests.fakes import RELEVANT_VECTOR, FakeLiteLLM, FakeQdrantClient


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def _index(services: Services, user: User, text: str) -> uuid.UUID:
    document_id = uuid.uuid4()
    await services.vector_store.upsert(
        [
            ChunkPoint(
                tenant_id=user.tenant_id,
                document_id=document_id,
                filename="lgpd.pdf",
                page=2,
                chunk_index=0,
                text=text,
                char_start=0,
                char_end=len(text),
                pipeline_version="baseline-v1",
                embedding_model="bge-m3",
                vector=list(RELEVANT_VECTOR),
            )
        ]
    )
    return document_id


def _query_tenants(fake_qdrant: FakeQdrantClient) -> list[str]:
    tenants: list[str] = []
    for query in fake_qdrant.calls_named("query_points"):
        filter_ = query["query_filter"]
        assert isinstance(filter_, rest.Filter)
        assert isinstance(filter_.must, list)
        for condition in filter_.must:
            if isinstance(condition, rest.FieldCondition) and condition.key == "tenant_id":
                assert isinstance(condition.match, rest.MatchValue)
                tenants.append(str(condition.match.value))
    return tenants


async def test_chat_streams_sources_tokens_and_done(
    client: httpx.AsyncClient,
    admin: User,
    services: Services,
    fake_llm: FakeLiteLLM,
    fake_qdrant: FakeQdrantClient,
) -> None:
    document_id = await _index(services, admin, "Dados pessoais são informações [...]")
    fake_llm.chat_tokens = ["<thi", "nk>vou pensar</th", "ink>\n\n", "Dados pessoais", " são [1]."]

    response = await client.post(
        "/chat",
        json={
            "question": "O que são dados pessoais?",
            "history": [{"role": "user", "content": "Oi"}, {"role": "assistant", "content": "Olá"}],
        },
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert set(names[1:-1]) == {"token"}
    [source] = events[0][1]["sources"]
    assert source == {
        "ref": 1,
        "document_id": str(document_id),
        "filename": "lgpd.pdf",
        "page": 2,
        "chunk_index": 0,
        "score": source["score"],
        "text": "Dados pessoais são informações [...]",
    }
    streamed = "".join(data["text"] for name, data in events if name == "token")
    assert streamed == "Dados pessoais são [1]."
    done = events[-1][1]
    assert done["answer"] == "Dados pessoais são [1]."
    assert done["refused"] is False
    assert done["usage"]["total_tokens"] == 12
    assert isinstance(done["latency_ms"], int)
    # History is forwarded, retrieval uses only the current question.
    [chat_request] = fake_llm.requests_to("/v1/chat/completions")
    assert [m["role"] for m in chat_request["messages"]] == ["system", "user", "assistant", "user"]
    assert fake_llm.requests_to("/v1/embeddings")[-1]["input"] == ["O que são dados pessoais?"]
    assert _query_tenants(fake_qdrant) == [str(admin.tenant_id)]


async def test_chat_refusal_without_sources(
    client: httpx.AsyncClient, admin: User, fake_llm: FakeLiteLLM
) -> None:
    response = await client.post(
        "/chat", json={"question": "Qual a capital?", "history": []}, headers=auth_headers(admin)
    )

    events = _parse_sse(response.text)
    assert events[0] == ("sources", {"sources": []})
    assert events[-1][0] == "done"
    assert events[-1][1]["answer"] == REFUSAL_TEXT
    assert events[-1][1]["refused"] is True
    assert fake_llm.requests_to("/v1/chat/completions") == []


async def test_chat_model_refusal_is_flagged(
    client: httpx.AsyncClient, admin: User, services: Services, fake_llm: FakeLiteLLM
) -> None:
    await _index(services, admin, "Texto sem relação")
    fake_llm.chat_tokens = [REFUSAL_TEXT]

    response = await client.post("/chat", json={"question": "x?"}, headers=auth_headers(admin))

    assert _parse_sse(response.text)[-1][1]["refused"] is True


async def test_chat_llm_failure_emits_error_event(
    client: httpx.AsyncClient, admin: User, services: Services, fake_llm: FakeLiteLLM
) -> None:
    await _index(services, admin, "Trecho")
    fake_llm.chat_status = 500

    response = await client.post("/chat", json={"question": "x?"}, headers=auth_headers(admin))

    events = _parse_sse(response.text)
    assert [name for name, _ in events] == ["sources", "error"]
    assert events[-1][1] == {"detail": "Falha ao gerar a resposta."}


async def test_chat_rejects_long_history(client: httpx.AsyncClient, admin: User) -> None:
    history = [{"role": "user", "content": "x"}] * 11
    response = await client.post(
        "/chat", json={"question": "x?", "history": history}, headers=auth_headers(admin)
    )
    assert response.status_code == 422


async def test_chat_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.post("/chat", json={"question": "x?"})).status_code == 401


async def test_search_filters_by_tenant_and_returns_sources(
    client: httpx.AsyncClient,
    admin: User,
    other_user: User,
    services: Services,
    fake_qdrant: FakeQdrantClient,
    fake_llm: FakeLiteLLM,
) -> None:
    await _index(services, admin, "trecho do admin")
    await _index(services, other_user, "trecho do outro tenant")

    response = await client.post(
        "/search", json={"query": "trecho", "top_k": 3}, headers=auth_headers(other_user)
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [(r["ref"], r["text"]) for r in results] == [(1, "trecho do outro tenant")]
    assert _query_tenants(fake_qdrant) == [str(other_user.tenant_id)]
    [query] = fake_qdrant.calls_named("query_points")
    assert query["limit"] == 3
    assert query["score_threshold"] == 0.35
    assert fake_llm.requests_to("/v1/chat/completions") == []


async def test_search_default_top_k_and_validation(
    client: httpx.AsyncClient, admin: User, fake_qdrant: FakeQdrantClient
) -> None:
    headers = auth_headers(admin)
    assert (await client.post("/search", json={"query": "x"}, headers=headers)).status_code == 200
    assert fake_qdrant.calls_named("query_points")[0]["limit"] == 5
    assert (await client.post("/search", json={"query": "  "}, headers=headers)).status_code == 422
    too_many = await client.post("/search", json={"query": "x", "top_k": 51}, headers=headers)
    assert too_many.status_code == 422


async def test_search_returns_503_when_qdrant_is_down(
    client: httpx.AsyncClient, admin: User, fake_qdrant: FakeQdrantClient
) -> None:
    fake_qdrant.fail = True
    response = await client.post("/search", json={"query": "x"}, headers=auth_headers(admin))
    assert response.status_code == 503
