#!/usr/bin/env python3
"""run_index.py — Build chunk and word indexes from Perseus TEI files.

Iterates over one or more TEI files (or all TEI files under CORPUS_DIR),
runs ChunkIndexer and WordIndexer on each, and writes the results to
OUTPUT_DIR as:

    OUTPUT_DIR/<namespace>/<textgroup>/<work>/<version>/chunks.json
    OUTPUT_DIR/<namespace>/<textgroup>/<work>/<version>/words.jsonl

The output paths are determined by the CTS URN found in the document header.
Documents that cannot be parsed or that lack a usable CTS URN are skipped
with an error message.

Usage:
    python src/tools/run_index.py CORPUS_DIR OUTPUT_DIR
    python src/tools/run_index.py path/to/file.xml OUTPUT_DIR

Examples:
    python src/tools/run_index.py \\
        ../canonicalLit/canonical-greekLit/data \\
        /tmp/indexes/greekLit
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from mvp.corpus.document import TEIDocument
from mvp.corpus.index_serializers import ChunkIndexSerializer, WordIndexSerializer
from mvp.corpus.indexers import ChunkIndexer, WordIndexer
from mvp.compilers.site_map import SiteMap


def _iter_tei_files(source: Path):
    if source.is_file():
        yield source
    else:
        for path in sorted(source.rglob("*.xml")):
            if path.name != "__cts__.xml":
                yield path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build chunk and word indexes from Perseus TEI files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("source", type=Path, metavar="SOURCE",
                        help="A TEI file or corpus root directory.")
    parser.add_argument("output_dir", type=Path, metavar="OUTPUT_DIR",
                        help="Root directory for index output files.")
    args = parser.parse_args()

    source = args.source.resolve()
    output_dir = args.output_dir.resolve()

    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        sys.exit(1)

    site_map = SiteMap(output_dir)
    files = list(_iter_tei_files(source))

    print(f"Source:  {source}")
    print(f"Output:  {output_dir}")
    print(f"Files:   {len(files)}")
    print()

    ok = failed = 0

    for tei_file in files:
        rel = tei_file.relative_to(source) if source.is_dir() else tei_file.name
        try:
            doc = TEIDocument(tei_file)
            meta = doc.metadata

            if not meta.urn:
                print(f"  SKIP    {rel}: no usable CTS URN")
                failed += 1
                continue

            chunk_index = ChunkIndexer(tei_file).chunk_index
            word_index = WordIndexer(tei_file).word_index

            ChunkIndexSerializer(chunk_index, meta).write(
                site_map.chunk_index_path(meta.urn)
            )
            WordIndexSerializer(word_index, meta).write(
                site_map.word_index_path(meta.urn)
            )
            print(f"  ok      {rel}  ({len(chunk_index.entries)} chunks, "
                  f"{sum(len(v) for v in word_index.entries.values())} word occurrences)")
            ok += 1
        except Exception as exc:
            print(f"  FAILED  {rel}: {exc}")
            failed += 1

    print(f"\nDone: {ok} ok, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
