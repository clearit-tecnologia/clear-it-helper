"""Baseline fixed-size chunking (pipeline ``baseline-v1``).

Chunks have ``size`` characters with ``overlap`` characters shared with the previous one
and never cross a page boundary. ``char_start``/``char_end`` are offsets into the page
text (end exclusive), so ``page_text[char_start:char_end] == chunk.text``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from clear_helper.extraction import PageText


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_index: int
    page: int
    text: str
    char_start: int
    char_end: int


def _windows(length: int, size: int, overlap: int) -> Iterable[tuple[int, int]]:
    step = size - overlap
    start = 0
    while start < length:
        end = min(start + size, length)
        yield start, end
        if end == length:
            return
        start += step


def chunk_pages(pages: Iterable[PageText], *, size: int, overlap: int) -> list[Chunk]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("chunk overlap must be >= 0 and smaller than the chunk size")

    chunks: list[Chunk] = []
    for page in pages:
        for start, end in _windows(len(page.text), size, overlap):
            raw = page.text[start:end]
            stripped = raw.strip()
            if not stripped:
                continue
            leading = len(raw) - len(raw.lstrip())
            char_start = start + leading
            chunks.append(
                Chunk(
                    chunk_index=len(chunks),
                    page=page.page,
                    text=stripped,
                    char_start=char_start,
                    char_end=char_start + len(stripped),
                )
            )
    return chunks
