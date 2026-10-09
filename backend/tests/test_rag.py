from __future__ import annotations

import uuid

from clear_helper.deps import Services
from clear_helper.rag import (
    REFUSAL_TEXT,
    SYSTEM_PROMPT,
    SSEEvent,
    build_messages,
    chat_events,
    is_refusal,
    retrieve,
)
from clear_helper.schemas import ChatMessage, Source
from clear_helper.vectorstore import ChunkPoint
from tests.fakes import RELEVANT_VECTOR, FakeLiteLLM


async def _index(services: Services, tenant_id: uuid.UUID, texts: list[str]) -> uuid.UUID:
    document_id = uuid.uuid4()
    await services.vector_store.upsert(
        [
            ChunkPoint(
                tenant_id=tenant_id,
                document_id=document_id,
                filename="lgpd.pdf",
                page=index + 1,
                chunk_index=index,
                text=text,
                char_start=0,
                char_end=len(text),
                pipeline_version="baseline-v1",
                embedding_model="bge-m3",
                vector=list(RELEVANT_VECTOR),
            )
            for index, text in enumerate(texts)
        ]
    )
    return document_id


async def _collect(services: Services, question: str, tenant_id: uuid.UUID) -> list[SSEEvent]:
    return [
        event
        async for event in chat_events(
            question=question,
            history=[],
            tenant_id=tenant_id,
            top_k=5,
            min_score=0.35,
            llm=services.llm,
            vector_store=services.vector_store,
        )
    ]


async def test_retrieve_numbers_sources_from_one(services: Services) -> None:
    tenant_id = uuid.uuid4()
    document_id = await _index(services, tenant_id, ["Art. 1º", "Art. 2º"])

    sources = await retrieve(
        query="o que diz o art. 1?",
        tenant_id=tenant_id,
        top_k=5,
        min_score=0.35,
        llm=services.llm,
        vector_store=services.vector_store,
    )

    assert [(s.ref, s.chunk_index, s.page) for s in sources] == [(1, 0, 1), (2, 1, 2)]
    assert all(s.document_id == document_id and s.filename == "lgpd.pdf" for s in sources)


async def test_refuses_without_calling_llm_when_no_chunk_passes_threshold(
    services: Services, fake_llm: FakeLiteLLM
) -> None:
    tenant_id = uuid.uuid4()
    await _index(services, tenant_id, ["Art. 1º"])

    events = await _collect(services, "pergunta irrelevante", tenant_id)

    assert [e.event for e in events] == ["sources", "token", "done"]
    assert events[0].data == {"sources": []}
    assert events[2].data["answer"] == REFUSAL_TEXT
    assert events[2].data["refused"] is True
    assert events[2].data["usage"] is None
    assert fake_llm.requests_to("/v1/chat/completions") == []


async def test_other_tenant_chunks_are_never_used(
    services: Services, fake_llm: FakeLiteLLM
) -> None:
    await _index(services, uuid.uuid4(), ["segredo de outro tenant"])

    events = await _collect(services, "qual o segredo?", uuid.uuid4())

    assert events[0].data == {"sources": []}
    assert events[-1].data["refused"] is True
    assert fake_llm.requests_to("/v1/chat/completions") == []


def test_build_messages_includes_refs_history_and_question() -> None:
    source = Source(
        ref=1,
        document_id=uuid.uuid4(),
        filename="lai.pdf",
        page=4,
        chunk_index=7,
        score=0.9,
        text="Art. 10. Qualquer interessado poderá apresentar pedido de acesso.",
    )
    history = [
        ChatMessage(role="user", content="O que é a LAI?"),
        ChatMessage(role="assistant", content="É a Lei de Acesso à Informação [1]."),
    ]

    messages = build_messages("E o prazo?", history, [source])

    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1:3] == [
        {"role": "user", "content": "O que é a LAI?"},
        {"role": "assistant", "content": "É a Lei de Acesso à Informação [1]."},
    ]
    last = messages[-1]
    assert last["role"] == "user"
    assert "[1] Documento: lai.pdf, página 4\nArt. 10." in last["content"]
    assert last["content"].endswith("Pergunta: E o prazo?")
    assert REFUSAL_TEXT in SYSTEM_PROMPT


def test_is_refusal() -> None:
    assert is_refusal(REFUSAL_TEXT)
    assert is_refusal("não encontrei essa informação nos documentos enviados")
    assert not is_refusal("O prazo é de 20 dias [1].")
