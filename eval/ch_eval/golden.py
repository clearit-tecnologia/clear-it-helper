"""Golden-set schema (contract: docs/arquitetura/fase-1-contrato.md, "Avaliação (eval/)")."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ch_eval.text import normalize

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden-set"
DEFAULT_GOLDEN = GOLDEN_DIR / "v1.jsonl"

TYPES = ("factual", "multi_hop", "unanswerable")
REQUIRED_KEYS = {"id", "question", "type", "reference_answer", "evidence", "reviewed"}
EVIDENCE_KEYS = {"document", "quote", "locator"}
QUOTE_MIN, QUOTE_MAX = 30, 200
MIN_QUESTIONS = 50
# Contract: ~70% factual, ~20% multi_hop, ~10% unanswerable. Accepted bands:
TYPE_BANDS = {"factual": (0.60, 0.80), "multi_hop": (0.15, 0.25), "unanswerable": (0.05, 0.15)}
MIN_EVIDENCE = {"factual": 1, "multi_hop": 2, "unanswerable": 0}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_WORD_RE = re.compile(r"\w+")


def load_golden(path: Path = DEFAULT_GOLDEN) -> list[dict[str, Any]]:
    items = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{n}: JSON inválido: {exc}") from exc
    return items


def validate_schema(item: Any, known_documents: set[str] | None = None) -> list[str]:
    """Return schema errors for one golden-set item (empty list = valid)."""
    if not isinstance(item, dict):
        return ["item não é um objeto JSON"]
    errs: list[str] = []
    missing = REQUIRED_KEYS - item.keys()
    extra = item.keys() - REQUIRED_KEYS
    if missing:
        errs.append(f"campos ausentes: {sorted(missing)}")
    if extra:
        errs.append(f"campos não previstos no contrato: {sorted(extra)}")
    if missing:
        return errs
    if not isinstance(item["id"], str) or not _ID_RE.match(item["id"]):
        errs.append("id deve ser string [a-z0-9_-]")
    if not isinstance(item["question"], str) or len(item["question"].strip()) < 10:
        errs.append("question vazia ou curta demais")
    if item["type"] not in TYPES:
        errs.append(f"type inválido: {item['type']!r}")
    if not isinstance(item["reference_answer"], str) or not item["reference_answer"].strip():
        errs.append("reference_answer vazia")
    if not isinstance(item["reviewed"], bool):
        errs.append("reviewed deve ser booleano")
    evidence = item["evidence"]
    if not isinstance(evidence, list):
        return [*errs, "evidence deve ser lista"]
    for i, ev in enumerate(evidence):
        if not isinstance(ev, dict) or set(ev.keys()) != EVIDENCE_KEYS:
            errs.append(f"evidence[{i}] deve ter exatamente {sorted(EVIDENCE_KEYS)}")
            continue
        quote = ev["quote"]
        if not isinstance(quote, str) or not QUOTE_MIN <= len(quote.strip()) <= QUOTE_MAX:
            size = len(quote) if isinstance(quote, str) else "?"
            errs.append(
                f"evidence[{i}].quote com {size} caracteres (esperado {QUOTE_MIN}-{QUOTE_MAX})"
            )
        if not isinstance(ev["locator"], str) or not ev["locator"].strip():
            errs.append(f"evidence[{i}].locator vazio")
        if known_documents is not None and ev["document"] not in known_documents:
            errs.append(f"evidence[{i}].document desconhecido: {ev['document']!r}")
    qtype = item["type"]
    if qtype in MIN_EVIDENCE and len(evidence) < MIN_EVIDENCE[qtype]:
        errs.append(f"{qtype} exige ao menos {MIN_EVIDENCE[qtype]} evidência(s)")
    return errs


def find_missing_quotes(item: dict[str, Any], corpus: dict[str, str]) -> list[str]:
    """Return the quotes of ``item`` that are not literally present in their document."""
    normalized = {doc: normalize(text) for doc, text in corpus.items()}
    missing = []
    for ev in item.get("evidence", []):
        doc_text = normalized.get(ev.get("document", ""))
        if doc_text is None or normalize(ev.get("quote", "")) not in doc_text:
            missing.append(ev.get("quote", ""))
    return missing


def ambiguous_quotes(item: dict[str, Any], corpus: dict[str, str]) -> list[str]:
    """Quotes that occur more than once in the corpus (weak relevance signal)."""
    normalized = [normalize(t) for t in corpus.values()]
    out = []
    for ev in item.get("evidence", []):
        nq = normalize(ev.get("quote", ""))
        if nq and sum(t.count(nq) for t in normalized) > 1:
            out.append(ev.get("quote", ""))
    return out


def type_distribution(items: list[dict[str, Any]]) -> dict[str, float]:
    counts = Counter(i.get("type") for i in items)
    total = len(items) or 1
    return {t: counts.get(t, 0) / total for t in TYPES}


def copied_ngrams(question: str, quotes: list[str], n: int = 8) -> bool:
    """True if the question reuses ``n`` consecutive words of an evidence quote."""
    qwords = _WORD_RE.findall(normalize(question))
    qgrams = {tuple(qwords[i : i + n]) for i in range(len(qwords) - n + 1)}
    for quote in quotes:
        w = _WORD_RE.findall(normalize(quote))
        if any(tuple(w[i : i + n]) in qgrams for i in range(len(w) - n + 1)):
            return True
    return False
