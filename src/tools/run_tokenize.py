#!/usr/bin/env python3
"""Tokenize prepared TEI documents into <tokens> XML files.

Stage 2 of the Perseus6 annotation pipeline.  Runs tokenize.xsl over one or
more TEI documents that have already been processed by run_add_xml_ids.py
(i.e., their citable elements carry stable @xml:id attributes).

Usage:
    python src/tools/run_tokenize.py SOURCE [SOURCE ...] OUTPUT_DIR

    SOURCE may be a single TEI XML file or a directory; directories are
    searched recursively for *.xml files (excluding __cts__.xml).

    Each output file is named <stem>-tokens.xml and written to OUTPUT_DIR.

Examples:
    # Tokenize a single prepared file
    python src/tools/run_tokenize.py \\
        /tmp/prepped/phi2331.phi013.perseus-lat2.xml /tmp/tokens

    # Tokenize a whole directory of prepared files
    python src/tools/run_tokenize.py /tmp/prepped /tmp/tokens

    # Full two-step pipeline on a single test file:
    python src/tools/run_add_xml_ids.py \\
        tests/data/phi2331.phi013.perseus-lat2.xml /tmp/prepped
    python src/tools/run_tokenize.py /tmp/prepped /tmp/tokens
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from saxonche import PySaxonProcessor

_DEFAULT_XSLT = Path(__file__).parent.parent / "xslt" / "tokenize.xsl"


def _iter_tei_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    return sorted(
        p for p in source.rglob("*.xml")
        if p.name != "__cts__.xml"
    )


def run(sources: list[Path], output_dir: Path, xslt_path: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    for source in sources:
        files.extend(_iter_tei_files(source))

    if not files:
        print("No TEI files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Tokenizing {len(files)} file(s) → {output_dir}")

    with PySaxonProcessor(license=False) as proc:
        xslt_proc = proc.new_xslt30_processor()
        transformer = xslt_proc.compile_stylesheet(stylesheet_file=str(xslt_path))

        ok = 0
        errors = 0
        for path in files:
            out_path = output_dir / f"{path.stem}-tokens.xml"
            try:
                transformer.transform_to_file(
                    source_file=str(path),
                    output_file=str(out_path),
                )
                ok += 1
            except Exception as exc:
                print(f"  ERROR {path.name}: {exc}", file=sys.stderr)
                errors += 1

    print(f"Done: {ok} succeeded, {errors} failed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tokenize prepared TEI documents into <tokens> XML files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        metavar="PATH",
        help="SOURCE [SOURCE ...] OUTPUT_DIR",
    )
    parser.add_argument(
        "--xslt",
        type=Path,
        default=_DEFAULT_XSLT,
        help=f"Path to tokenize.xsl (default: {_DEFAULT_XSLT})",
    )
    args = parser.parse_args()

    if len(args.paths) < 2:
        parser.error("Requires at least one SOURCE and an OUTPUT_DIR")

    *sources, output_dir = args.paths
    run([Path(s) for s in sources], Path(output_dir), args.xslt)


if __name__ == "__main__":
    main()
