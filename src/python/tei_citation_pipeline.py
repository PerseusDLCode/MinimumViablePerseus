#!/usr/bin/env python3
"""
tei_citation_pipeline.py — Perseus TEI citation normalization pipeline.

Three phases:
  Phase 1  Structural audit: characterize citation hierarchy, xml:base
           correctness, milestones, and propose a <citeStructure> block.
  Phase 2  xml:base normalization: repair xml:base on every citable node
           so it carries the full CTS URN for that node.
  Phase 3  xml:id addition: add xml:id attributes compositionally derived
           from the CTS URN, creating stable token-level anchors for NLP
           annotation pipelines.

Usage:
  tei-audit FILE [FILE ...] [options]

Options:
  --phase {1,2,3}   Run only this phase (default: 1)
  --fix             Phase 2/3: write repaired file(s) (requires --output for
                    single file, or --output-dir for multiple files)
  --output PATH     Output path for a single fixed file
  --output-dir DIR  Output directory for fixed files (uses original filenames)
  --verbose         Extra diagnostic output
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from mvp.auditors import StructureAuditor
from mvp.normalizers import phase2_normalize, phase3_add_ids
from mvp.tei_document import TEIDocument


def _resolve_output(
    path: Path, args: argparse.Namespace, total: int
) -> Path:
    if args.output and total == 1:
        return args.output
    if args.output_dir:
        return args.output_dir / path.name
    suffix = "_fixed" if args.phase == 2 else "_with_ids"
    return path.with_stem(path.stem + suffix)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="+", type=Path, metavar="FILE")
    p.add_argument(
        "--phase", type=int, choices=[1, 2, 3], default=1,
        help="Phase to run (default: 1)",
    )
    p.add_argument("--fix", action="store_true")
    p.add_argument("--output", type=Path, metavar="PATH")
    p.add_argument("--output-dir", type=Path, metavar="DIR")
    p.add_argument("--verbose", action="store_true")
    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.phase in (2, 3) and not args.fix:
        print(
            f"Phase {args.phase} selected but --fix not given; "
            "running in dry-run mode (audit only).",
            file=sys.stderr,
        )

    errors = 0
    for path in args.files:
        if not path.exists():
            print(f"ERROR: {path} does not exist", file=sys.stderr)
            errors += 1
            continue

        try:
            doc = TEIDocument(path)
            auditor = StructureAuditor(doc)
            report = auditor.audit()

            if args.phase == 1:
                print(report.render_text())

            elif args.phase == 2:
                print(report.render_text())
                if args.fix:
                    out = _resolve_output(path, args, len(args.files))
                    counts = phase2_normalize(path, out, verbose=args.verbose)
                    total = sum(counts.values())
                    print(f"\nPhase 2 complete: {total} changes written to {out}")
                    print(
                        f"  div fixed: {counts['div_fixed']}, "
                        f"div added: {counts['div_added']}, "
                        f"leaf fixed: {counts['leaf_fixed']}, "
                        f"leaf added: {counts['leaf_added']}"
                    )

            elif args.phase == 3:
                print(report.render_text())
                if args.fix:
                    out = _resolve_output(path, args, len(args.files))
                    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
                        tmp_path = Path(tmp.name)
                    counts2 = phase2_normalize(path, tmp_path, verbose=args.verbose)
                    counts3 = phase3_add_ids(tmp_path, out, verbose=args.verbose)
                    tmp_path.unlink()
                    print(f"\nPhase 2+3 complete → {out}")
                    print(
                        f"  Phase 2 — div fixed: {counts2['div_fixed']}, "
                        f"div added: {counts2['div_added']}, "
                        f"leaf fixed: {counts2['leaf_fixed']}, "
                        f"leaf added: {counts2['leaf_added']}"
                    )
                    print(
                        f"  Phase 3 — div IDs added: {counts3['div_added']}, "
                        f"leaf IDs added: {counts3['leaf_added']}"
                    )

        except Exception as exc:
            print(f"ERROR processing {path.name}: {exc}", file=sys.stderr)
            if args.verbose:
                import traceback
                traceback.print_exc()
            errors += 1

    return errors


if __name__ == "__main__":
    sys.exit(main())
