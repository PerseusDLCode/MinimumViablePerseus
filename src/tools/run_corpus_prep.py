#!/usr/bin/env python3
"""run_corpus_prep.py — Apply a corpus-preparation XSLT to a Perseus corpus.

Iterates over all TEI files in CORPUS_DIR (skipping __cts__.xml metadata
files), applies STYLESHEET to each, and writes the results to OUTPUT_DIR,
preserving the source directory structure.

The CTS namespace (greekLit, latinLit, …) is detected automatically from
CORPUS_DIR's path and passed to the stylesheet as the $cts-namespace
parameter.  Override with --cts-namespace if needed.

Usage:
    python src/tools/run_corpus_prep.py CORPUS_DIR OUTPUT_DIR STYLESHEET

Examples:
    python src/tools/run_corpus_prep.py \\
        ../canonicalLit/canonical-greekLit/data \\
        /tmp/prepared/greekLit \\
        src/xslt/corpus-prep/transform1.xsl

    python src/tools/run_corpus_prep.py \\
        ../canonicalLit/canonical-latinLit/data \\
        /tmp/prepared/latinLit \\
        src/xslt/corpus-prep/transform1.xsl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from saxonche import PySaxonProcessor


def _detect_cts_namespace(corpus_dir: Path) -> str:
    for part in corpus_dir.parts:
        if "latinLit" in part:
            return "latinLit"
        if "greekLit" in part:
            return "greekLit"
    return "greekLit"


def _iter_tei_files(corpus_dir: Path):
    for path in sorted(corpus_dir.rglob("*.xml")):
        if path.name != "__cts__.xml":
            yield path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a corpus-preparation XSLT to a Perseus corpus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("corpus_dir", type=Path, metavar="CORPUS_DIR",
                        help="Root of a canonical-*Lit data/ directory.")
    parser.add_argument("output_dir", type=Path, metavar="OUTPUT_DIR",
                        help="Output root; directory structure is preserved.")
    parser.add_argument("stylesheet", type=Path, metavar="STYLESHEET",
                        help="Path to the corpus-prep XSLT stylesheet.")
    parser.add_argument("--cts-namespace", metavar="NS",
                        help="Override the CTS namespace (default: auto-detect).")
    args = parser.parse_args()

    corpus_dir = args.corpus_dir.resolve()
    output_dir = args.output_dir.resolve()
    stylesheet  = args.stylesheet.resolve()
    cts_namespace = args.cts_namespace or _detect_cts_namespace(corpus_dir)

    for path, label in ((corpus_dir, "Corpus"), (stylesheet, "Stylesheet")):
        if not path.exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            sys.exit(1)

    files = list(_iter_tei_files(corpus_dir))
    print(f"Corpus:        {corpus_dir}")
    print(f"Output:        {output_dir}")
    print(f"Stylesheet:    {stylesheet.name}")
    print(f"CTS namespace: {cts_namespace}")
    print(f"Files:         {len(files)}")
    print()

    ok = failed = 0

    with PySaxonProcessor(license=False) as proc:
        xslt = proc.new_xslt30_processor()
        transformer = xslt.compile_stylesheet(stylesheet_file=str(stylesheet))
        if xslt.error_message:
            print(f"ERROR: stylesheet compilation failed:\n{xslt.error_message}",
                  file=sys.stderr)
            sys.exit(1)

        transformer.set_parameter("cts-namespace",
                                  proc.make_string_value(cts_namespace))

        for tei_file in files:
            rel = tei_file.relative_to(corpus_dir)
            out_file = output_dir / rel
            out_file.parent.mkdir(parents=True, exist_ok=True)

            try:
                result = transformer.transform_to_string(
                    source_file=str(tei_file)
                )
                if xslt.error_message:
                    raise RuntimeError(xslt.error_message)
                out_file.write_text(result, encoding="utf-8")
                print(f"  ok      {rel}")
                ok += 1
            except Exception as exc:
                print(f"  FAILED  {rel}: {exc}")
                failed += 1

    print(f"\nDone: {ok} ok, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
