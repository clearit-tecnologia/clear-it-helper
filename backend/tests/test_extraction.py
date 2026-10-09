from __future__ import annotations

import pytest

from clear_helper.extraction import (
    NO_TEXT_PDF_MESSAGE,
    DocumentFormat,
    ExtractionError,
    detect_format,
    extract,
)
from tests.documents_factory import make_docx, make_pdf


def test_pdf_text_is_extracted_per_real_page() -> None:
    data = make_pdf(["Primeira pagina", None, "Terceira pagina"])

    result = extract(data, DocumentFormat.PDF)

    assert result.page_count == 3
    assert [(p.page, p.text) for p in result.pages] == [
        (1, "Primeira pagina"),
        (3, "Terceira pagina"),
    ]


def test_pdf_without_text_fails_with_ocr_message() -> None:
    with pytest.raises(ExtractionError) as exc_info:
        extract(make_pdf([None, None]), DocumentFormat.PDF)
    assert str(exc_info.value) == NO_TEXT_PDF_MESSAGE


def test_corrupted_pdf_fails() -> None:
    with pytest.raises(ExtractionError):
        extract(b"%PDF-1.4\nnot really a pdf", DocumentFormat.PDF)


def test_docx_paragraphs_and_tables_in_order() -> None:
    data = make_docx(["Art. 1º Disposições gerais.", "Art. 2º Definições."], [["A", "B"]])

    result = extract(data, DocumentFormat.DOCX)

    assert result.page_count == 1
    assert result.pages[0].page == 1
    assert result.pages[0].text == "Art. 1º Disposições gerais.\nArt. 2º Definições.\nA | B"


def test_html_keeps_only_visible_text() -> None:
    html = (
        b"<html><head><title>T</title><style>p{color:red}</style></head>"
        b"<body><script>alert(1)</script><h1>Lei</h1><p>Texto vis\xc3\xadvel</p></body></html>"
    )

    text = extract(html, DocumentFormat.HTML).pages[0].text

    assert "Lei" in text
    assert "Texto visível" in text
    assert "alert" not in text
    assert "color" not in text


@pytest.mark.parametrize(
    "data",
    ["Ação e decisão".encode(), "Ação e decisão".encode("cp1252"), "\ufeffAção e decisão".encode()],
)
def test_text_decoding_handles_common_encodings(data: bytes) -> None:
    assert extract(data, DocumentFormat.TXT).pages[0].text == "Ação e decisão"


def test_text_is_normalized() -> None:
    text = extract(b"a  \r\n\r\n\r\n\r\nb\x00", DocumentFormat.MARKDOWN).pages[0].text
    assert text == "a\n\nb"


def test_empty_text_document_fails() -> None:
    with pytest.raises(ExtractionError):
        extract(b"   \n ", DocumentFormat.TXT)


@pytest.mark.parametrize(
    ("filename", "content_type", "head", "expected"),
    [
        ("lei.pdf", "application/octet-stream", b"%PDF-1.7", DocumentFormat.PDF),
        ("lei.PDF", None, b"%PDF-1.7", DocumentFormat.PDF),
        ("doc.docx", None, b"PK\x03\x04", DocumentFormat.DOCX),
        ("notas.md", None, b"# titulo", DocumentFormat.MARKDOWN),
        ("pagina.htm", None, b"<html>", DocumentFormat.HTML),
        ("sem-extensao", "text/plain; charset=utf-8", b"abc", DocumentFormat.TXT),
        ("C:\\Users\\x\\lei.txt", None, b"abc", DocumentFormat.TXT),
    ],
)
def test_detect_format_supported(
    filename: str, content_type: str | None, head: bytes, expected: DocumentFormat
) -> None:
    assert detect_format(filename, content_type, head) is expected


@pytest.mark.parametrize(
    ("filename", "content_type", "head"),
    [
        ("planilha.xlsx", None, b"PK\x03\x04"),
        ("imagem.png", "image/png", b"\x89PNG"),
        ("falso.pdf", "application/pdf", b"MZ\x90\x00"),  # wrong magic bytes
        ("falso.docx", None, b"%PDF-1.4"),
        ("binario.txt", None, b"\x00\x01\x02\x00"),
        ("sem-extensao", None, b"abc"),
    ],
)
def test_detect_format_unsupported(filename: str, content_type: str | None, head: bytes) -> None:
    assert detect_format(filename, content_type, head) is None
