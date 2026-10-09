"""Retrieval-only search (no LLM), used by the evaluation and for debugging."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from clear_helper.deps import CurrentUser, LLMDep, SettingsDep, VectorStoreDep
from clear_helper.rag import RetrievalError, retrieve
from clear_helper.schemas import SearchRequest, SearchResponse

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    user: CurrentUser,
    settings: SettingsDep,
    llm: LLMDep,
    vector_store: VectorStoreDep,
) -> SearchResponse:
    try:
        results = await retrieve(
            query=body.query,
            tenant_id=user.tenant_id,
            top_k=body.top_k or settings.retrieval_top_k,
            min_score=settings.retrieval_min_score,
            llm=llm,
            vector_store=vector_store,
        )
    except RetrievalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Falha ao buscar trechos nos documentos",
        ) from exc
    return SearchResponse(results=results)
