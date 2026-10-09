import json

import httpx

import run_eval
from run_eval import Api, aggregate, render_markdown


def _sse(*events):
    return "".join(f"event: {n}\ndata: {json.dumps(p)}\n\n" for n, p in events).encode()


def make_api(handler):
    api = Api("http://test/api", timeout=5)
    api.client = httpx.Client(transport=httpx.MockTransport(handler))
    api.token = "t"
    return api


def test_login_search_and_chat_stream():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.url.path == "/api/auth/login":
            return httpx.Response(
                200, json={"access_token": "jwt", "token_type": "bearer", "expires_in": 3600}
            )
        if request.url.path == "/api/search":
            assert json.loads(request.content) == {"query": "q", "top_k": 10}
            return httpx.Response(200, json={"results": [{"ref": 1, "text": "x"}]})
        if request.url.path == "/api/chat":
            body = _sse(
                ("sources", {"sources": [{"ref": 1, "text": "ctx"}]}),
                ("token", {"text": "Resposta [1]"}),
                (
                    "done",
                    {"answer": "Resposta [1]", "refused": False, "usage": None, "latency_ms": 10},
                ),
            )
            return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    api = make_api(handler)
    api.token = None
    api.login("a@b.c", "x")
    assert api.token == "jwt"
    assert api.search("q", 10) == [{"ref": 1, "text": "x"}]
    res, timing = api.chat("q", timeout=5)
    assert res.answer == "Resposta [1]" and res.has_citation and not res.refused
    assert res.sources[0]["text"] == "ctx"
    assert timing["total_ms"] is not None and timing["ttft_ms"] is not None
    assert seen[-1] == ("POST", "/api/chat", "Bearer jwt")


def test_chat_http_error_is_recorded():
    api = make_api(lambda r: httpx.Response(500, text="boom"))
    res, timing = api.chat("q", timeout=5)
    assert res.error.startswith("HTTP 500")
    assert timing["total_ms"] is None


def test_upload_409_is_idempotent(tmp_path):
    f = tmp_path / "lei.txt"
    f.write_text("conteúdo", "utf-8")

    def handler(request):
        assert b'filename="lei.txt"' in request.content
        return httpx.Response(409, json={"detail": "duplicado", "document_id": "abc"})

    status, body = make_api(handler).upload(f)
    assert status == 409 and body["document_id"] == "abc"


def _row(qid, qtype, refused=False, latency=1000.0, mrr=1.0):
    row = {
        "id": qid,
        "type": qtype,
        "question": f"pergunta {qid}",
        "reference_answer": "r",
        "evidence": [],
        "search": [{"score": 0.5}],
        "chat": {
            "answer": "x [1]",
            "refused": refused,
            "refused_flag": False,
            "has_citation": not refused,
            "error": None,
            "latency_ms": latency,
            "ttft_ms": 100.0,
            "server_latency_ms": 900,
            "usage": None,
            "n_sources": 1,
            "contexts": ["c"],
        },
    }
    if qtype != "unanswerable":
        row["retrieval"] = {
            "mrr": mrr,
            **{f"{m}@{k}": mrr for m in ("recall", "hit", "ndcg") for k in (1, 3, 5, 10)},
        }
    return row


def test_aggregate_refusal_rates_and_latency():
    rows = [
        _row("f1", "factual", latency=1000),
        _row("f2", "factual", refused=True, latency=3000, mrr=0.0),
        _row("m1", "multi_hop", latency=2000, mrr=0.5),
        _row("u1", "unanswerable", refused=True, latency=500),
        _row("u2", "unanswerable", refused=False, latency=4000),
    ]
    m = aggregate(rows, skip_chat=False)
    assert m["retrieval"]["all"]["n"] == 3
    assert m["retrieval"]["all"]["mrr"] == 0.5
    assert m["retrieval"]["factual"]["mrr"] == 0.5
    assert m["chat"]["correct_refusal_rate"] == 0.5
    assert m["chat"]["false_refusal_rate"] == 1 / 3
    assert m["chat"]["citation_rate_answered"] == 1.0
    assert m["chat"]["latency_ms"]["p50"] == 2000
    md = render_markdown(
        {
            "meta": {
                "pipeline_version": "baseline-v1",
                "date": "2026-10-09",
                "api_url": "u",
                "tenant": "eval",
                "golden_set": "g",
                "golden_sha256": "0" * 64,
                "limit": None,
                "top_k": 10,
                "skip_chat": False,
                "ragas": False,
                "documents": [],
            },
            "metrics": m,
            "questions": rows,
        }
    )
    assert "| all | 3 |" in md and "Recusa correta" in md and "| u2 | unanswerable |" in md


def test_aggregate_skip_chat_has_no_chat_block():
    rows = [_row("f1", "factual")]
    for r in rows:
        del r["chat"]
    assert "chat" not in aggregate(rows, skip_chat=True)


def test_results_dir_is_inside_eval():
    assert run_eval.RESULTS_DIR.name == "results"
    assert run_eval.RESULTS_DIR.parent == run_eval.EVAL_ROOT
