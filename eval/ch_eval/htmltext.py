"""Convert Planalto law pages (legacy FrontPage HTML) into clean UTF-8 plain text.

Downloaded pages are untrusted data: this module only parses them with the standard library
HTML parser, never executes or follows anything inside them.

The Planalto "texto compilado" keeps superseded wording visible with strike-through
(``<strike>``, ``<s>``, ``<del>`` or ``style="text-decoration:line-through"``) right before the
current wording. To obtain the *current* (vigente) text we drop every struck-through fragment
and keep the amendment notes such as "(Redação dada pela Lei nº 13.853, de 2019)".
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

SKIP_TAGS = frozenset(
    {
        "head",
        "script",
        "style",
        "noscript",
        "iframe",
        "object",
        "template",
        "svg",
        "form",
        "button",
        "select",
        "textarea",
        "nav",
    }
)
STRIKE_TAGS = frozenset({"strike", "s", "del"})
VOID_TAGS = frozenset(
    {
        "br",
        "img",
        "meta",
        "link",
        "hr",
        "input",
        "area",
        "base",
        "col",
        "embed",
        "param",
        "source",
        "track",
        "wbr",
    }
)
BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "br",
        "tr",
        "li",
        "ul",
        "ol",
        "table",
        "blockquote",
        "center",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "title",
        "body",
        "dt",
        "dd",
        "pre",
        "section",
        "article",
        "header",
        "footer",
    }
)
CELL_TAGS = frozenset({"td", "th"})
_LINE_THROUGH = re.compile(r"text-decoration\s*:\s*[^;\"']*line-through", re.IGNORECASE)


def decode_html(raw: bytes) -> str:
    """Decode a Planalto page. Most pages have no charset and are windows-1252."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # cp1252 leaves 5 bytes undefined; map those through latin-1 instead of failing.
    out = []
    for b in raw:
        try:
            out.append(bytes([b]).decode("cp1252"))
        except UnicodeDecodeError:
            out.append(bytes([b]).decode("latin-1"))
    return "".join(out)


class _Extractor(HTMLParser):
    def __init__(self, drop_struck: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.drop_struck = drop_struck
        self.stack: list[tuple[str, bool, bool]] = []  # (tag, struck, skipped)
        self.parts: list[str] = []

    def _struck(self) -> bool:
        return any(s for _, s, _ in self.stack)

    def _skipped(self) -> bool:
        return any(k for _, _, k in self.stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in CELL_TAGS:
            self.parts.append(" ")
        if tag in VOID_TAGS:
            return
        if tag == "p" and any(t == "p" for t, _, _ in self.stack):
            self._pop_until("p")  # an open <p> is implicitly closed by a new <p>
        style = " ".join(v or "" for k, v in attrs if k.lower() == "style")
        struck = self.drop_struck and (tag in STRIKE_TAGS or bool(_LINE_THROUGH.search(style)))
        self.stack.append((tag, struck, tag in SKIP_TAGS))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in BLOCK_TAGS:
            self.parts.append("\n")

    def _pop_until(self, tag: str) -> None:
        while self.stack:
            t, _, _ = self.stack.pop()
            if t == tag:
                return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in CELL_TAGS:
            self.parts.append(" ")
        if any(t == tag for t, _, _ in self.stack):
            self._pop_until(tag)
        # stray end tags (frequent in this legacy HTML) are ignored

    def handle_data(self, data: str) -> None:
        if self._skipped() or self._struck():
            return
        # Whitespace inside HTML text nodes (including source line breaks) is a single space.
        self.parts.append(re.sub(r"\s+", " ", data))

    def text(self) -> str:
        return "".join(self.parts)


def html_to_text(html: str, *, drop_struck: bool = True, start_pattern: str | None = None) -> str:
    """Return clean text: one paragraph per line, collapsed spaces, no empty lines.

    ``start_pattern`` (regex) drops leading lines (page banner) before the first match.
    """
    parser = _Extractor(drop_struck=drop_struck)
    parser.feed(html)
    parser.close()
    lines = []
    for line in parser.text().replace("\xa0", " ").splitlines():
        line = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
        if line:
            lines.append(line)
    if start_pattern:
        rx = re.compile(start_pattern)
        for i, line in enumerate(lines):
            if rx.search(line):
                lines = lines[i:]
                break
    return "\n".join(lines) + "\n"
