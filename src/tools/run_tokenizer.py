#!/usr/bin/env python3
"""Tokenize compiled chunk XML files via the NLP server.

For each chunk XML file under PROTO_DIR, this script sends the chunk's
primary text to the NLP server's /tokenize endpoint and writes a
companion .tokens.json.zst sidecar alongside the chunk XML: one file per
chunk, individually zstd-compressed (not a single archive), so the sidecar
tree can be pulled and consumed without ever materializing the full
uncompressed set on disk — tokens.json is ~50x the size of its source
chunk XML uncompressed (mostly null morphological fields), but compresses
~30x with zstd, so per-file compression keeps both the packaged artifact
and the read path cheap.

Usage:
    python src/tools/run_tokenizer.py --proto-dir ./proto-pages --nlp-url http://localhost:8001

Re-running is safe: chunks whose .tokens.json.zst already exists are
skipped unless --force is given.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import zstandard

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from kodon_py.tei_parser import TEIParser, TEIParserError
from lxml import etree

from mvp.site_map import token_sidecar_name

_ZSTD_LEVEL = 19


def _is_punct(text: str) -> bool:
    return bool(text) and all(unicodedata.category(c)[0] in ("P", "S") for c in text)


def _post_json(url: str, payload: dict, timeout: float = 30.0) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _primary_text(chunk_file: Path) -> tuple[str, str]:
    """Return (cts_urn, primary_text) for a compiled chunk XML file."""
    root = etree.parse(chunk_file).getroot()
    cts_urn = root.get("cts_urn", "")
    base_urn = root.get("base_urn", "") or cts_urn.rsplit(":", 1)[0]
    chunk_unit = root.get("unit", "")

    content_el = root.find("elements")
    if content_el is None:
        raise TEIParserError(f"No <elements> in {chunk_file}")

    parser = TEIParser(content_el, base_urn, chunk_unit)
    return cts_urn, parser.primary_text


def _tokenize(nlp_url: str, chunk_urn: str, primary_text: str) -> list[dict]:
    if not primary_text.strip():
        return []
    data = _post_json(
        f"{nlp_url}/tokenize",
        {"content": primary_text, "extra": {"urn": chunk_urn}},
    )
    tokens = []
    for token in data.get("tokens", []):
        text = token["text"].strip()
        urn = None if _is_punct(text) else f"{chunk_urn}@{token['identifier']}"
        tokens.append({**token, "urn": urn, "text": text})
    return tokens


def _iter_chunk_files(proto_dir: Path):
    for index_file in sorted(proto_dir.glob("**/index.json")):
        version_dir = index_file.parent
        with open(index_file) as f:
            chunks = json.load(f).get("chunks", [])
        for entry in chunks:
            chunk_file = version_dir / entry["file"]
            if chunk_file.exists():
                yield chunk_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Tokenize compiled chunk XML files")
    parser.add_argument(
        "--proto-dir",
        required=True,
        type=Path,
        help="Root directory of compiled chunk XML files (output of Chunker)",
    )
    parser.add_argument(
        "--nlp-url",
        required=True,
        help="Base URL of the NLP server (e.g. http://localhost:8001)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-tokenize even if .tokens.json.zst already exists",
    )
    args = parser.parse_args()

    nlp_url = args.nlp_url.rstrip("/")
    generated = skipped = failed = 0
    compressor = zstandard.ZstdCompressor(level=_ZSTD_LEVEL)

    for chunk_file in _iter_chunk_files(args.proto_dir):
        sidecar = chunk_file.parent / token_sidecar_name(chunk_file)
        if sidecar.exists() and not args.force:
            skipped += 1
            continue
        try:
            cts_urn, primary_text = _primary_text(chunk_file)
            tokens = _tokenize(nlp_url, cts_urn, primary_text)
            payload = json.dumps(
                {"urn": cts_urn, "tokens": tokens}, ensure_ascii=False
            ).encode("utf-8")
            sidecar.write_bytes(compressor.compress(payload))
            generated += 1
        except urllib.error.URLError as exc:
            print(f"  ERROR (NLP server): {chunk_file.name}: {exc}", file=sys.stderr)
            sys.exit(1)
        except (TEIParserError, Exception) as exc:
            print(f"  FAILED: {chunk_file.name}: {exc}", file=sys.stderr)
            failed += 1

    print(f"Tokens: {generated} generated, {skipped} skipped, {failed} failed.")


if __name__ == "__main__":
    main()
