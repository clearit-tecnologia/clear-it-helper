"""Validate the golden set: schema, literal quotes present in the corpus, type distribution.

Usage (from eval/):
    uv run python scripts/validate_golden_set.py [--golden golden-set/v1.jsonl] [--strict]

Exit code 0 = valid; 1 = errors. Requires the converted corpus (corpus/fetch_corpus.py).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ch_eval.corpus import FILES_DIR, SOURCES_FILE, load_corpus_texts, load_sources
from ch_eval.golden import (
    DEFAULT_GOLDEN,
    MIN_QUESTIONS,
    TYPE_BANDS,
    TYPES,
    ambiguous_quotes,
    copied_ngrams,
    find_missing_quotes,
    load_golden,
    type_distribution,
    validate_schema,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    ap.add_argument("--sources", type=Path, default=SOURCES_FILE)
    ap.add_argument("--files", type=Path, default=FILES_DIR)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="também falha em avisos (sha256 divergente, pergunta copiando a lei)",
    )
    args = ap.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    sources = load_sources(args.sources)
    corpus = load_corpus_texts(args.files, args.sources)
    for src in sources:
        sha = hashlib.sha256((args.files / src.output_file).read_bytes()).hexdigest()
        if src.sha256 and sha != src.sha256:
            warnings.append(f"{src.output_file}: sha256 difere do sources.yaml (texto mudou?)")

    items = load_golden(args.golden)
    seen: set[str] = set()
    n_quotes = 0
    for item in items:
        qid = item.get("id", "?") if isinstance(item, dict) else "?"
        for err in validate_schema(item, set(corpus)):
            errors.append(f"[{qid}] {err}")
        if not isinstance(item, dict):
            continue
        if qid in seen:
            errors.append(f"[{qid}] id duplicado")
        seen.add(qid)
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        n_quotes += len(evidence)
        for quote in find_missing_quotes(item, corpus):
            errors.append(f"[{qid}] quote NÃO encontrado no corpus: {quote[:90]!r}")
        for quote in ambiguous_quotes(item, corpus):
            warnings.append(f"[{qid}] quote aparece mais de uma vez no corpus: {quote[:70]!r}")
        quotes = [e.get("quote", "") for e in evidence if isinstance(e, dict)]
        if copied_ngrams(str(item.get("question", "")), quotes):
            warnings.append(f"[{qid}] a pergunta repete 8+ palavras seguidas de um quote")

    counts = Counter(i.get("type") for i in items if isinstance(i, dict))
    dist = type_distribution([i for i in items if isinstance(i, dict)])
    if len(items) < MIN_QUESTIONS:
        errors.append(f"golden set com {len(items)} perguntas (mínimo {MIN_QUESTIONS})")
    for t in TYPES:
        lo, hi = TYPE_BANDS[t]
        if not lo <= dist[t] <= hi:
            errors.append(f"proporção de {t} = {dist[t]:.0%} fora da faixa {lo:.0%}-{hi:.0%}")

    reviewed = sum(1 for i in items if isinstance(i, dict) and i.get("reviewed") is True)
    print(f"Golden set: {args.golden}")
    print(f"Perguntas: {len(items)} | quotes verificados: {n_quotes} | revisadas: {reviewed}")
    for t in TYPES:
        print(f"  {t:<13} {counts.get(t, 0):>3}  ({dist[t]:.0%})")
    for w in warnings:
        print(f"AVISO: {w}")
    for e in errors:
        print(f"ERRO: {e}")
    failed = bool(errors) or (args.strict and bool(warnings))
    print("RESULTADO: " + ("FALHOU" if failed else "OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
