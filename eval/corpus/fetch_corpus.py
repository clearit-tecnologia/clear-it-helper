"""Download the golden-set corpus (official law texts) and convert it to clean UTF-8 TXT.

Downloads are treated as untrusted data: HTTPS only, host allow-list (*.gov.br / *.leg.br),
size limit, saved under corpus/files/raw/ without execute permission, parsed only with the
standard-library HTML parser. Nothing downloaded is executed.

Usage (from eval/):
    uv run python corpus/fetch_corpus.py                 # download + convert + check sha256
    uv run python corpus/fetch_corpus.py --offline       # re-convert existing raw files
    uv run python corpus/fetch_corpus.py --update-lock   # write sha256/retrieved_at to sources.yaml
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from ch_eval.corpus import FILES_DIR, SOURCES_FILE, Source, load_sources
from ch_eval.htmltext import decode_html, html_to_text

ALLOWED_HOST_SUFFIXES = (".gov.br", ".leg.br")
MAX_BYTES = 20 * 1024 * 1024
# The Planalto WAF drops connections from non-browser User-Agents.
USER_AGENT = "Mozilla/5.0 (compatible; clear-helper-eval/0.1)"
RETRIES = 3


def _check_url(url: str) -> None:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host.endswith(ALLOWED_HOST_SUFFIXES):
        raise ValueError(f"URL fora da allow-list (https + *.gov.br/*.leg.br): {url}")


def download(url: str) -> tuple[bytes, dict[str, str]]:
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            return _download_once(url)
        except httpx.TransportError as exc:
            last = exc
            print(f"  tentativa {attempt}/{RETRIES} falhou: {exc}", file=sys.stderr)
            time.sleep(2 * attempt)
    raise RuntimeError(f"falha ao baixar {url}") from last


def _download_once(url: str) -> tuple[bytes, dict[str, str]]:
    _check_url(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"}
    client = httpx.Client(follow_redirects=True, timeout=60.0, headers=headers)
    with client, client.stream("GET", url) as resp:
        resp.raise_for_status()
        _check_url(str(resp.url))  # redirects must stay inside the allow-list
        buf = bytearray()
        for chunk in resp.iter_bytes():
            buf.extend(chunk)
            if len(buf) > MAX_BYTES:
                raise ValueError(f"download maior que {MAX_BYTES} bytes: {url}")
        meta = {
            "final_url": str(resp.url),
            "content_type": resp.headers.get("content-type", ""),
            "last_modified": resp.headers.get("last-modified", ""),
        }
    return bytes(buf), meta


def convert(src: Source, raw: bytes) -> str:
    if src.source_format != "html":
        raise ValueError(f"formato de origem não suportado: {src.source_format}")
    text = html_to_text(decode_html(raw), drop_struck=True, start_pattern=r"^LEI N")
    header = f"{src.norma} - {src.title}\nTexto compilado vigente. Fonte oficial: {src.url}\n"
    return header + text


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o644)
    tmp.replace(path)


def update_lock(sources_path: Path, updates: dict[str, dict[str, str]]) -> None:
    """Rewrite sha256/retrieved_at in place, preserving comments and layout."""
    lines = sources_path.read_text(encoding="utf-8").splitlines(keepends=True)
    current = None
    for i, line in enumerate(lines):
        m = re.match(r"^\s*-\s+id:\s*(\S+)", line)
        if m:
            current = m.group(1)
            continue
        if current in updates:
            for key, value in updates[current].items():
                km = re.match(rf"^(\s+){key}:", line)
                if km:
                    lines[i] = f'{km.group(1)}{key}: "{value}"\n'
    sources_path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--sources", type=Path, default=SOURCES_FILE)
    ap.add_argument("--out", type=Path, default=FILES_DIR)
    ap.add_argument("--offline", action="store_true", help="não baixa; reconverte files/raw/")
    ap.add_argument(
        "--update-lock", action="store_true", help="grava sha256 e retrieved_at no sources.yaml"
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="falha se o sha256 do texto convertido divergir do sources.yaml",
    )
    args = ap.parse_args()

    sources = load_sources(args.sources)
    raw_dir = args.out / "raw"
    manifest_path = args.out / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.is_file() else {}
    today = dt.date.today().isoformat()
    updates: dict[str, dict[str, str]] = {}
    mismatches = 0

    for src in sources:
        raw_path = raw_dir / f"{src.id}.{src.source_format}"
        if args.offline:
            raw = raw_path.read_bytes()
            meta = manifest.get(src.id, {}).get("download", {})
        else:
            print(f"[{src.id}] baixando {src.url}")
            raw, meta = download(src.url)
            _write(raw_path, raw)
            meta["retrieved_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        text = convert(src, raw)
        data = text.encode("utf-8")
        out_path = args.out / src.output_file
        _write(out_path, data)
        sha = hashlib.sha256(data).hexdigest()
        manifest[src.id] = {
            "url": src.url,
            "raw_file": str(raw_path.relative_to(args.out)),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_bytes": len(raw),
            "output_file": src.output_file,
            "sha256": sha,
            "chars": len(text),
            "lines": text.count("\n"),
            "download": meta,
        }
        status = "ok"
        if src.sha256 and src.sha256 != sha:
            status = "DIVERGENTE do sources.yaml (texto mudou na fonte? revalide o golden set)"
            mismatches += 1
        elif not src.sha256:
            status = "sem trava no sources.yaml (use --update-lock)"
        print(f"[{src.id}] {out_path.name}: {len(text)} chars, sha256={sha[:16]}... {status}")
        updates[src.id] = {
            "sha256": sha,
            "retrieved_at": today if not args.offline else (src.raw.get("retrieved_at") or today),
        }

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    if args.update_lock:
        update_lock(args.sources, updates)
        print(f"sources.yaml atualizado ({len(updates)} fontes)")
    if mismatches and args.strict:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
