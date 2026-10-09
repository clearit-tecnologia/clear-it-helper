"""LiteLLM proxy client (OpenAI-compatible API): batched embeddings and streaming chat."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from clear_helper.config import Settings

logger = logging.getLogger(__name__)

EMBEDDING_TIMEOUT_SECONDS = 120.0
_CONNECT_TIMEOUT_SECONDS = 10.0
_MAX_ERROR_DETAIL = 200


class LLMError(Exception):
    """Raised when LiteLLM is unreachable or returns an invalid/erroneous response."""


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class Usage:
    data: dict[str, Any]


ChatChunk = TextDelta | Usage


class ThinkFilter:
    """Remove ``<think>...</think>`` blocks from a token stream.

    Tags may be split across tokens, so a possible partial tag at the end of the buffer
    is held back until the next token arrives. A stray ``</think>`` (emitted when the chat
    template already opened the block) is dropped as well, and leading whitespace of the
    answer is trimmed.
    """

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False
        self._started = False

    @staticmethod
    def _partial_suffix(text: str, tag: str) -> int:
        for size in range(min(len(tag) - 1, len(text)), 0, -1):
            if text.endswith(tag[:size]):
                return size
        return 0

    def _emit(self, text: str) -> str:
        if not self._started:
            text = text.lstrip()
            self._started = bool(text)
        return text

    def feed(self, chunk: str) -> str:
        self._buffer += chunk
        out: list[str] = []
        while self._buffer:
            if self._inside:
                end = self._buffer.find(self.CLOSE)
                if end == -1:
                    keep = self._partial_suffix(self._buffer, self.CLOSE)
                    self._buffer = self._buffer[len(self._buffer) - keep :] if keep else ""
                    break
                self._buffer = self._buffer[end + len(self.CLOSE) :]
                self._inside = False
                continue

            open_at = self._buffer.find(self.OPEN)
            close_at = self._buffer.find(self.CLOSE)
            found = [pos for pos in (open_at, close_at) if pos != -1]
            if not found:
                keep = max(
                    self._partial_suffix(self._buffer, self.OPEN),
                    self._partial_suffix(self._buffer, self.CLOSE),
                )
                out.append(self._buffer[: len(self._buffer) - keep])
                self._buffer = self._buffer[len(self._buffer) - keep :]
                break
            first = min(found)
            out.append(self._buffer[:first])
            if first == open_at:
                self._buffer = self._buffer[first + len(self.OPEN) :]
                self._inside = True
            else:
                self._buffer = self._buffer[first + len(self.CLOSE) :]
        return self._emit("".join(out))

    def flush(self) -> str:
        """Return held-back text at the end of the stream (an unclosed block is dropped)."""
        rest = "" if self._inside else self._buffer
        self._buffer = ""
        return self._emit(rest)


def strip_think(text: str) -> str:
    """Remove reasoning blocks from a complete text."""
    think = ThinkFilter()
    return think.feed(text) + think.flush()


def _describe_response(response: httpx.Response) -> str:
    try:
        body = response.json()
        message = body.get("error", {}).get("message") if isinstance(body, dict) else None
    except (ValueError, AttributeError):
        message = None
    detail = f"HTTP {response.status_code}"
    if message:
        detail = f"{detail}: {str(message)[:_MAX_ERROR_DETAIL]}"
    return detail


class LiteLLMClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        headers = {"Content-Type": "application/json"}
        if settings.litellm_api_key is not None:
            headers["Authorization"] = f"Bearer {settings.litellm_api_key.get_secret_value()}"
        self.chat_model = settings.llm_model
        self.embedding_model = settings.embedding_model
        self._chat_timeout = httpx.Timeout(
            settings.llm_timeout_seconds, connect=_CONNECT_TIMEOUT_SECONDS
        )
        self._client = httpx.AsyncClient(
            base_url=settings.litellm_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(EMBEDDING_TIMEOUT_SECONDS, connect=_CONNECT_TIMEOUT_SECONDS),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed ``texts`` in a single request; order matches the input."""
        if not texts:
            return []
        try:
            response = await self._client.post(
                "/v1/embeddings", json={"model": self.embedding_model, "input": list(texts)}
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"embedding request failed: {type(exc).__name__}") from exc
        if response.status_code != httpx.codes.OK:
            raise LLMError(f"embedding request failed: {_describe_response(response)}")
        try:
            items = response.json()["data"]
            ordered = sorted(items, key=lambda item: int(item["index"]))
            vectors = [[float(value) for value in item["embedding"]] for item in ordered]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError("invalid embedding response") from exc
        if len(vectors) != len(texts):
            raise LLMError(f"expected {len(texts)} embeddings, got {len(vectors)}")
        return vectors

    async def embed_batched(self, texts: Sequence[str], batch_size: int) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            vectors.extend(await self.embed(texts[start : start + batch_size]))
        return vectors

    async def stream_chat(self, messages: Sequence[dict[str, str]]) -> AsyncIterator[ChatChunk]:
        """Stream a chat completion, yielding raw text deltas and, at the end, the usage.

        Reasoning blocks are not removed here; see ``ThinkFilter``.
        """
        payload = {
            "model": self.chat_model,
            "messages": list(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            async with self._client.stream(
                "POST", "/v1/chat/completions", json=payload, timeout=self._chat_timeout
            ) as response:
                if response.status_code != httpx.codes.OK:
                    await response.aread()
                    raise LLMError(f"chat request failed: {_describe_response(response)}")
                async for line in response.aiter_lines():
                    for chunk in _parse_sse_line(line):
                        yield chunk
        except httpx.HTTPError as exc:
            raise LLMError(f"chat request failed: {type(exc).__name__}") from exc


def _parse_sse_line(line: str) -> list[ChatChunk]:
    line = line.strip()
    if not line.startswith("data:"):
        return []
    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return []
    try:
        event = json.loads(data)
    except ValueError as exc:
        raise LLMError("invalid chat stream chunk") from exc
    if not isinstance(event, dict):
        raise LLMError("invalid chat stream chunk")
    if "error" in event:
        error = event["error"]
        message = error.get("message") if isinstance(error, dict) else error
        raise LLMError(f"chat stream error: {str(message)[:_MAX_ERROR_DETAIL]}")

    chunks: list[ChatChunk] = []
    for choice in event.get("choices") or []:
        delta = choice.get("delta") or {}
        # Only the visible answer; ``reasoning_content`` (if any) is intentionally ignored.
        content = delta.get("content")
        if isinstance(content, str) and content:
            chunks.append(TextDelta(content))
    usage = event.get("usage")
    if isinstance(usage, dict) and usage:
        chunks.append(Usage(usage))
    return chunks
