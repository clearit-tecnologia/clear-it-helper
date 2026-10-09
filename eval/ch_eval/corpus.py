"""Corpus manifest (sources.yaml) helpers shared by the fetcher, the validator and run_eval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

EVAL_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = EVAL_ROOT / "corpus"
SOURCES_FILE = CORPUS_DIR / "sources.yaml"
FILES_DIR = CORPUS_DIR / "files"


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    norma: str
    url: str
    source_format: str
    output_file: str
    sha256: str
    raw: dict[str, Any]


def load_sources(path: Path = SOURCES_FILE) -> list[Source]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = []
    for item in data["sources"]:
        out.append(
            Source(
                id=item["id"],
                title=item["title"],
                norma=item["norma"],
                url=item["url"],
                source_format=item["source_format"],
                output_file=item["output_file"],
                sha256=item.get("sha256") or "",
                raw=item,
            )
        )
    return out


def load_corpus_texts(
    files_dir: Path = FILES_DIR, sources_path: Path = SOURCES_FILE
) -> dict[str, str]:
    """Return ``{output_file: text}`` for every converted corpus file (raises if missing)."""
    texts = {}
    for src in load_sources(sources_path):
        p = files_dir / src.output_file
        if not p.is_file():
            raise FileNotFoundError(
                f"{p} não existe. Rode primeiro: uv run python corpus/fetch_corpus.py"
            )
        texts[src.output_file] = p.read_text(encoding="utf-8")
    return texts
