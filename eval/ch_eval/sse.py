"""Minimal Server-Sent Events parser for the /chat stream (text/event-stream, JSON in data:)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

# Answers that mean "not found in the documents" (the API's fixed text and model paraphrases).
REFUSAL_PATTERNS = re.compile(
    r"n[aã]o encontrei|n[aã]o (h[aá]|consta|existe)m? (essa |esta |tal )?informa[cç]|"
    r"n[aã]o (est[aá]|constam?) (presente|dispon[ií]ve)|"
    r"os (documentos|trechos)( fornecidos| enviados)? n[aã]o "
    r"(cont[eê]m|trazem|mencionam|informam|abordam|tratam)|"
    r"n[aã]o (foi poss[ií]vel|consegui) (encontrar|localizar|identificar)",
    re.IGNORECASE,
)
CITATION = re.compile(r"\[\d+\]")


@dataclass
class SSEEvent:
    event: str
    data: str


def iter_sse(lines: Iterable[str]) -> Iterator[SSEEvent]:
    """Parse SSE lines (without trailing newlines) into events.

    Follows the WHATWG rules used by the API: ``event:`` sets the type, multiple ``data:`` lines
    are joined with ``\\n``, a single space after the colon is removed, ``:`` lines are comments,
    a blank line dispatches. A trailing event without the final blank line is also dispatched.
    """
    event, data = "", []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line == "":
            if data:
                yield SSEEvent(event or "message", "\n".join(data))
            event, data = "", []
            continue
        if line.startswith(":"):
            continue
        name, sep, value = line.partition(":")
        if not sep:
            value = ""
        elif value.startswith(" "):
            value = value[1:]
        if name == "event":
            event = value
        elif name == "data":
            data.append(value)
        # "id" and "retry" are irrelevant for the evaluation
    if data:
        yield SSEEvent(event or "message", "\n".join(data))


@dataclass
class ChatResult:
    sources: list[dict[str, Any]] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    done: dict[str, Any] | None = None
    error: str | None = None

    @property
    def answer(self) -> str:
        if self.done and isinstance(self.done.get("answer"), str):
            return self.done["answer"]
        return "".join(self.tokens)

    @property
    def refused_flag(self) -> bool:
        return bool(self.done and self.done.get("refused"))

    @property
    def refused(self) -> bool:
        """API flag (no context above the score threshold) or a refusal written by the LLM."""
        return self.refused_flag or bool(REFUSAL_PATTERNS.search(self.answer))

    @property
    def has_citation(self) -> bool:
        return bool(CITATION.search(self.answer))


def collect_chat(events: Iterable[SSEEvent]) -> ChatResult:
    """Fold the /chat event stream into a ChatResult (unknown events are ignored)."""
    res = ChatResult()
    for ev in events:
        try:
            payload = json.loads(ev.data) if ev.data else {}
        except json.JSONDecodeError:
            if ev.event == "error":
                res.error = ev.data
            continue
        if ev.event == "sources":
            res.sources = list(payload.get("sources") or [])
        elif ev.event == "token":
            res.tokens.append(str(payload.get("text", "")))
        elif ev.event == "done":
            res.done = payload
        elif ev.event == "error":
            res.error = str(payload.get("detail", payload))
    return res
