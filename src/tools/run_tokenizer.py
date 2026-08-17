#!/usr/bin/env python3
"""Tokenize compiled chunk XML files via the NLP server.

For each chunk XML file under PROTO_DIR, this script sends the chunk's
primary text to the NLP server's /tokenize endpoint and writes a
companion .tokens.json.zst sidecar: one file per chunk, individually
zstd-compressed (not a single archive), so the sidecar tree can be pulled
and consumed without ever materializing the full uncompressed set on disk
— tokens.json is ~50x the size of its source chunk XML uncompressed
(mostly null morphological fields), but compresses ~30x with zstd, so
per-file compression keeps both the packaged artifact and the read path
cheap.

By default, each sidecar is written into --tokens-dir (falling back to
mvp.site.config.TOKENS_DIR, i.e. the MVP_TOKENS_DIR env var) at the same
relative path the chunk occupies under --proto-dir, mirroring PROTO_DIR's
corpus/textgroup/work/version layout — the tree checked into this repo
under tokenized-pages/ and baked into Dockerfile.corpus, and the same
layout mvp.site.chunks._load_token_sidecar reads from at render time. If
neither is set, sidecars are written alongside the chunk XML instead (the
old co-located layout, still supported for ad hoc local use).

Usage:
    python src/tools/run_tokenizer.py --proto-dir ./proto-pages --tokens-dir ./tokenized-pages --nlp-url http://localhost:8001 --workers 2

Chunks are tokenized concurrently across --workers threads (default 2) --
each request is an independent network round-trip to the NLP server, so
threading (rather than multiprocessing) is enough to overlap them despite
the GIL. Re-running is safe: chunks whose .tokens.json.zst already exists
are skipped unless --force is given.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import zstandard

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from kodon_py.tei_parser import TEIParser, TEIParserError
from lxml import etree

from mvp.site import config
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


class _AbortTokenization(Exception):
    """Raised to stop the whole run when the NLP server itself is unreachable.

    Distinguished from a single chunk failing to parse/tokenize (recorded as
    a per-chunk failure and skipped) -- an unreachable server means every
    remaining request would fail too, so the run should stop instead of
    burning through the rest of the queue one URLError at a time.
    """


def _process_chunk(
    chunk_file: Path, proto_dir: Path, tokens_dir: Path | None, nlp_url: str, force: bool
) -> str:
    """Tokenize one chunk and write its sidecar. Returns "generated", "skipped", or "failed".

    A fresh ZstdCompressor is used per call rather than one shared across
    calls: ZstdCompressor instances aren't safe for concurrent use from
    multiple threads (see _process_chunk's callers, which run this via a
    thread pool), and compressor construction is cheap relative to a
    network round-trip to the NLP server.
    """
    if tokens_dir is not None:
        rel_dir = chunk_file.parent.resolve().relative_to(proto_dir)
        sidecar_dir = tokens_dir / rel_dir
        sidecar_dir.mkdir(parents=True, exist_ok=True)
    else:
        sidecar_dir = chunk_file.parent
    sidecar = sidecar_dir / token_sidecar_name(chunk_file)
    if sidecar.exists() and not force:
        return "skipped"

    try:
        cts_urn, primary_text = _primary_text(chunk_file)
        tokens = _tokenize(nlp_url, cts_urn, primary_text)
    except urllib.error.URLError as exc:
        raise _AbortTokenization(f"NLP server unreachable: {exc}") from exc
    except (TEIParserError, Exception) as exc:
        print(f"  FAILED: {chunk_file.name}: {exc}", file=sys.stderr)
        return "failed"

    payload = json.dumps({"urn": cts_urn, "tokens": tokens}, ensure_ascii=False).encode(
        "utf-8"
    )
    compressor = zstandard.ZstdCompressor(level=_ZSTD_LEVEL)
    sidecar.write_bytes(compressor.compress(payload))
    return "generated"


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
        "--tokens-dir",
        type=Path,
        default=config.TOKENS_DIR,
        help=(
            "Root directory to write sidecars into, mirroring --proto-dir's "
            "layout (default: mvp.site.config.TOKENS_DIR / MVP_TOKENS_DIR env "
            "var). If unset, sidecars are written alongside each chunk XML."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of chunks to tokenize concurrently (default: 2)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-tokenize even if .tokens.json.zst already exists",
    )
    args = parser.parse_args()

    nlp_url = args.nlp_url.rstrip("/")
    proto_dir = args.proto_dir.resolve()
    generated = skipped = failed = 0

    chunk_files = list(_iter_chunk_files(args.proto_dir))
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                _process_chunk, chunk_file, proto_dir, args.tokens_dir, nlp_url, args.force
            ): chunk_file
            for chunk_file in chunk_files
        }
        try:
            for future in as_completed(futures):
                result = future.result()
                if result == "generated":
                    generated += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    failed += 1
        except _AbortTokenization as exc:
            executor.shutdown(cancel_futures=True)
            print(f"  ERROR (NLP server): {exc}", file=sys.stderr)
            sys.exit(1)

    print(f"Tokens: {generated} generated, {skipped} skipped, {failed} failed.")


if __name__ == "__main__":
    main()
