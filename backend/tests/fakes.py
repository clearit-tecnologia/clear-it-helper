"""In-memory fakes for the external services (S3, Qdrant, LiteLLM, arq)."""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as rest

from clear_helper.config import Settings
from clear_helper.jobs import JobQueue, QueueError
from clear_helper.llm import LiteLLMClient
from clear_helper.storage import ObjectNotFoundError, ObjectStorage, StorageError
from clear_helper.vectorstore import VectorStore

EMBEDDING_DIM = 4
RELEVANT_VECTOR = [1.0, 0.0, 0.0, 0.0]
IRRELEVANT_VECTOR = [0.0, 1.0, 0.0, 0.0]
IRRELEVANT_MARKER = "irrelevante"


def fake_embedding(text: str) -> list[float]:
    """Every chunk matches every query, except queries containing ``IRRELEVANT_MARKER``."""
    return IRRELEVANT_VECTOR if IRRELEVANT_MARKER in text.lower() else RELEVANT_VECTOR


class FakeStorage(ObjectStorage):
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.fail = False

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        if self.fail:
            raise StorageError("unavailable")
        self.objects[key] = (data, content_type)

    async def get_bytes(self, key: str) -> bytes:
        if key not in self.objects:
            raise ObjectNotFoundError(key)
        return self.objects[key][0]

    async def open_stream(self, key: str) -> AsyncIterator[bytes]:
        data = await self.get_bytes(key)

        async def _iterate() -> AsyncIterator[bytes]:
            for start in range(0, len(data), 4):
                yield data[start : start + 4]

        return _iterate()

    async def delete(self, key: str) -> None:
        if self.fail:
            raise StorageError("unavailable")
        self.objects.pop(key, None)


class FakeJobQueue(JobQueue):
    def __init__(self) -> None:
        self.enqueued: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.fail = False

    async def enqueue_ingestion(self, *, document_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        if self.fail:
            raise QueueError("redis down")
        self.enqueued.append((document_id, tenant_id))

    async def aclose(self) -> None:
        return None


def _matches(filter_: rest.Filter | None, payload: dict[str, Any]) -> bool:
    if filter_ is None:
        return True
    for condition in filter_.must or []:
        assert isinstance(condition, rest.FieldCondition)
        assert isinstance(condition.match, rest.MatchValue)
        if payload.get(condition.key) != condition.match.value:
            return False
    return True


def _cosine(a: list[float], b: list[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0


@dataclass
class FakeQdrantClient:
    """Implements the subset of ``AsyncQdrantClient`` used by ``VectorStore``."""

    dim: int = EMBEDDING_DIM
    exists: bool = False
    points: dict[str, rest.PointStruct] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    fail: bool = False

    def _record(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))
        if self.fail:
            raise OSError("qdrant down")

    def calls_named(self, name: str) -> list[dict[str, Any]]:
        return [kwargs for call, kwargs in self.calls if call == name]

    async def collection_exists(self, collection_name: str) -> bool:
        self._record("collection_exists", collection_name=collection_name)
        return self.exists

    async def get_collection(self, collection_name: str) -> Any:
        self._record("get_collection", collection_name=collection_name)
        vectors = {"dense": rest.VectorParams(size=self.dim, distance=rest.Distance.COSINE)}
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vectors)))

    async def create_collection(self, collection_name: str, **kwargs: Any) -> bool:
        self._record("create_collection", collection_name=collection_name, **kwargs)
        self.exists = True
        return True

    async def create_payload_index(
        self, collection_name: str, field_name: str, **kwargs: Any
    ) -> Any:
        self._record("create_payload_index", field_name=field_name, **kwargs)
        return None

    async def upsert(self, collection_name: str, points: list[rest.PointStruct], **kw: Any) -> Any:
        self._record("upsert", points=points)
        for point in points:
            self.points[str(point.id)] = point
        return None

    async def delete(self, collection_name: str, points_selector: Any, **kwargs: Any) -> Any:
        self._record("delete", points_selector=points_selector)
        assert isinstance(points_selector, rest.FilterSelector)
        for point_id in [
            pid
            for pid, point in self.points.items()
            if _matches(points_selector.filter, point.payload or {})
        ]:
            del self.points[point_id]
        return None

    async def query_points(self, collection_name: str, **kwargs: Any) -> rest.QueryResponse:
        self._record("query_points", **kwargs)
        query: list[float] = kwargs["query"]
        threshold: float | None = kwargs.get("score_threshold")
        scored: list[rest.ScoredPoint] = []
        for point in self.points.values():
            payload = point.payload or {}
            if not _matches(kwargs.get("query_filter"), payload):
                continue
            vector = cast(dict[str, list[float]], point.vector)["dense"]
            score = _cosine(query, vector)
            if threshold is not None and score < threshold:
                continue
            scored.append(rest.ScoredPoint(id=point.id, version=0, score=score, payload=payload))
        scored.sort(key=lambda p: (-p.score, p.payload["chunk_index"] if p.payload else 0))
        return rest.QueryResponse(points=scored[: kwargs["limit"]])

    async def close(self) -> None:
        return None


def make_vector_store(client: FakeQdrantClient, settings: Settings) -> VectorStore:
    return VectorStore(
        cast(AsyncQdrantClient, client),
        collection=settings.qdrant_collection,
        dim=settings.embedding_dim,
    )


@dataclass
class FakeLiteLLM:
    """``httpx.MockTransport`` handler emulating LiteLLM's OpenAI-compatible endpoints."""

    chat_tokens: list[str] = field(default_factory=lambda: ["Resposta", " [1]."])
    usage: dict[str, Any] | None = field(
        default_factory=lambda: {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
    )
    embed: Callable[[str], list[float]] = fake_embedding
    chat_status: int = 200
    embed_status: int = 200
    requests: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def requests_to(self, path: str) -> list[dict[str, Any]]:
        return [body for url, body in self.requests if url == path]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append((request.url.path, body))
        if request.url.path == "/v1/embeddings":
            if self.embed_status != 200:
                return httpx.Response(self.embed_status, json={"error": {"message": "boom"}})
            # Reverse the order to check that the client sorts by ``index``.
            data = [
                {"object": "embedding", "index": i, "embedding": self.embed(text)}
                for i, text in enumerate(body["input"])
            ][::-1]
            return httpx.Response(200, json={"object": "list", "data": data})
        if request.url.path == "/v1/chat/completions":
            if self.chat_status != 200:
                return httpx.Response(self.chat_status, json={"error": {"message": "not found"}})
            lines = [
                "data: " + json.dumps({"choices": [{"index": 0, "delta": {"content": token}}]})
                for token in self.chat_tokens
            ]
            if self.usage is not None:
                lines.append("data: " + json.dumps({"choices": [], "usage": self.usage}))
            lines.append("data: [DONE]")
            content = "\n\n".join(lines) + "\n\n"
            return httpx.Response(
                200, content=content.encode(), headers={"content-type": "text/event-stream"}
            )
        return httpx.Response(404)


def make_llm(settings: Settings, fake: FakeLiteLLM) -> LiteLLMClient:
    return LiteLLMClient(settings, transport=httpx.MockTransport(fake))
