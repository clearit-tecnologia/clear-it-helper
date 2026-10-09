"""Baseline RAG: dense retrieval filtered by tenant, pt-BR prompt and streamed answer."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from clear_helper.llm import LiteLLMClient, LLMError, ThinkFilter, Usage
from clear_helper.schemas import ChatMessage, Source
from clear_helper.vectorstore import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)

REFUSAL_TEXT = "Não encontrei essa informação nos documentos enviados."

SYSTEM_PROMPT = f"""Você é o assistente de documentos da ClearIT. Responda sempre em português do \
Brasil.

Regras obrigatórias:
1. Use APENAS as informações dos trechos numerados enviados junto com a pergunta. Não use \
conhecimento externo e não invente fatos, números, datas ou referências.
2. Cite cada afirmação com o número do trecho de origem entre colchetes, por exemplo [1] ou [2][3].
3. Se os trechos não respondem à pergunta, responda exatamente: "{REFUSAL_TEXT}"
4. O histórico da conversa serve apenas para entender a pergunta atual; a resposta deve se \
basear nos trechos.
5. Seja direto e objetivo."""

_REFUSAL_NORMALIZED = re.sub(r"[\W_]+", " ", REFUSAL_TEXT.lower()).strip()


class RetrievalError(Exception):
    """Raised when the query cannot be embedded or the vector store cannot be searched."""


@dataclass(frozen=True, slots=True)
class SSEEvent:
    event: str
    data: dict[str, Any]


def is_refusal(answer: str) -> bool:
    normalized = re.sub(r"[\W_]+", " ", answer.lower()).strip()
    return normalized.startswith(_REFUSAL_NORMALIZED)


async def retrieve(
    *,
    query: str,
    tenant_id: uuid.UUID,
    top_k: int,
    min_score: float,
    llm: LiteLLMClient,
    vector_store: VectorStore,
) -> list[Source]:
    """Return the ``top_k`` chunks of the tenant scoring at least ``min_score``."""
    try:
        [vector] = await llm.embed([query])
        hits = await vector_store.search(
            tenant_id=tenant_id, vector=vector, limit=top_k, score_threshold=min_score
        )
    except (LLMError, VectorStoreError) as exc:
        raise RetrievalError(str(exc)) from exc
    return [
        Source(
            ref=ref,
            document_id=hit.document_id,
            filename=hit.filename,
            page=hit.page,
            chunk_index=hit.chunk_index,
            score=hit.score,
            text=hit.text,
        )
        for ref, hit in enumerate(hits, start=1)
    ]


def build_messages(
    question: str, history: Sequence[ChatMessage], sources: Sequence[Source]
) -> list[dict[str, str]]:
    context = "\n\n".join(
        f"[{source.ref}] Documento: {source.filename}, página {source.page}\n{source.text}"
        for source in sources
    )
    user_message = f"Trechos dos documentos:\n\n{context}\n\nPergunta: {question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *({"role": message.role, "content": message.content} for message in history),
        {"role": "user", "content": user_message},
    ]


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _done(answer: str, *, refused: bool, usage: dict[str, Any] | None, started: float) -> SSEEvent:
    return SSEEvent(
        "done",
        {"answer": answer, "refused": refused, "usage": usage, "latency_ms": _elapsed_ms(started)},
    )


async def chat_events(
    *,
    question: str,
    history: Sequence[ChatMessage],
    tenant_id: uuid.UUID,
    top_k: int,
    min_score: float,
    llm: LiteLLMClient,
    vector_store: VectorStore,
) -> AsyncIterator[SSEEvent]:
    """Yield the SSE events of one answer: sources, token*, then done (or error)."""
    started = time.perf_counter()
    log_extra = {"tenant_id": str(tenant_id)}
    try:
        sources = await retrieve(
            query=question,
            tenant_id=tenant_id,
            top_k=top_k,
            min_score=min_score,
            llm=llm,
            vector_store=vector_store,
        )
    except RetrievalError as exc:
        logger.warning("chat.retrieval_failed", extra={**log_extra, "detail": str(exc)})
        yield SSEEvent("error", {"detail": "Falha ao buscar trechos nos documentos."})
        return

    yield SSEEvent("sources", {"sources": [source.model_dump(mode="json") for source in sources]})

    if not sources:
        # No evidence above the threshold: refuse without calling the LLM.
        logger.info("chat.refused_without_sources", extra=log_extra)
        yield SSEEvent("token", {"text": REFUSAL_TEXT})
        yield _done(REFUSAL_TEXT, refused=True, usage=None, started=started)
        return

    think = ThinkFilter()
    parts: list[str] = []
    usage: dict[str, Any] | None = None
    try:
        async for chunk in llm.stream_chat(build_messages(question, history, sources)):
            if isinstance(chunk, Usage):
                usage = chunk.data
                continue
            text = think.feed(chunk.text)
            if text:
                parts.append(text)
                yield SSEEvent("token", {"text": text})
        tail = think.flush()
    except LLMError as exc:
        logger.warning("chat.llm_failed", extra={**log_extra, "detail": str(exc)})
        yield SSEEvent("error", {"detail": "Falha ao gerar a resposta."})
        return
    if tail:
        parts.append(tail)
        yield SSEEvent("token", {"text": tail})

    answer = "".join(parts).strip()
    if not answer:
        # The model produced only reasoning (or nothing): treat it as a refusal.
        answer = REFUSAL_TEXT
        yield SSEEvent("token", {"text": REFUSAL_TEXT})
    refused = is_refusal(answer)
    logger.info(
        "chat.answered",
        extra={
            **log_extra,
            "sources": len(sources),
            "refused": refused,
            "latency_ms": _elapsed_ms(started),
            "model": llm.chat_model,
        },
    )
    yield _done(answer, refused=refused, usage=usage, started=started)
