"""Text normalization shared by the golden-set validator and the relevance judgement."""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Normalize text for literal-quote matching.

    Contract rule: lowercase + collapsed whitespace. We additionally apply Unicode NFKC so that
    visually identical characters (non-breaking spaces, ordinal indicators, ligatures) compare
    equal regardless of how the ingestion pipeline extracted the text. NFKC is applied to both
    sides, so it never makes a quote match text that differs in content.
    """
    text = unicodedata.normalize("NFKC", text)
    return _WS.sub(" ", text.lower()).strip()


def contains_quote(chunk_text: str, quote: str) -> bool:
    """True when the normalized ``quote`` is a substring of the normalized ``chunk_text``."""
    nq = normalize(quote)
    return bool(nq) and nq in normalize(chunk_text)
