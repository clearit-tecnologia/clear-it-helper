"""Retrieval and latency metrics.

Relevance model (contract): a retrieved chunk is relevant when it contains the normalized quote
of an evidence item (same document). Each question has ``n`` evidence items; a chunk may cover
zero, one or several of them. With overlapping chunks the same quote can appear in two chunks,
so metrics count *evidence coverage*, never raw relevant chunks:

- Recall@k: fraction of the evidence items covered by the top-k chunks.
- Hit@k: 1 if at least one top-k chunk is relevant.
- MRR: 1 / rank of the first relevant chunk (0 if none in the returned list).
- nDCG@k: binary gain 1 for a chunk that covers at least one evidence item not covered by a
  higher-ranked chunk (novelty, so duplicates do not inflate the score); the ideal ranking puts
  one new evidence item at each of the first min(k, n) positions.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

from ch_eval.text import normalize

KS = (1, 3, 5, 10)
Coverage = Sequence[frozenset[int]]


def chunk_coverage(
    results: Sequence[dict[str, Any]], evidence: Sequence[dict[str, Any]]
) -> list[frozenset[int]]:
    """For each retrieved chunk, the indices of the evidence items whose quote it contains.

    A chunk only counts for evidence of the same document (``Source.filename`` equals
    ``evidence.document``); if the API does not return a filename, the document is not checked.
    """
    quotes = [(ev.get("document"), normalize(ev.get("quote", ""))) for ev in evidence]
    out = []
    for res in results:
        text = normalize(res.get("text", ""))
        fname = res.get("filename")
        covered = frozenset(
            i
            for i, (doc, q) in enumerate(quotes)
            if q and q in text and (not fname or not doc or fname == doc)
        )
        out.append(covered)
    return out


def recall_at_k(coverage: Coverage, n_evidence: int, k: int) -> float:
    if n_evidence <= 0:
        raise ValueError("recall is undefined without evidence")
    covered: set[int] = set()
    for c in coverage[:k]:
        covered |= c
    return len(covered) / n_evidence


def hit_at_k(coverage: Coverage, k: int) -> float:
    return 1.0 if any(coverage[:k]) else 0.0


def reciprocal_rank(coverage: Coverage) -> float:
    for rank, c in enumerate(coverage, start=1):
        if c:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(coverage: Coverage, n_evidence: int, k: int) -> float:
    if n_evidence <= 0:
        raise ValueError("nDCG is undefined without evidence")
    seen: set[int] = set()
    dcg = 0.0
    for rank, c in enumerate(coverage[:k], start=1):
        new = c - seen
        if new:
            dcg += 1.0 / math.log2(rank + 1)
            seen |= new
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(k, n_evidence) + 1))
    return dcg / ideal


def retrieval_scores(
    coverage: Coverage, n_evidence: int, ks: Iterable[int] = KS
) -> dict[str, float]:
    scores: dict[str, float] = {"mrr": reciprocal_rank(coverage)}
    for k in ks:
        scores[f"recall@{k}"] = recall_at_k(coverage, n_evidence, k)
        scores[f"hit@{k}"] = hit_at_k(coverage, k)
        scores[f"ndcg@{k}"] = ndcg_at_k(coverage, n_evidence, k)
    return scores


def mean(values: Iterable[float | None]) -> float | None:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    return sum(vals) / len(vals) if vals else None


def percentile(values: Iterable[float], p: float) -> float | None:
    """Percentile with linear interpolation between closest ranks (same as numpy 'linear')."""
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    if not 0 <= p <= 100:
        raise ValueError("p must be in [0, 100]")
    pos = (len(data) - 1) * p / 100
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)
