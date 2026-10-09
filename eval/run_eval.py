"""clear-helper evaluation runner (Fase 1 contract, section "Avaliação (eval/)").

Steps: login -> idempotent upload of the corpus into the evaluation tenant -> wait for `indexed`
-> /search (Recall@k, Hit@k, MRR, nDCG@k with k in {1,3,5,10}) -> /chat over SSE (answer, refusal,
citations, latency p50/p95) -> optional RAGAS with the local judge behind LiteLLM.

Outputs: results/<YYYY-MM-DD>-<pipeline_version>.json and .md (partial runs with --limit get a
"-limitN" suffix so they never overwrite an official baseline).

Usage (from eval/):
    EVAL_EMAIL=... EVAL_PASSWORD=... uv run python run_eval.py
    uv run python run_eval.py --limit 5 --skip-chat
    uv run python run_eval.py --ragas --judge-base-url http://localhost:4000 --judge-model qwen3
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from ch_eval.corpus import FILES_DIR, SOURCES_FILE, load_sources
from ch_eval.golden import DEFAULT_GOLDEN, load_golden, validate_schema
from ch_eval.metrics import KS, chunk_coverage, mean, percentile, retrieval_scores
from ch_eval.sse import ChatResult, collect_chat, iter_sse

EVAL_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_ROOT / "results"
EVAL_VERSION = "1.0.0"
ANSWERABLE = ("factual", "multi_hop")


# --------------------------------------------------------------------------- API client
class Api:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base = base_url.rstrip("/")
        self.client = httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0))
        self.token: str | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def login(self, email: str, password: str) -> None:
        r = self.client.post(f"{self.base}/auth/login", json={"email": email, "password": password})
        if r.status_code == 401:
            raise SystemExit("login falhou (401): verifique --email/--password")
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def get(self, path: str) -> Any:
        r = self.client.get(f"{self.base}{path}", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def upload(self, path: Path) -> tuple[int, dict[str, Any]]:
        with path.open("rb") as fh:
            files = {"file": (path.name, fh, "text/plain; charset=utf-8")}
            r = self.client.post(f"{self.base}/documents", headers=self._headers(), files=files)
        if r.status_code not in (202, 409):
            raise SystemExit(f"upload de {path.name} falhou: HTTP {r.status_code} {r.text[:300]}")
        return r.status_code, r.json()

    def reprocess(self, doc_id: str) -> None:
        r = self.client.post(f"{self.base}/documents/{doc_id}/reprocess", headers=self._headers())
        r.raise_for_status()

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        r = self.client.post(
            f"{self.base}/search", headers=self._headers(), json={"query": query, "top_k": top_k}
        )
        r.raise_for_status()
        return list(r.json().get("results") or [])

    def chat(self, question: str, timeout: float) -> tuple[ChatResult, dict[str, float | None]]:
        """Stream /chat and measure client-side TTFT and total latency (ms)."""
        t0 = time.perf_counter()
        first_token: float | None = None
        events = []
        headers = {**self._headers(), "Accept": "text/event-stream"}
        body = {"question": question, "history": []}
        try:
            with self.client.stream(
                "POST",
                f"{self.base}/chat",
                headers=headers,
                json=body,
                timeout=httpx.Timeout(timeout, connect=10.0),
            ) as r:
                if r.status_code != 200:
                    r.read()
                    res = ChatResult(error=f"HTTP {r.status_code}: {r.text[:300]}")
                    return res, {"ttft_ms": None, "total_ms": None}
                for ev in iter_sse(r.iter_lines()):
                    if ev.event == "token" and first_token is None:
                        first_token = time.perf_counter()
                    events.append(ev)
        except httpx.HTTPError as exc:
            res = collect_chat(events)
            res.error = res.error or f"{type(exc).__name__}: {exc}"
            return res, {"ttft_ms": None, "total_ms": None}
        total = (time.perf_counter() - t0) * 1000
        ttft = (first_token - t0) * 1000 if first_token else None
        return collect_chat(events), {"ttft_ms": ttft, "total_ms": total}


# --------------------------------------------------------------------------- corpus
def ensure_corpus(
    api: Api, files_dir: Path, wait_timeout: float, reprocess_failed: bool
) -> list[dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for src in load_sources(SOURCES_FILE):
        path = files_dir / src.output_file
        if not path.is_file():
            raise SystemExit(f"{path} não existe; rode: uv run python corpus/fetch_corpus.py")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if src.sha256 and sha != src.sha256:
            print(f"AVISO: {path.name} difere do sha256 do sources.yaml", file=sys.stderr)
        status, body = api.upload(path)
        doc_id = body["id"] if status == 202 else body["document_id"]
        print(f"  {path.name}: {'enviado' if status == 202 else 'já existia'} ({doc_id})")
        docs[doc_id] = {"source_id": src.id, "filename": path.name, "sha256": sha}

    deadline = time.monotonic() + wait_timeout
    reprocessed: set[str] = set()
    while True:
        pending = []
        for doc_id, info in docs.items():
            d = api.get(f"/documents/{doc_id}")
            info.update(
                {
                    k: d.get(k)
                    for k in (
                        "status",
                        "error",
                        "chunk_count",
                        "page_count",
                        "pipeline_version",
                        "size_bytes",
                    )
                }
            )
            if d["status"] == "failed":
                if reprocess_failed and doc_id not in reprocessed:
                    print(f"  {info['filename']}: failed ({d.get('error')}); reprocessando")
                    api.reprocess(doc_id)
                    reprocessed.add(doc_id)
                    pending.append(doc_id)
                    continue
                raise SystemExit(
                    f"ingestão de {info['filename']} falhou: {d.get('error')} "
                    "(use --reprocess-failed)"
                )
            if d["status"] != "indexed":
                pending.append(doc_id)
        if not pending:
            break
        if time.monotonic() > deadline:
            raise SystemExit(f"timeout esperando indexação de {len(pending)} documento(s)")
        names = ", ".join(docs[p]["filename"] for p in pending)
        print(f"  aguardando indexação: {names}")
        time.sleep(10)

    others = [d for d in api.get("/documents").get("items", []) if d["id"] not in docs]
    if others:
        print(
            f"AVISO: o tenant tem {len(others)} documento(s) fora do corpus; eles entram na "
            "busca e distorcem as métricas. Use um tenant dedicado ao eval.",
            file=sys.stderr,
        )
    return [{"id": k, **v} for k, v in docs.items()]


# --------------------------------------------------------------------------- RAGAS
def run_ragas(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    """Score answered (non-refused) answerable questions with RAGAS using the LiteLLM judge."""
    os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # no telemetry: on-prem principle
    import warnings

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, ResponseRelevancy
    from ragas.run_config import RunConfig

    eligible = [
        r
        for r in rows
        if r["type"] in ANSWERABLE
        and r.get("chat")
        and not r["chat"]["refused"]
        and not r["chat"]["error"]
        and r["chat"]["contexts"]
    ]
    if not eligible:
        return {"skipped": "nenhuma resposta elegível (respondível, não recusada, com contexto)"}

    api_key = args.judge_api_key or "sk-none"
    extra_body = json.loads(args.judge_extra_body) if args.judge_extra_body else None
    llm = ChatOpenAI(
        model=args.judge_model,
        base_url=args.judge_base_url,
        api_key=api_key,
        temperature=0,
        timeout=args.judge_timeout,
        max_retries=1,
        extra_body=extra_body,
    )
    emb = OpenAIEmbeddings(
        model=args.judge_embedding_model,
        base_url=args.judge_base_url,
        api_key=api_key,
        check_embedding_ctx_length=False,
    )
    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": r["question"],
                "response": r["chat"]["answer"],
                "retrieved_contexts": r["chat"]["contexts"],
                "reference": r["reference_answer"],
            }
            for r in eligible
        ]
    )
    metrics = [Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithReference()]
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=LangchainLLMWrapper(llm),
        embeddings=LangchainEmbeddingsWrapper(emb),
        run_config=RunConfig(
            timeout=args.judge_timeout, max_workers=args.judge_workers, max_retries=2
        ),
        raise_exceptions=False,
        show_progress=True,
    )
    df = result.to_pandas()
    names = [
        c
        for c in df.columns
        if c in ("faithfulness", "answer_relevancy", "llm_context_precision_with_reference")
    ]
    per_q: dict[str, dict[str, float | None]] = {}
    for row, rec in zip(eligible, df.to_dict(orient="records"), strict=True):
        per_q[row["id"]] = {n: _num(rec.get(n)) for n in names}
    summary = {n: mean(v[n] for v in per_q.values()) for n in names}
    failures = {n: sum(1 for v in per_q.values() if v[n] is None) for n in names}
    return {
        "judge_model": args.judge_model,
        "embedding_model": args.judge_embedding_model,
        "n_scored": len(eligible),
        "means": summary,
        "nan_counts": failures,
        "per_question": per_q,
    }


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN -> None


# --------------------------------------------------------------------------- aggregation
def aggregate(rows: list[dict[str, Any]], skip_chat: bool) -> dict[str, Any]:
    answerable = [r for r in rows if r["type"] in ANSWERABLE]
    out: dict[str, Any] = {
        "n_questions": len(rows),
        "n_answerable": len(answerable),
        "n_unanswerable": len(rows) - len(answerable),
    }
    keys = ["mrr"] + [f"{m}@{k}" for m in ("recall", "hit", "ndcg") for k in KS]

    def summarize(subset: list[dict[str, Any]]) -> dict[str, Any]:
        scored = [r["retrieval"] for r in subset if r.get("retrieval")]
        return {"n": len(scored), **{k: mean(s[k] for s in scored) for k in keys}}

    out["retrieval"] = {"all": summarize(answerable)}
    for t in ANSWERABLE:
        out["retrieval"][t] = summarize([r for r in answerable if r["type"] == t])
    out["retrieval"]["search_errors"] = sum(1 for r in rows if r.get("search_error"))

    if skip_chat:
        return out
    chats = [r for r in rows if r.get("chat")]
    ok = [r for r in chats if not r["chat"]["error"]]
    unans = [r for r in ok if r["type"] == "unanswerable"]
    ans = [r for r in ok if r["type"] in ANSWERABLE]
    answered = [r for r in ans if not r["chat"]["refused"]]
    lat = [r["chat"]["latency_ms"] for r in ok if r["chat"]["latency_ms"] is not None]
    ttft = [r["chat"]["ttft_ms"] for r in ok if r["chat"]["ttft_ms"] is not None]
    srv = [
        r["chat"]["server_latency_ms"]
        for r in ok
        if isinstance(r["chat"]["server_latency_ms"], int | float)
    ]
    out["chat"] = {
        "n": len(chats),
        "errors": len(chats) - len(ok),
        "correct_refusal_rate": _rate(sum(r["chat"]["refused"] for r in unans), len(unans)),
        "false_refusal_rate": _rate(sum(r["chat"]["refused"] for r in ans), len(ans)),
        "api_refusals_no_context": sum(r["chat"]["refused_flag"] for r in ok),
        "citation_rate_answered": _rate(
            sum(r["chat"]["has_citation"] for r in answered), len(answered)
        ),
        "latency_ms": {
            "p50": percentile(lat, 50),
            "p95": percentile(lat, 95),
            "max": max(lat) if lat else None,
        },
        "ttft_ms": {"p50": percentile(ttft, 50), "p95": percentile(ttft, 95)},
        "server_latency_ms": {"p50": percentile(srv, 50), "p95": percentile(srv, 95)},
    }
    return out


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


# --------------------------------------------------------------------------- report
def _fmt(v: Any, pct: bool = False, digits: int = 3) -> str:
    if v is None:
        return "n/d"
    if isinstance(v, float):
        return f"{v * 100:.1f}%" if pct else f"{v:.{digits}f}"
    return str(v)


def render_markdown(report: dict[str, Any]) -> str:
    m, meta = report["metrics"], report["meta"]
    lines = [
        f"# Avaliação clear-helper: {meta['pipeline_version']} ({meta['date']})",
        "",
        f"- API: `{meta['api_url']}` | tenant: `{meta.get('tenant') or 'n/d'}`",
        f"- Golden set: `{meta['golden_set']}` (sha256 `{meta['golden_sha256'][:12]}`), "
        f"{m['n_questions']} perguntas ({m['n_answerable']} respondíveis, "
        f"{m['n_unanswerable']} sem resposta){' **parcial: --limit**' if meta['limit'] else ''}",
        f"- Busca: top_k={meta['top_k']} | chat: {'pulado' if meta['skip_chat'] else 'sim'} | "
        f"RAGAS: {'sim' if meta['ragas'] else 'não'}",
        "- Documentos: "
        + ", ".join(
            f"`{d['filename']}` ({d.get('chunk_count')} chunks, {d.get('pipeline_version')})"
            for d in meta["documents"]
        ),
        "",
        "## Recuperação (`/search`, só perguntas respondíveis)",
        "",
        "| Subconjunto | n | MRR | "
        + " | ".join(f"Recall@{k}" for k in KS)
        + " | "
        + " | ".join(f"nDCG@{k}" for k in KS)
        + " | Hit@5 |",
        "|---|---|---|" + "---|" * (2 * len(KS)) + "---|",
    ]
    for name in ("all", *ANSWERABLE):
        r = m["retrieval"][name]
        lines.append(
            f"| {name} | {r['n']} | {_fmt(r['mrr'])} | "
            + " | ".join(_fmt(r[f"recall@{k}"]) for k in KS)
            + " | "
            + " | ".join(_fmt(r[f"ndcg@{k}"]) for k in KS)
            + f" | {_fmt(r['hit@5'])} |"
        )
    if "chat" in m:
        c = m["chat"]
        lines += [
            "",
            "## Resposta (`/chat`)",
            "",
            "| Métrica | Valor |",
            "|---|---|",
            f"| Latência p50 / p95 (cliente, ms) | {_fmt(c['latency_ms']['p50'], digits=0)} / "
            f"{_fmt(c['latency_ms']['p95'], digits=0)} |",
            f"| TTFT p50 / p95 (ms) | {_fmt(c['ttft_ms']['p50'], digits=0)} / "
            f"{_fmt(c['ttft_ms']['p95'], digits=0)} |",
            f"| Latência servidor p50 / p95 (`done.latency_ms`) | "
            f"{_fmt(c['server_latency_ms']['p50'], digits=0)} / "
            f"{_fmt(c['server_latency_ms']['p95'], digits=0)} |",
            f"| Recusa correta (unanswerable) | {_fmt(c['correct_refusal_rate'], pct=True)} |",
            f"| Recusa indevida (respondíveis) | {_fmt(c['false_refusal_rate'], pct=True)} |",
            f"| Respostas com citação [n] | {_fmt(c['citation_rate_answered'], pct=True)} |",
            f"| Recusas da API sem contexto (score mínimo) | {c['api_refusals_no_context']} |",
            f"| Erros | {c['errors']} |",
        ]
    rg = report.get("ragas")
    if rg:
        lines += ["", "## RAGAS", ""]
        if "skipped" in rg or "error" in rg:
            lines.append(f"Não executado: {rg.get('skipped') or rg.get('error')}")
        else:
            lines += [
                f"Juiz `{rg['judge_model']}`, embeddings `{rg['embedding_model']}`, "
                f"{rg['n_scored']} respostas avaliadas.",
                "",
                "| Métrica | Média | Falhas (NaN) |",
                "|---|---|---|",
            ]
            lines += [
                f"| {k} | {_fmt(v)} | {rg['nan_counts'][k]} |" for k, v in rg["means"].items()
            ]
    lines += [
        "",
        "## Detalhes por pergunta",
        "",
        "| id | tipo | MRR | R@5 | top score | recusou | cit. | latência (ms) | pergunta |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["questions"]:
        ret = r.get("retrieval") or {}
        ch = r.get("chat") or {}
        top = r["search"][0]["score"] if r.get("search") else None
        refused = (
            "erro" if ch.get("error") else ("sim" if ch.get("refused") else ("não" if ch else "-"))
        )
        q = r["question"].replace("|", "/")
        lines.append(
            f"| {r['id']} | {r['type']} | {_fmt(ret.get('mrr'), digits=2)} | "
            f"{_fmt(ret.get('recall@5'), digits=2)} | {_fmt(top, digits=3)} | {refused} | "
            f"{'sim' if ch.get('has_citation') else '-'} | "
            f"{_fmt(ch.get('latency_ms'), digits=0)} | {q} |"
        )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- main
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--api-url", default=os.environ.get("EVAL_API_URL", "http://clear-helper.localhost/api")
    )
    ap.add_argument("--email", default=os.environ.get("EVAL_EMAIL"))
    ap.add_argument("--password", default=os.environ.get("EVAL_PASSWORD"))
    ap.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    ap.add_argument("--files", type=Path, default=FILES_DIR, help="corpus convertido")
    ap.add_argument("--limit", type=int, default=None, help="avalia só as N primeiras perguntas")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--skip-chat", action="store_true", help="só /search (sem LLM)")
    ap.add_argument(
        "--skip-upload",
        action="store_true",
        help="não envia o corpus (só confere o que já está no tenant)",
    )
    ap.add_argument("--reprocess-failed", action="store_true")
    ap.add_argument("--index-timeout", type=float, default=3600, help="segundos")
    ap.add_argument("--http-timeout", type=float, default=60, help="segundos (exceto /chat)")
    ap.add_argument("--chat-timeout", type=float, default=600, help="segundos por pergunta")
    ap.add_argument(
        "--pipeline-version",
        default=None,
        help="sobrescreve o pipeline_version lido dos documentos",
    )
    ap.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    # RAGAS (optional) — judge reached through LiteLLM's OpenAI-compatible endpoint
    ap.add_argument("--ragas", action="store_true", help="roda RAGAS (requer o /chat)")
    ap.add_argument(
        "--judge-base-url",
        default=os.environ.get("EVAL_JUDGE_BASE_URL", "http://localhost:4000/v1"),
    )
    ap.add_argument("--judge-api-key", default=os.environ.get("EVAL_JUDGE_API_KEY"))
    ap.add_argument("--judge-model", default=os.environ.get("EVAL_JUDGE_MODEL", "qwen3"))
    ap.add_argument(
        "--judge-embedding-model", default=os.environ.get("EVAL_JUDGE_EMBEDDING_MODEL", "bge-m3")
    )
    ap.add_argument("--judge-timeout", type=float, default=600)
    ap.add_argument("--judge-workers", type=int, default=1)
    ap.add_argument(
        "--judge-extra-body",
        default=os.environ.get("EVAL_JUDGE_EXTRA_BODY"),
        help="JSON repassado ao juiz, ex.: '{\"think\": false}'",
    )
    args = ap.parse_args()
    if not args.email or not args.password:
        ap.error("informe --email/--password ou EVAL_EMAIL/EVAL_PASSWORD")
    if args.ragas and args.skip_chat:
        ap.error("--ragas precisa das respostas do /chat (remova --skip-chat)")
    return args


def main() -> int:
    args = parse_args()
    golden_bytes = args.golden.read_bytes()
    items = load_golden(args.golden)
    bad = {i.get("id"): e for i in items if (e := validate_schema(i))}
    if bad:
        raise SystemExit(f"golden set inválido (rode scripts/validate_golden_set.py): {bad}")
    if args.limit:
        items = items[: args.limit]

    api = Api(args.api_url, args.http_timeout)
    print(f"Login em {args.api_url} ...")
    api.login(args.email, args.password)
    me = api.get("/auth/me")
    tenant = (me.get("tenant") or {}).get("slug")
    print(f"Tenant: {tenant}")

    if args.skip_upload:
        listed = api.get("/documents").get("items", [])
        wanted = {s.output_file for s in load_sources(SOURCES_FILE)}
        documents = [d for d in listed if d["filename"] in wanted]
    else:
        print("Garantindo o corpus no tenant ...")
        documents = ensure_corpus(api, args.files, args.index_timeout, args.reprocess_failed)
    versions = sorted({str(d.get("pipeline_version")) for d in documents})
    pipeline_version = args.pipeline_version or "+".join(versions) or "unknown"

    rows: list[dict[str, Any]] = []
    for n, item in enumerate(items, start=1):
        row: dict[str, Any] = {k: item[k] for k in ("id", "type", "question", "reference_answer")}
        row["evidence"] = item["evidence"]
        try:
            results = api.search(item["question"], args.top_k)
        except httpx.HTTPError as exc:
            row["search_error"] = str(exc)
            results = []
        coverage = chunk_coverage(results, item["evidence"])
        row["search"] = [
            {
                "rank": i + 1,
                "filename": r.get("filename"),
                "page": r.get("page"),
                "chunk_index": r.get("chunk_index"),
                "score": r.get("score"),
                "covers": sorted(c),
                "text_preview": (r.get("text") or "")[:160],
            }
            for i, (r, c) in enumerate(zip(results, coverage, strict=True))
        ]
        if item["type"] in ANSWERABLE and item["evidence"] and not row.get("search_error"):
            row["retrieval"] = retrieval_scores(coverage, len(item["evidence"]))

        if not args.skip_chat:
            res, timing = api.chat(item["question"], args.chat_timeout)
            done = res.done or {}
            row["chat"] = {
                "answer": res.answer,
                "refused": res.refused,
                "refused_flag": res.refused_flag,
                "has_citation": res.has_citation,
                "error": res.error,
                "latency_ms": timing["total_ms"],
                "ttft_ms": timing["ttft_ms"],
                "server_latency_ms": done.get("latency_ms"),
                "usage": done.get("usage"),
                "n_sources": len(res.sources),
                "contexts": [s.get("text", "") for s in res.sources],
            }
        rr = row.get("retrieval", {})
        status = (
            f"MRR={rr.get('mrr', 0):.2f} R@5={rr.get('recall@5', 0):.2f}"
            if rr
            else "(sem métricas de recuperação)"
        )
        if "chat" in row:
            c = row["chat"]
            status += (
                f" | chat {'ERRO' if c['error'] else ('recusou' if c['refused'] else 'ok')}"
                f" {(c['latency_ms'] or 0) / 1000:.1f}s"
            )
        print(f"[{n}/{len(items)}] {item['id']} {status}")
        rows.append(row)

    metrics = aggregate(rows, args.skip_chat)
    report: dict[str, Any] = {
        "meta": {
            "date": dt.date.today().isoformat(),
            "started_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "eval_version": EVAL_VERSION,
            "api_url": args.api_url,
            "tenant": tenant,
            "pipeline_version": pipeline_version,
            "golden_set": str(
                args.golden.relative_to(EVAL_ROOT)
                if args.golden.is_relative_to(EVAL_ROOT)
                else args.golden
            ),
            "golden_sha256": hashlib.sha256(golden_bytes).hexdigest(),
            "limit": args.limit,
            "top_k": args.top_k,
            "skip_chat": args.skip_chat,
            "ragas": args.ragas,
            "documents": documents,
            "python": platform.python_version(),
        },
        "metrics": metrics,
        "questions": rows,
    }
    if args.ragas:
        print("Rodando RAGAS (juiz local via LiteLLM; pode demorar em CPU) ...")
        try:
            report["ragas"] = run_ragas(rows, args)
        except Exception as exc:  # judge failures must not discard the run
            report["ragas"] = {"error": f"{type(exc).__name__}: {exc}"}
        for row in rows:
            per_q = (report["ragas"].get("per_question") or {}).get(row["id"])
            if per_q:
                row["ragas"] = per_q

    args.output_dir.mkdir(parents=True, exist_ok=True)
    safe_version = "".join(ch if ch.isalnum() or ch in "-_.+" else "_" for ch in pipeline_version)
    stem = f"{report['meta']['date']}-{safe_version}" + (
        f"-limit{args.limit}" if args.limit else ""
    )
    json_path = args.output_dir / f"{stem}.json"
    md_path = args.output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    md_path.write_text(render_markdown(report), "utf-8")
    print(f"\nResultados: {json_path}\n            {md_path}")
    r_all = metrics["retrieval"]["all"]
    print(
        f"Recall@5={_fmt(r_all['recall@5'])} MRR={_fmt(r_all['mrr'])} "
        f"nDCG@10={_fmt(r_all['ndcg@10'])}"
    )
    if "chat" in metrics:
        c = metrics["chat"]
        print(
            f"Latência p50/p95={_fmt(c['latency_ms']['p50'], digits=0)}/"
            f"{_fmt(c['latency_ms']['p95'], digits=0)} ms | recusa correta="
            f"{_fmt(c['correct_refusal_rate'], pct=True)} | recusa indevida="
            f"{_fmt(c['false_refusal_rate'], pct=True)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
