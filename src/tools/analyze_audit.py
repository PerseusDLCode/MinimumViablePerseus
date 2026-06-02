#!/usr/bin/env python3
"""
analyze_audit.py — Focused defect analysis of audit-report JSON files.

Usage:
  analyze_audit.py REPORT_DIR [REPORT_DIR ...]  [--list-files]

Each REPORT_DIR is a directory of *.json files produced by run_audit.py.
The corpus name is taken from the directory name.

Reports on two defect categories:
  1. No effective citation declarations (no refsDecl elements, or all empty)
  2. Faulty xml:base — elements that carry xml:base but the value is wrong,
     plus elements that carry @n but have no xml:base at all.

With --list-files, prints every affected filename under each category.

Example:
  analyze_audit.py data/analysis/greekLit data/analysis/latinLit \\
                   data/analysis/first1kgreek data/analysis/csel
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


# ── data loading ──────────────────────────────────────────────────────────────

def _load_reports(directory: Path) -> list[dict]:
    reports = []
    for p in sorted(directory.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            if "structure" not in data:
                continue  # skip non-TEI reports (e.g. catalog.json)
            data["_filename"] = p.stem
            reports.append(data)
        except Exception as exc:
            print(f"  SKIP {p.name}: {exc}", file=sys.stderr)
    return reports


# ── defect classifiers ────────────────────────────────────────────────────────

def _refsDecl_status(rep: dict) -> str:
    """Classify the refsDecl situation for a single report.

    Returns one of:
      'none'    — refsDecls list is empty
      'empty'   — refsDecls present but none carry citation info
      'ok'      — at least one refsDecl has cref_pattern_names or cite_units
    """
    rds = rep.get("reference", {}).get("refsDecls", [])
    if not rds:
        return "none"
    if any(rd.get("cref_pattern_names") or rd.get("cite_units") for rd in rds):
        return "ok"
    return "empty"


def _xml_base_defects(rep: dict) -> tuple[Counter, Counter]:
    """Return (wrong_by_type, missing_by_type) element Counters.

    wrong_by_type  — elements that have xml:base but the value is incorrect
    missing_by_type — elements that have @n (citable) but no xml:base at all
    Keys are strings like 'div[book]', 'l', 'p', etc.
    """
    wrong: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    for lvl in rep.get("structure", {}).get("citation_levels", []):
        subtype = lvl.get("subtype", "")
        elem = lvl.get("element", "?")
        key = f"{elem}[{subtype}]" if subtype else elem
        with_base = lvl.get("with_base", 0)
        base_correct = lvl.get("base_correct", 0)
        with_n = lvl.get("with_n", 0)
        wrong[key] += with_base - base_correct
        missing[key] += with_n - with_base
    return wrong, missing


# ── per-corpus analysis ───────────────────────────────────────────────────────

def _analyse_corpus(reports: list[dict]) -> dict:
    no_refs: list[str] = []    # no refsDecl elements at all
    empty_refs: list[str] = [] # refsDecl present but effectively empty

    wrong_files: list[str] = []    # files with any wrong xml:base
    missing_files: list[str] = []  # files with any missing xml:base on @n elems

    wrong_by_type: Counter[str] = Counter()    # aggregate element counts
    missing_by_type: Counter[str] = Counter()

    for rep in reports:
        fname = rep["_filename"]
        status = _refsDecl_status(rep)
        if status == "none":
            no_refs.append(fname)
        elif status == "empty":
            empty_refs.append(fname)

        wrong, missing = _xml_base_defects(rep)
        if sum(wrong.values()) > 0:
            wrong_files.append(fname)
            wrong_by_type.update(wrong)
        if sum(missing.values()) > 0:
            missing_files.append(fname)
            missing_by_type.update(missing)

    return {
        "n": len(reports),
        "no_refs": no_refs,
        "empty_refs": empty_refs,
        "wrong_files": wrong_files,
        "missing_files": missing_files,
        "wrong_by_type": wrong_by_type,
        "missing_by_type": missing_by_type,
    }


# ── display ───────────────────────────────────────────────────────────────────

def _section(title: str) -> None:
    print(f"\n## {title}")


def _table(rows: list[tuple], headers: tuple) -> None:
    print("| " + " | ".join(str(h) for h in headers) + " |")
    print("|" + "|".join(" --- " for _ in headers) + "|")
    for row in rows:
        print("| " + " | ".join(str(c) for c in row) + " |")


def pct(n: int, total: int) -> str:
    return f"{100*n/total:5.1f}%" if total else "  n/a"


def _report(corpora: dict[str, dict], list_files: bool) -> None:
    names = list(corpora)
    stats = list(corpora.values())
    total = sum(s["n"] for s in stats)

    # ── overview ──────────────────────────────────────────────────────────────
    _section("Overview")
    header = ("Corpus",) + tuple(names) + ("Total",)
    _table([("Files audited",) + tuple(s["n"] for s in stats) + (total,)],
           header)

    # ── 1. No citation declarations ───────────────────────────────────────────
    _section("1. No effective citation declarations")
    print("  'none'  — refsDecls list is literally empty")
    print("  'empty' — refsDecl elements present but carry no cref patterns")
    print()

    rows = []
    for label, key in [
        ("No refsDecl elements (none)", "no_refs"),
        ("Empty refsDecl only (empty)",  "empty_refs"),
        ("Combined",                      None),
    ]:
        if key:
            row = (label,) + tuple(
                f"{len(s[key])} ({pct(len(s[key]), s['n'])})"
                for s in stats
            )
        else:
            combined_counts = [len(s["no_refs"]) + len(s["empty_refs"]) for s in stats]
            row = (label,) + tuple(
                f"{c} ({pct(c, s['n'])})"
                for c, s in zip(combined_counts, stats)
            )
        rows.append(row)
    _table(rows, header[:-1])

    if list_files:
        for name, s in corpora.items():
            if s["no_refs"] or s["empty_refs"]:
                print(f"\n### {name} — no refsDecl elements")
                for f in s["no_refs"]:
                    print(f"- `[none]  {f}`")
                print(f"\n### {name} — empty refsDecl only")
                for f in s["empty_refs"]:
                    print(f"- `[empty] {f}`")

    # ── 2a. Wrong xml:base ────────────────────────────────────────────────────
    _section("2a. Wrong xml:base (element has xml:base but value is incorrect)")

    row_files = ("Files affected",) + tuple(
        f"{len(s['wrong_files'])} ({pct(len(s['wrong_files']), s['n'])})"
        for s in stats
    )
    _table([row_files], header[:-1])

    print()
    print("Elements with wrong xml:base, by element type (all corpora):")
    combined_wrong: Counter[str] = Counter()
    for s in stats:
        combined_wrong.update(s["wrong_by_type"])
    etype_header = tuple(["Element type", "Total elements"] + names)
    etype_rows = []
    for etype in sorted(combined_wrong, key=lambda k: -combined_wrong[k]):
        if combined_wrong[etype] == 0:
            continue
        etype_rows.append(
            (etype, combined_wrong[etype]) + tuple(s["wrong_by_type"].get(etype, 0) for s in stats)
        )
    _table(etype_rows, etype_header)

    if list_files:
        for name, s in corpora.items():
            if s["wrong_files"]:
                print(f"\n### {name} — wrong xml:base")
                for f in s["wrong_files"]:
                    print(f"- `{f}`")

    # ── 2b. Missing xml:base on citable elements ──────────────────────────────
    _section("2b. Missing xml:base (element has @n but no xml:base at all)")

    row_files = ("Files affected",) + tuple(
        f"{len(s['missing_files'])} ({pct(len(s['missing_files']), s['n'])})"
        for s in stats
    )
    _table([row_files], header[:-1])

    print()
    print("Elements missing xml:base, by element type (all corpora):")
    combined_missing: Counter[str] = Counter()
    for s in stats:
        combined_missing.update(s["missing_by_type"])
    etype_header = tuple(["Element type", "Total elements"] + names)
    etype_rows = []
    for etype in sorted(combined_missing, key=lambda k: -combined_missing[k]):
        if combined_missing[etype] == 0:
            continue
        etype_rows.append(
            (etype, combined_missing[etype]) + tuple(s["missing_by_type"].get(etype, 0) for s in stats)
        )
    _table(etype_rows, etype_header)

    if list_files:
        for name, s in corpora.items():
            if s["missing_files"]:
                print(f"\n### {name} — missing xml:base on citable elements")
                for f in s["missing_files"]:
                    print(f"- `{f}`")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "report_dirs", nargs="+", type=Path, metavar="REPORT_DIR",
    )
    parser.add_argument(
        "--list-files", action="store_true",
        help="Print filenames of every affected text under each category",
    )
    args = parser.parse_args()

    corpora: dict[str, dict] = {}
    for d in args.report_dirs:
        if not d.is_dir():
            print(f"ERROR: {d} is not a directory", file=sys.stderr)
            return 1
        name = d.name
        print(f"Loading {name} ...", file=sys.stderr)
        reports = _load_reports(d)
        if not reports:
            print(f"  WARNING: no .json files found in {d}", file=sys.stderr)
            continue
        corpora[name] = _analyse_corpus(reports)

    if not corpora:
        print("No data loaded.", file=sys.stderr)
        return 1

    _report(corpora, args.list_files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
