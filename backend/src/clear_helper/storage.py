"""S3-compatible object storage (Garage) for the original documents.

boto3 is synchronous, so every call runs in a worker thread to keep the event loop free.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from clear_helper.config import Settings

STREAM_CHUNK_BYTES = 64 * 1024

_NOT_FOUND_CODES = frozenset({"NoSuchKey", "404", "NotFound"})


class StorageError(Exception):
    """Raised when the object storage is unavailable or misconfigured."""


class ObjectNotFoundError(StorageError):
    """Raised when the requested object does not exist."""


def document_key(tenant_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f"tenants/{tenant_id}/documents/{document_id}/original"


def _is_not_found(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    return code in _NOT_FOUND_CODES


class ObjectStorage:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._bucket = settings.s3_bucket
        if client is not None:
            self._client = client
            return
        if settings.s3_access_key is None or settings.s3_secret_key is None:
            raise StorageError("S3 credentials are not configured")
        # boto3 clients are thread-safe, so one instance serves every request.
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            config=BotoConfig(
                connect_timeout=5,
                read_timeout=60,
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"put_object failed: {type(exc).__name__}") from exc

    async def _get_body(self, key: str) -> Any:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise StorageError(f"get_object failed: {type(exc).__name__}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"get_object failed: {type(exc).__name__}") from exc
        return response["Body"]

    async def get_bytes(self, key: str) -> bytes:
        body = await self._get_body(key)
        try:
            data: bytes = await asyncio.to_thread(body.read)
        except BotoCoreError as exc:
            raise StorageError(f"read failed: {type(exc).__name__}") from exc
        finally:
            body.close()
        return data

    async def open_stream(self, key: str) -> AsyncIterator[bytes]:
        """Open the object and return an iterator over its bytes.

        Opening happens eagerly so that a missing object is reported before the HTTP
        response starts; the body is closed when the iterator finishes or is cancelled.
        """
        body = await self._get_body(key)

        async def _iterate() -> AsyncIterator[bytes]:
            try:
                while True:
                    chunk: bytes = await asyncio.to_thread(body.read, STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    yield chunk
            finally:
                body.close()

        return _iterate()

    async def delete(self, key: str) -> None:
        """Delete the object; deleting a missing object is not an error (S3 semantics)."""
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                return
            raise StorageError(f"delete_object failed: {type(exc).__name__}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"delete_object failed: {type(exc).__name__}") from exc
