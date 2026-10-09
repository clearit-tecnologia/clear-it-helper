"""Qdrant access for the baseline collection.

Rule: every read and delete is filtered by ``tenant_id``. There is no search without it.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from clear_helper.config import Settings

logger = logging.getLogger(__name__)

DENSE_VECTOR = "dense"

# Fixed namespace so that point ids are deterministic per (document, chunk): re-indexing
# the same document overwrites its points instead of duplicating them.
_POINT_NAMESPACE = uuid.UUID("6f1c3e2a-8d4b-4c1e-9a57-2b0f4d9e7c31")


# Errors raised by qdrant-client for HTTP failures and unreachable servers.
_QDRANT_ERRORS = (UnexpectedResponse, ResponseHandlingException, OSError)


class VectorStoreError(Exception):
    """Raised when Qdrant is unavailable or the collection is incompatible."""


@dataclass(frozen=True, slots=True)
class ChunkPoint:
    tenant_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page: int
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    pipeline_version: str
    embedding_model: str
    vector: list[float]

    @property
    def point_id(self) -> str:
        return str(uuid.uuid5(_POINT_NAMESPACE, f"{self.document_id}:{self.chunk_index}"))

    def payload(self) -> dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "document_id": str(self.document_id),
            "filename": self.filename,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "pipeline_version": self.pipeline_version,
            "embedding_model": self.embedding_model,
        }


@dataclass(frozen=True, slots=True)
class SearchHit:
    document_id: uuid.UUID
    filename: str
    page: int
    chunk_index: int
    score: float
    text: str


def tenant_filter(tenant_id: uuid.UUID, *extra: models.Condition) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(key="tenant_id", match=models.MatchValue(value=str(tenant_id))),
            *extra,
        ]
    )


def _hit_from_point(point: models.ScoredPoint) -> SearchHit | None:
    payload = point.payload or {}
    try:
        return SearchHit(
            document_id=uuid.UUID(str(payload["document_id"])),
            filename=str(payload["filename"]),
            page=int(payload["page"]),
            chunk_index=int(payload["chunk_index"]),
            score=float(point.score),
            text=str(payload["text"]),
        )
    except (KeyError, ValueError, TypeError):
        logger.warning("vectorstore.malformed_point", extra={"point_id": str(point.id)})
        return None


class VectorStore:
    def __init__(self, client: AsyncQdrantClient, *, collection: str, dim: int) -> None:
        self._client = client
        self.collection = collection
        self._dim = dim
        self._ready = False
        self._lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> VectorStore:
        return cls(
            AsyncQdrantClient(url=settings.qdrant_url),
            collection=settings.qdrant_collection,
            dim=settings.embedding_dim,
        )

    async def aclose(self) -> None:
        await self._client.close()

    def is_ready(self) -> bool:
        return self._ready

    async def ensure_collection(self) -> None:
        """Create the collection and payload indexes if missing (idempotent)."""
        if self.is_ready():
            return
        async with self._lock:
            # Re-check: another coroutine may have finished while we waited for the lock.
            if self.is_ready():
                return
            try:
                await self._ensure_collection()
            except _QDRANT_ERRORS as exc:
                raise VectorStoreError(f"cannot prepare collection: {type(exc).__name__}") from exc
            self._ready = True

    async def _ensure_collection(self) -> None:
        if await self._client.collection_exists(self.collection):
            await self._check_dimension()
        else:
            try:
                await self._client.create_collection(
                    self.collection,
                    vectors_config={
                        DENSE_VECTOR: models.VectorParams(
                            size=self._dim, distance=models.Distance.COSINE
                        )
                    },
                )
                logger.info("vectorstore.collection_created", extra={"collection": self.collection})
            except UnexpectedResponse as exc:
                # Another process created it concurrently.
                if exc.status_code != 409:
                    raise
        await self._client.create_payload_index(
            self.collection,
            "tenant_id",
            field_schema=models.KeywordIndexParams(
                type=models.KeywordIndexType.KEYWORD, is_tenant=True
            ),
        )
        await self._client.create_payload_index(
            self.collection,
            "document_id",
            field_schema=models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD),
        )

    async def _check_dimension(self) -> None:
        info = await self._client.get_collection(self.collection)
        vectors = info.config.params.vectors
        params = vectors.get(DENSE_VECTOR) if isinstance(vectors, dict) else None
        if params is None or params.size != self._dim:
            # Changing the embedding model requires a new collection (reindexing rule).
            raise VectorStoreError(
                f"collection {self.collection!r} has no {DENSE_VECTOR!r} vector "
                f"with {self._dim} dimensions"
            )

    async def upsert(self, points: Sequence[ChunkPoint]) -> None:
        if not points:
            return
        await self.ensure_collection()
        for point in points:
            if len(point.vector) != self._dim:
                raise VectorStoreError(
                    f"embedding has {len(point.vector)} dimensions, expected {self._dim}"
                )
        try:
            await self._client.upsert(
                self.collection,
                points=[
                    models.PointStruct(
                        id=point.point_id,
                        vector={DENSE_VECTOR: point.vector},
                        payload=point.payload(),
                    )
                    for point in points
                ],
                wait=True,
            )
        except _QDRANT_ERRORS as exc:
            raise VectorStoreError(f"upsert failed: {type(exc).__name__}") from exc

    async def delete_document(self, *, tenant_id: uuid.UUID, document_id: uuid.UUID) -> None:
        await self.ensure_collection()
        selector = models.FilterSelector(
            filter=tenant_filter(
                tenant_id,
                models.FieldCondition(
                    key="document_id", match=models.MatchValue(value=str(document_id))
                ),
            )
        )
        try:
            await self._client.delete(self.collection, points_selector=selector, wait=True)
        except _QDRANT_ERRORS as exc:
            raise VectorStoreError(f"delete failed: {type(exc).__name__}") from exc

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        vector: list[float],
        limit: int,
        score_threshold: float | None,
    ) -> list[SearchHit]:
        await self.ensure_collection()
        try:
            response = await self._client.query_points(
                self.collection,
                query=vector,
                using=DENSE_VECTOR,
                query_filter=tenant_filter(tenant_id),
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False,
            )
        except _QDRANT_ERRORS as exc:
            raise VectorStoreError(f"search failed: {type(exc).__name__}") from exc
        hits = (_hit_from_point(point) for point in response.points)
        return [hit for hit in hits if hit is not None]
