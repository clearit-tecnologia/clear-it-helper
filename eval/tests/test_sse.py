import json

from ch_eval.sse import collect_chat, iter_sse


def _stream(*events):
    lines = []
    for name, payload in events:
        lines.append(f"event: {name}")
        lines.append("data: " + json.dumps(payload, ensure_ascii=False))
        lines.append("")
    return lines


def test_iter_sse_basic_multiline_comment_and_crlf():
    lines = [
        ": keep-alive",
        "event: token",
        'data: {"text":',
        'data: "oi"}\r',
        "",
        "data: sem-evento",
        "",
    ]
    events = list(iter_sse(lines))
    assert [(e.event, e.data) for e in events] == [
        ("token", '{"text":\n"oi"}'),
        ("message", "sem-evento"),
    ]


def test_iter_sse_dispatches_trailing_event_and_ignores_empty():
    events = list(
        iter_sse(["event: done", "data: {}", "", "event: x", "", "event: y", "data:nospace"])
    )
    assert [(e.event, e.data) for e in events] == [("done", "{}"), ("y", "nospace")]


def test_collect_chat_full_answer():
    src = {
        "ref": 1,
        "document_id": "d",
        "filename": "a.txt",
        "page": 1,
        "chunk_index": 0,
        "score": 0.8,
        "text": "trecho",
    }
    lines = _stream(
        ("sources", {"sources": [src]}),
        ("token", {"text": "O prazo é de 20 dias "}),
        ("token", {"text": "[1]."}),
        (
            "done",
            {
                "answer": "O prazo é de 20 dias [1].",
                "refused": False,
                "usage": None,
                "latency_ms": 1234,
            },
        ),
    )
    res = collect_chat(iter_sse(lines))
    assert res.sources == [src]
    assert res.answer == "O prazo é de 20 dias [1]."
    assert not res.refused
    assert res.has_citation
    assert res.done["latency_ms"] == 1234


def test_collect_chat_refusal_by_flag_and_by_text():
    flag = collect_chat(
        iter_sse(
            _stream(
                ("sources", {"sources": []}),
                (
                    "done",
                    {
                        "answer": "Não encontrei essa informação nos documentos enviados.",
                        "refused": True,
                        "usage": None,
                        "latency_ms": 5,
                    },
                ),
            )
        )
    )
    assert flag.refused and flag.refused_flag
    text = collect_chat(
        iter_sse(
            _stream(
                ("token", {"text": "Os trechos fornecidos não mencionam esse valor."}),
                (
                    "done",
                    {
                        "answer": "Os trechos fornecidos não mencionam esse valor.",
                        "refused": False,
                        "usage": None,
                        "latency_ms": 5,
                    },
                ),
            )
        )
    )
    assert text.refused and not text.refused_flag
    normal = collect_chat(
        iter_sse(
            _stream(
                (
                    "done",
                    {
                        "answer": "A LAI prevê recurso em 10 dias [1].",
                        "refused": False,
                        "usage": None,
                        "latency_ms": 5,
                    },
                ),
            )
        )
    )
    assert not normal.refused


def test_collect_chat_error_and_fallback_to_tokens():
    res = collect_chat(
        iter_sse(
            _stream(
                ("token", {"text": "parcial"}),
                ("error", {"detail": "LLM timeout"}),
            )
        )
    )
    assert res.error == "LLM timeout"
    assert res.answer == "parcial"
    assert res.done is None
