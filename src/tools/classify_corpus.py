#!/usr/bin/env python3
"""
classify_corpus.py — Classify audit-report JSON files by structural family.

Usage:
  classify_corpus.py REPORT_DIR [REPORT_DIR ...]  [--list-files] [--tsv]

Each REPORT_DIR is a directory of *.json files produced by run_audit.py.
The corpus name is taken from the directory name.

Prints a summary table showing how many documents fall into each of five
structural families, with percentages per corpus.  With --list-files, also
prints every filename under each family.  With --tsv, emits tab-separated
values instead of a Markdown table (useful for piping into a spreadsheet).

Families
--------
1. hierarchical-div
   All citable units are <div type="textpart"> elements.
   Leaf unit is a <div>, not <l> or <p> or <milestone>.
   Examples: Thucydides (book/chapter/section), Aristotle Politics.

2. verse-l-leaf
   Div hierarchy for upper levels; citable leaf is <l>.
   Examples: Homer (book/line), Anthologia Palatina (book/epigram/line).

3. milestone-primary
   Primary citation unit is a <milestone> element.
   No significant div hierarchy; milestones carry the citation.
   Examples: Argonautica (card), Plato (stephpage).

4. drama
   Flat or near-flat list of <div type="textpart"> with many distinct
   one-off subtypes (>= DRAMA_SUBTYPE_THRESHOLD distinct subtypes at
   the deepest div level, or specific dramatic subtype vocabulary).
   Examples: Aristophanes, Sophocles, Euripides.

5. parallel-tradition
   Has both a div/milestone primary citation AND a separate scholarly
   milestone tradition (Bekker, Stephanus, Jebb, casaubon, etc.).
   Requires two refsDecl elements.
   Examples: Aristotle Poetics (chapter + Bekker), Plato (section + Stephanus).

6. unknown / other
   Doesn't cleanly match any family above — needs manual inspection.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


# ── constants ─────────────────────────────────────────────────────────────────

# Milestone unit names that indicate a scholarly parallel tradition,
# as opposed to a primary citation tradition.
PARALLEL_TRADITION_MILESTONES = {
    "bekker_page", "bekkerpage", "bekker",
    "stephpage", "stephanus",
    "casaubonpage", "casaubon",
    "jebb_page", "jebb",
    "reiskpage", "reisk",
    "reitz_page", "reitz",
    "olearius_page", "olearius",
    "whiston_section", "whiston_chapter",
    "camerarius_2ed_page",
    "loebline",
    "mpage", "rpage", "pagep", "pagew",
    "altpage", "altref", "altbook", "altchap", "altchapter",
    "blancard_page", "borheck_page", "hudson_page", "mueller_page",
    "tlnum", "signaline",
}

# Dramatic structural subtype vocabulary — if a document uses several of
# these, it's drama regardless of how many distinct subtypes it has.
DRAMA_SUBTYPES = {
    "episode", "Episode", "prologue", "Prologue", "parodos", "Parodos",
    "exodos", "Exodus", "stasimon", "choral", "Choral", "strophe",
    "antistrophe", "ephymnion", "ephymn", "ephymn.", "epode",
    "anapests", "lyric", "iambics", "iambic", "trochees",
    "pnigos", "antipnigos", "antepirrheme", "epirrheme", "antepirrhema",
    "epirrhema", "parabasis", "Parabasis", "agon", "Agon",
    "katakeleusmenos", "antikatakeleusmenos", "katakeleusmos",
    "antikatakeleusmos", "Katakeleusmos", "Antikatakeleusmos",
    "kommos", "mesode", "monody", "proagon", "scene",
    "Lyric-Scene", "lyric_anapests", "epirrheme", "Epirrheme",
    "Antepirrheme",
    # Latin drama
    "act",
}

# Number of distinct dramatic subtypes required to call something drama
# (in case only one or two appear — could just be a prefatory section).
DRAMA_SUBTYPE_MIN_MATCHES = 2

# Milestone units that indicate PRIMARY citation (not parallel tradition).
# A document whose only milestones are in this set is milestone-primary.
PRIMARY_MILESTONE_UNITS = {
    "card", "section", "line", "para", "Para", "paragraph",
    "chapter", "part", "subsection", "verse", "fragment",
    "book", "volume", "tale", "unit", "strophe", "antistrophe",
    "speech", "head",
}


# ── loading ───────────────────────────────────────────────────────────────────

def _load_reports(directory: Path) -> list[dict]:
    reports = []
    for p in sorted(directory.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            if "structure" not in data or "reference" not in data:
                continue
            data["_filename"] = p.stem
            data["_corpus"] = directory.name
            reports.append(data)
        except Exception as exc:
            print(f"  SKIP {p.name}: {exc}", file=sys.stderr)
    return reports


# ── classification ────────────────────────────────────────────────────────────

def _leaf_elements(report: dict) -> set[str]:
    """Return the set of element names at the deepest citation level."""
    levels = report.get("structure", {}).get("citation_levels", [])
    if not levels:
        return set()
    max_depth = max(lvl.get("depth", 0) for lvl in levels)
    return {
        lvl["element"]
        for lvl in levels
        if lvl.get("depth", 0) == max_depth
    }


def _all_subtypes(report: dict) -> set[str]:
    """Return all div subtypes mentioned in citation_levels."""
    levels = report.get("structure", {}).get("citation_levels", [])
    return {lvl.get("subtype", "") for lvl in levels if lvl.get("subtype")}


def _milestone_units(report: dict) -> set[str]:
    """Return all milestone unit names in the document."""
    return {
        m.get("unit", "") if isinstance(m, dict) else str(m)
        for m in report.get("structure", {}).get("milestones", [])
    }


def _has_parallel_tradition(report: dict) -> bool:
    """True if the document has any parallel-tradition scholarly milestones."""
    units = {u.lower() for u in _milestone_units(report)}
    return bool(units & {p.lower() for p in PARALLEL_TRADITION_MILESTONES})


def _drama_score(report: dict) -> int:
    """Count how many dramatic subtype vocabulary words appear."""
    subtypes = _all_subtypes(report)
    return len(subtypes & DRAMA_SUBTYPES)


def classify(report: dict) -> str:
    """
    Return a family label for this audit report.

    Classification order matters — a document can satisfy multiple
    criteria.  We assign the most specific matching family.
    """
    struct = report.get("structure", {})
    structural_type = struct.get("structural_type", "unknown")
    milestones = _milestone_units(report)
    leaf_elems = _leaf_elements(report)
    has_parallel = _has_parallel_tradition(report)
    drama = _drama_score(report)

    # Primary milestones only (no div hierarchy with subtypes)
    primary_milestones = milestones - PARALLEL_TRADITION_MILESTONES
    only_primary_milestones = bool(primary_milestones) and not bool(
        _all_subtypes(report) - {""}
    )

    # ── family 5: parallel tradition ─────────────────────────────────────────
    # Must have BOTH a substantial primary structure AND parallel milestones.
    # Don't assign this to purely-milestone texts that happen to have Bekker.
    if has_parallel and structural_type == "div-hierarchy":
        return "5-parallel-tradition"

    # ── family 3: milestone-primary ──────────────────────────────────────────
    # Primary citation is carried by milestones; divs are vestigial.
    if structural_type == "milestone-sections" or only_primary_milestones:
        return "3-milestone-primary"

    # ── family 4: drama ──────────────────────────────────────────────────────
    if drama >= DRAMA_SUBTYPE_MIN_MATCHES:
        return "4-drama"

    # ── family 2: verse with <l> leaves ─────────────────────────────────────
    if "l" in leaf_elems:
        return "2-verse-l-leaf"

    # ── family 1: hierarchical div ───────────────────────────────────────────
    if structural_type == "div-hierarchy" and leaf_elems <= {"div", "p", "ab", "seg"}:
        return "1-hierarchical-div"

    # ── catch-all ────────────────────────────────────────────────────────────
    return "6-unknown"


FAMILY_LABELS = {
    "1-hierarchical-div":    "1. Hierarchical div",
    "2-verse-l-leaf":        "2. Verse with <l> leaf",
    "3-milestone-primary":   "3. Milestone-primary",
    "4-drama":               "4. Drama",
    "5-parallel-tradition":  "5. Parallel tradition",
    "6-unknown":             "6. Unknown / other",
}

FAMILY_ORDER = list(FAMILY_LABELS.keys())


# ── reporting ─────────────────────────────────────────────────────────────────

def pct(n: int, total: int) -> str:
    return f"{100 * n / total:5.1f}%" if total else "   n/a"


def _markdown_table(headers: list, rows: list[list]) -> None:
    print("| " + " | ".join(str(h) for h in headers) + " |")
    print("|" + "|".join(" --- " for _ in headers) + "|")
    for row in rows:
        print("| " + " | ".join(str(c) for c in row) + " |")


def _tsv_table(headers: list, rows: list[list]) -> None:
    print("\t".join(str(h) for h in headers))
    for row in rows:
        print("\t".join(str(c) for c in row))


def _report(
    all_reports: list[dict],
    corpus_names: list[str],
    list_files: bool,
    tsv: bool,
) -> None:
    emit = _tsv_table if tsv else _markdown_table

    # Group by corpus, classify each
    by_corpus: dict[str, list[dict]] = defaultdict(list)
    for rep in all_reports:
        by_corpus[rep["_corpus"]].append(rep)

    family_by_corpus: dict[str, Counter] = {}
    files_by_family: dict[str, list[str]] = defaultdict(list)

    for corpus in corpus_names:
        counts: Counter = Counter()
        for rep in by_corpus.get(corpus, []):
            family = classify(rep)
            counts[family] += 1
            files_by_family[family].append(f"[{corpus}] {rep['_filename']}")
        family_by_corpus[corpus] = counts

    totals_per_family: Counter = Counter()
    for counts in family_by_corpus.values():
        totals_per_family.update(counts)

    corpus_totals = {c: sum(family_by_corpus[c].values()) for c in corpus_names}
    grand_total = sum(corpus_totals.values())

    # ── overview ──────────────────────────────────────────────────────────────
    print("\n## Corpus overview\n")
    headers = ["Corpus"] + corpus_names + ["Total"]
    rows = [
        ["Files classified"]
        + [corpus_totals[c] for c in corpus_names]
        + [grand_total]
    ]
    emit(headers, rows)

    # ── family breakdown ──────────────────────────────────────────────────────
    print("\n## Structural family breakdown\n")
    headers = ["Family"] + [f"{c} (n / %)" for c in corpus_names] + ["Total (n / %)"]
    rows = []
    for fam in FAMILY_ORDER:
        label = FAMILY_LABELS[fam]
        cells = []
        for c in corpus_names:
            n = family_by_corpus[c][fam]
            total = corpus_totals[c]
            cells.append(f"{n} ({pct(n, total)})")
        total_n = totals_per_family[fam]
        cells.append(f"{total_n} ({pct(total_n, grand_total)})")
        rows.append([label] + cells)
    emit(headers, rows)

    # ── pattern shapes within each family (no file listing needed) ────────────
    print("\n## cRefPattern shapes by family\n")
    print("Most common cref-pattern level sequences (coarsest → finest):\n")

    pattern_by_family: dict[str, Counter] = defaultdict(Counter)
    for rep in all_reports:
        fam = classify(rep)
        patterns = rep.get("structure", {}).get("cref_patterns", [])
        key = " / ".join(patterns) if patterns else "(none)"
        pattern_by_family[fam][key] += 1

    for fam in FAMILY_ORDER:
        if not pattern_by_family[fam]:
            continue
        print(f"### {FAMILY_LABELS[fam]}\n")
        headers = ["Pattern (coarsest → finest)", "Count"]
        rows = [
            [pat, cnt]
            for pat, cnt in pattern_by_family[fam].most_common(10)
        ]
        emit(headers, rows)
        print()

    # ── per-family file listing ───────────────────────────────────────────────
    if list_files:
        print("\n## File listing by family\n")
        for fam in FAMILY_ORDER:
            files = files_by_family.get(fam, [])
            if not files:
                continue
            print(f"### {FAMILY_LABELS[fam]} ({len(files)} files)\n")
            for f in sorted(files):
                print(f"- `{f}`")
            print()


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
        help="Print every filename under each family",
    )
    parser.add_argument(
        "--tsv", action="store_true",
        help="Emit tab-separated values instead of Markdown tables",
    )
    args = parser.parse_args()

    all_reports: list[dict] = []
    corpus_names: list[str] = []

    for d in args.report_dirs:
        if not d.is_dir():
            print(f"ERROR: {d} is not a directory", file=sys.stderr)
            return 1
        name = d.name
        corpus_names.append(name)
        print(f"Loading {name} ...", file=sys.stderr)
        reports = _load_reports(d)
        if not reports:
            print(f"  WARNING: no usable .json files in {d}", file=sys.stderr)
        else:
            print(f"  {len(reports)} reports loaded", file=sys.stderr)
        all_reports.extend(reports)

    if not all_reports:
        print("No data loaded.", file=sys.stderr)
        return 1

    _report(all_reports, corpus_names, args.list_files, args.tsv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
