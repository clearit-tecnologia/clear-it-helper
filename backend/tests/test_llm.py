from __future__ import annotations

import pytest

from clear_helper.config import Settings
from clear_helper.llm import LLMError, TextDelta, ThinkFilter, Usage, strip_think
from tests.fakes import RELEVANT_VECTOR, FakeLiteLLM, make_llm


def _run(tokens: list[str]) -> str:
    think = ThinkFilter()
    return "".join(think.feed(token) for token in tokens) + think.flush()


def test_think_block_in_a_single_token_is_removed() -> None:
    assert _run(["<think>raciocínio</think>\n\nResposta [1]."]) == "Resposta [1]."


def test_think_tags_split_across_tokens_are_removed() -> None:
    tokens = ["<th", "ink>pens", "ando...</", "thi", "nk>", "\n", "Olá", " mundo"]
    assert _run(tokens) == "Olá mundo"


def test_think_filter_char_by_char() -> None:
    text = "Antes <think>oculto <b>x</b></think>depois"
    assert _run(list(text)) == "Antes depois"


def test_text_resembling_a_tag_prefix_is_not_lost() -> None:
    assert _run(["a <t", "abela> b <", "/t"]) == "a <tabela> b </t"


def test_stray_closing_tag_is_dropped() -> None:
    # Some chat templates open the block in the prompt, so only "</think>" is streamed.
    assert _run(["raciocínio implícito", "</think>", "Resposta"]) == "raciocínio implícitoResposta"


def test_unclosed_think_block_is_dropped() -> None:
    assert _run(["Resposta. ", "<think>nunca fecha"]) == "Resposta. "


def test_multiple_blocks_and_no_partial_emission() -> None:
    think = ThinkFilter()
    assert think.feed("<think>a</think>X<thi") == "X"
    assert think.feed("nk>b</think>Y") == "Y"
    assert think.flush() == ""


def test_strip_think_helper() -> None:
    assert strip_think("<think>x</think> ok") == "ok"


async def test_embed_sorts_by_index_and_sends_model(settings: Settings) -> None:
    fake = FakeLiteLLM(embed=lambda text: [float(len(text)), 0.0, 0.0, 0.0])
    client = make_llm(settings, fake)
    try:
        vectors = await client.embed(["a", "bbb"])
    finally:
        await client.aclose()

    assert vectors == [[1.0, 0.0, 0.0, 0.0], [3.0, 0.0, 0.0, 0.0]]
    assert fake.requests_to("/v1/embeddings") == [{"model": "bge-m3", "input": ["a", "bbb"]}]


async def test_embed_batched_splits_requests(settings: Settings) -> None:
    fake = FakeLiteLLM()
    client = make_llm(settings, fake)
    try:
        vectors = await client.embed_batched([f"t{i}" for i in range(5)], batch_size=2)
    finally:
        await client.aclose()

    assert vectors == [RELEVANT_VECTOR] * 5
    assert [len(body["input"]) for body in fake.requests_to("/v1/embeddings")] == [2, 2, 1]


async def test_embed_error_raises_llm_error(settings: Settings) -> None:
    client = make_llm(settings, FakeLiteLLM(embed_status=500))
    try:
        with pytest.raises(LLMError, match="HTTP 500"):
            await client.embed(["x"])
    finally:
        await client.aclose()


async def test_stream_chat_yields_deltas_and_usage(settings: Settings) -> None:
    fake = FakeLiteLLM(chat_tokens=["Olá", " mundo"])
    client = make_llm(settings, fake)
    try:
        chunks = [chunk async for chunk in client.stream_chat([{"role": "user", "content": "x"}])]
    finally:
        await client.aclose()

    assert chunks[:2] == [TextDelta("Olá"), TextDelta(" mundo")]
    assert isinstance(chunks[2], Usage)
    assert chunks[2].data["total_tokens"] == 12
    [body] = fake.requests_to("/v1/chat/completions")
    assert body["model"] == "qwen3"
    assert body["stream"] is True


async def test_stream_chat_http_error_raises(settings: Settings) -> None:
    client = make_llm(settings, FakeLiteLLM(chat_status=404))
    try:
        with pytest.raises(LLMError, match="not found"):
            [chunk async for chunk in client.stream_chat([{"role": "user", "content": "x"}])]
    finally:
        await client.aclose()
