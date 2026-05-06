#!/usr/bin/env python3
"""Run the full annotation pipeline (prep + tokenize) over a corpus.

Applies add_xml_ids.xsl then tokenize.xsl to every TEI file in SOURCE,
writing prepared documents to PREP_DIR and token documents to TOKEN_DIR.
Emits a tab-separated summary to SUMMARY_FILE (or stdout if omitted).

Usage:
    python src/tools/run_annotation_pipeline.py SOURCE PREP_DIR TOKEN_DIR [SUMMARY_FILE]

    SOURCE may be a file or a directory (searched recursively; __cts__.xml skipped).

Examples:
    python src/tools/run_annotation_pipeline.py \\
        data/canonical-greekLit/data \\
        /tmp/greek-prepped \\
        /tmp/greek-tokens \\
        /tmp/greek-annotation-summary.tsv
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from saxonche import PySaxonProcessor

_XSLT_ROOT = Path(__file__).parent.parent / "xslt"
_PREP_XSL  = _XSLT_ROOT / "add_xml_ids.xsl"
_TOK_XSL   = _XSLT_ROOT / "tokenize.xsl"

# Saxon surfaces xsl:message output via its error/message listener.
# We capture it by redirecting through a custom listener if available,
# otherwise we parse the string output from transform_to_string.
_WARNING_RE = re.compile(r"WARNING:", re.IGNORECASE)
_ERROR_RE   = re.compile(r"(ERROR|Exception|SaxonApiException)", re.IGNORECASE)


@dataclass
class FileResult:
    source: Path
    prep_errors: list[str]  = field(default_factory=list)
    tok_errors:  list[str]  = field(default_factory=list)
    warnings:    list[str]  = field(default_factory=list)
    token_count: int         = 0
    skipped:     bool        = False


def _iter_tei_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    return sorted(p for p in source.rglob("*.xml") if p.name != "__cts__.xml")


def _count_tokens(xml_str: str) -> int:
    return xml_str.count("<token ")


def _run_transform(transformer, *, source_file: str) -> tuple[str | None, list[str], list[str]]:
    """Run a compiled transformer; return (output_str, warnings, errors)."""
    warnings: list[str] = []
    errors:   list[str] = []
    try:
        result = transformer.transform_to_string(source_file=source_file)
        # Saxon xsl:message lines appear in error_message when they are not
        # fatal; collect them.
        msg = transformer.error_message or ""
        for line in msg.splitlines():
            line = line.strip()
            if not line:
                continue
            if _ERROR_RE.search(line):
                errors.append(line)
            else:
                warnings.append(line)
        return result, warnings, errors
    except Exception as exc:
        errors.append(str(exc))
        return None, warnings, errors


def run(
    source: Path,
    prep_dir: Path,
    token_dir: Path,
    summary_path: Path | None,
    *,
    prep_xsl: Path = _PREP_XSL,
    tok_xsl:  Path = _TOK_XSL,
) -> None:
    prep_dir.mkdir(parents=True, exist_ok=True)
    token_dir.mkdir(parents=True, exist_ok=True)

    files = _iter_tei_files(source)
    total = len(files)
    print(f"Source files : {total}")
    print(f"Prep output  : {prep_dir}")
    print(f"Token output : {token_dir}")
    if summary_path:
        print(f"Summary      : {summary_path}")
    print()

    results: list[FileResult] = []
    t0 = time.monotonic()

    with PySaxonProcessor(license=False) as proc:
        xslt = proc.new_xslt30_processor()
        prep_t = xslt.compile_stylesheet(stylesheet_file=str(prep_xsl))
        tok_t  = xslt.compile_stylesheet(stylesheet_file=str(tok_xsl))

        for i, path in enumerate(files, 1):
            res = FileResult(source=path)

            # ── Stage 1: add xml:ids ──────────────────────────────────────
            prepped_xml, res.warnings, res.prep_errors = _run_transform(
                prep_t, source_file=str(path)
            )
            if prepped_xml is None:
                res.skipped = True
                results.append(res)
                print(f"[{i}/{total}] PREP FAILED  {path.name}", flush=True)
                continue

            # Write prepared document to a temp path so tokenizer can read it
            prep_out = prep_dir / path.name
            prep_out.write_text(prepped_xml, encoding="utf-8")

            # ── Stage 2: tokenize ─────────────────────────────────────────
            tok_xml, tok_warnings, tok_errors = _run_transform(
                tok_t, source_file=str(prep_out)
            )
            res.warnings   += tok_warnings
            res.tok_errors  = tok_errors

            if tok_xml is None:
                res.skipped = True
                results.append(res)
                print(f"[{i}/{total}] TOK  FAILED  {path.name}", flush=True)
                continue

            res.token_count = _count_tokens(tok_xml)
            tok_out = token_dir / f"{path.stem}-tokens.xml"
            tok_out.write_text(tok_xml, encoding="utf-8")

            error_flag = "ERR " if (res.prep_errors or res.tok_errors) else "    "
            print(
                f"[{i}/{total}] {error_flag} {path.name}"
                f"  tokens={res.token_count}"
                f"  warn={len(res.warnings)}"
                f"  err={len(res.prep_errors)+len(res.tok_errors)}",
                flush=True,
            )
            results.append(res)

    elapsed = time.monotonic() - t0
    _write_summary(results, summary_path, elapsed)


def _write_summary(
    results: list[FileResult],
    summary_path: Path | None,
    elapsed: float,
) -> None:
    total_tokens  = sum(r.token_count for r in results)
    total_errors  = sum(len(r.prep_errors) + len(r.tok_errors) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    failed         = sum(1 for r in results if r.skipped)

    header = (
        "source_file\t"
        "tokens\t"
        "prep_errors\t"
        "tok_errors\t"
        "warnings\t"
        "skipped\t"
        "prep_error_detail\t"
        "tok_error_detail"
    )
    rows = []
    for r in results:
        rows.append(
            f"{r.source.name}\t"
            f"{r.token_count}\t"
            f"{len(r.prep_errors)}\t"
            f"{len(r.tok_errors)}\t"
            f"{len(r.warnings)}\t"
            f"{'yes' if r.skipped else ''}\t"
            f"{' | '.join(r.prep_errors[:3])}\t"
            f"{' | '.join(r.tok_errors[:3])}"
        )

    footer_lines = [
        "",
        f"# Files processed : {len(results)}",
        f"# Files failed    : {failed}",
        f"# Total tokens    : {total_tokens:,}",
        f"# Total errors    : {total_errors}",
        f"# Total warnings  : {total_warnings}",
        f"# Elapsed         : {elapsed:.1f}s",
    ]

    content = "\n".join([header] + rows + footer_lines) + "\n"

    if summary_path:
        summary_path.write_text(content, encoding="utf-8")
    else:
        print(content)

    # Always print footer to console
    for line in footer_lines[1:]:
        print(line)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run full annotation pipeline over a TEI corpus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("source",   type=Path, help="Source directory or file")
    parser.add_argument("prep_dir", type=Path, help="Output directory for prepared XML")
    parser.add_argument("token_dir",type=Path, help="Output directory for token XML")
    parser.add_argument("summary",  type=Path, nargs="?", help="Summary TSV output file")
    parser.add_argument("--prep-xsl", type=Path, default=_PREP_XSL)
    parser.add_argument("--tok-xsl",  type=Path, default=_TOK_XSL)
    args = parser.parse_args()

    run(
        args.source,
        args.prep_dir,
        args.token_dir,
        args.summary,
        prep_xsl=args.prep_xsl,
        tok_xsl=args.tok_xsl,
    )


if __name__ == "__main__":
    main()
