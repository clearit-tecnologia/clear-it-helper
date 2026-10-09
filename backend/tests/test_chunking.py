from __future__ import annotations

import pytest

from clear_helper.chunking import chunk_pages
from clear_helper.extraction import PageText


def test_short_page_yields_single_chunk() -> None:
    chunks = chunk_pages([PageText(1, "abc")], size=10, overlap=2)

    assert len(chunks) == 1
    assert chunks[0].text == "abc"
    assert (chunks[0].char_start, chunks[0].char_end, chunks[0].page) == (0, 3, 1)


def test_exact_size_does_not_create_overlap_only_tail() -> None:
    chunks = chunk_pages([PageText(1, "x" * 10)], size=10, overlap=3)
    assert [(c.char_start, c.char_end) for c in chunks] == [(0, 10)]


def test_windows_overlap_and_cover_the_whole_page() -> None:
    text = "".join(chr(ord("a") + i % 26) for i in range(25))

    chunks = chunk_pages([PageText(1, text)], size=10, overlap=3)

    assert [(c.char_start, c.char_end) for c in chunks] == [(0, 10), (7, 17), (14, 24), (21, 25)]
    for chunk in chunks:
        assert text[chunk.char_start : chunk.char_end] == chunk.text
    # Consecutive chunks share exactly ``overlap`` characters.
    assert chunks[0].text[-3:] == chunks[1].text[:3]
    assert chunks[-1].char_end == len(text)


def test_chunks_never_cross_pages_and_index_is_global() -> None:
    pages = [PageText(1, "a" * 15), PageText(3, "b" * 5)]

    chunks = chunk_pages(pages, size=10, overlap=2)

    assert [(c.chunk_index, c.page, c.text) for c in chunks] == [
        (0, 1, "a" * 10),
        (1, 1, "a" * 7),
        (2, 3, "b" * 5),
    ]


def test_whitespace_is_trimmed_and_offsets_follow_the_text() -> None:
    text = "  hello   " + " " * 10 + "world"

    chunks = chunk_pages([PageText(1, text)], size=10, overlap=0)

    assert [c.text for c in chunks] == ["hello", "world"]
    for chunk in chunks:
        assert text[chunk.char_start : chunk.char_end] == chunk.text


def test_empty_pages_produce_no_chunks() -> None:
    assert chunk_pages([PageText(1, ""), PageText(2, "   ")], size=10, overlap=2) == []


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (10, 10), (10, -1)])
def test_invalid_parameters_are_rejected(size: int, overlap: int) -> None:
    with pytest.raises(ValueError, match="chunk"):
        chunk_pages([PageText(1, "abc")], size=size, overlap=overlap)
