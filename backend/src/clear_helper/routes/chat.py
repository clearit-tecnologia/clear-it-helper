"""Chat over the tenant's documents, streamed as Server-Sent Events."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from clear_helper.deps import CurrentUser, LLMDep, SessionDep, SettingsDep, VectorStoreDep
from clear_helper.rag import SSEEvent, chat_events
from clear_helper.schemas import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def format_sse(event: SSEEvent) -> str:
    data = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event}\ndata: {data}\n\n"


async def _stream(events: AsyncIterator[SSEEvent]) -> AsyncIterator[str]:
    try:
        async for event in events:
            yield format_sse(event)
    except Exception:
        # Headers are already sent: report the failure as an SSE error event.
        logger.exception("chat.stream_failed")
        yield format_sse(SSEEvent("error", {"detail": "Erro interno ao gerar a resposta."}))


@router.post("/chat", response_class=StreamingResponse)
async def chat(
    body: ChatRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    llm: LLMDep,
    vector_store: VectorStoreDep,
) -> StreamingResponse:
    tenant_id = user.tenant_id
    # The session (used only for authentication) would otherwise keep a pooled connection
    # checked out for the whole stream, which can last minutes on CPU inference.
    await session.close()
    events = chat_events(
        question=body.question,
        history=body.history,
        tenant_id=tenant_id,
        top_k=settings.retrieval_top_k,
        min_score=settings.retrieval_min_score,
        llm=llm,
        vector_store=vector_store,
    )
    return StreamingResponse(_stream(events), media_type="text/event-stream", headers=SSE_HEADERS)
