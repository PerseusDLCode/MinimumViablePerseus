#!/usr/bin/env python3
"""
run_audit.py — Run StructureAuditor and ReferenceAuditor over a Perseus corpus.

Usage:
  run-audit FILE [FILE ...]  [--output-dir DIR]
  run-audit CORPUS_DIR       [--output-dir DIR]

When given a directory, traverses the Perseus corpus layout:
  data/textgroup/work/edition/*.xml

Skips __cts__.xml files.  Writes one JSON report per file to --output-dir
(default: ./audit-reports/).  Prints a summary table to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mvp.corpus.auditors import ReferenceAuditor, StructureAuditor
from mvp.corpus.tei_document import LenientTEIDocument


def _find_tei_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*.xml")
        if p.name != "__cts__.xml"
    )


def _audit_file(path: Path) -> dict:
    doc = LenientTEIDocument(path)
    s_report = StructureAuditor(doc).audit()
    r_report = ReferenceAuditor(doc).audit()
    return {
        "path": str(path),
        "structure": json.loads(s_report.to_json()),
        "reference": json.loads(r_report.to_json()),
    }


def _collect_paths(inputs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for p in inputs:
        if p.is_dir():
            paths.extend(_find_tei_files(p))
        elif p.is_file():
            paths.append(p)
        else:
            print(f"WARNING: {p} does not exist, skipping", file=sys.stderr)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs", nargs="+", type=Path, metavar="FILE_OR_DIR",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("audit-reports"),
        metavar="DIR",
    )
    args = parser.parse_args()

    paths = _collect_paths(args.inputs)
    if not paths:
        print("No TEI files found.", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'File':<50} {'Type':<22} {'CiteStruct':>10} {'Issues':>7}")
    print(f"{'-'*50} {'-'*22} {'-'*10} {'-'*7}")

    errors = 0
    for path in paths:
        try:
            combined = _audit_file(path)
            out = args.output_dir / (path.stem + ".json")
            out.write_text(json.dumps(combined, indent=2))

            s = combined["structure"]
            r = combined["reference"]
            total_issues = len(s.get("issues", [])) + len(r.get("issues", []))
            has_cs = r.get("has_cite_structure", False)
            print(
                f"{path.name:<50} "
                f"{s.get('structural_type', 'unknown'):<22} "
                f"{'yes' if has_cs else 'no':>10} "
                f"{total_issues:>7}"
            )
        except Exception as exc:
            print(f"ERROR {path.name}: {exc}", file=sys.stderr)
            errors += 1

    print(f"\n{len(paths)} files processed, {errors} errors.")
    print(f"Reports written to {args.output_dir}/")
    return errors


if __name__ == "__main__":
    sys.exit(main())
