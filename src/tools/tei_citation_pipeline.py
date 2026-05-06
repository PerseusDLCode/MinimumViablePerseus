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
  python3 tei_citation_pipeline.py FILE [FILE ...] [options]

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
import copy
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lxml import etree

# ---------------------------------------------------------------------------
# Namespace constants
# ---------------------------------------------------------------------------

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI_NS, "xml": XML_NS}

# Convenience Clark-notation attribute names
XML_BASE = f"{{{XML_NS}}}base"
XML_ID = f"{{{XML_NS}}}id"
XML_LANG = f"{{{XML_NS}}}lang"


# ---------------------------------------------------------------------------
# Data classes for audit results
# ---------------------------------------------------------------------------

@dataclass
class CitationLevel:
    """One level in the citation hierarchy."""
    element: str          # "div", "l", "p", "ab", "seg"
    subtype: str          # div subtype ("book", "chapter", "section") or ""
    depth: int            # nesting depth from edition div (0-based)
    count: int            # number of instances
    with_n: int           # instances that have @n
    with_base: int        # instances that have xml:base
    with_id: int          # instances that have xml:id
    base_correct: int     # instances where xml:base value is correct
    base_wrong_examples: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class MilestoneInfo:
    unit: str
    count: int


@dataclass
class AuditReport:
    path: Path
    base_urn: str          # the CTS work/version URN
    citation_levels: list[CitationLevel]
    milestones: list[MilestoneInfo]
    cref_patterns: list[str]   # raw cRefPattern @n values, deepest first
    structural_type: str   # "div-hierarchy", "milestone-sections",
                           # "milestone-cards", "flat-lines", "unknown"
    issues: list[str]
    proposed_cite_structure: str   # XML fragment as string


# ---------------------------------------------------------------------------
# URN / citation helpers
# ---------------------------------------------------------------------------

def extract_base_urn(root: etree._Element) -> str:
    """
    Return the CTS work/version URN from the edition div's @n attribute.
    Falls back to xml:base on the edition div if @n is absent.
    """
    edition_divs = root.xpath(
        "//tei:div[@type='edition']", namespaces=NS
    )
    if not edition_divs:
        return ""
    ed = edition_divs[0]
    urn = ed.get("n", "") or ed.get(XML_BASE, "")
    return urn.rstrip(":")


def parse_cref_patterns(root: etree._Element) -> list[str]:
    """Return cRefPattern @n values from the CTS refsDecl, deepest first."""
    patterns = root.xpath(
        "//tei:refsDecl[@n='CTS']/tei:cRefPattern/@n", namespaces=NS
    )
    return list(patterns)


# ---------------------------------------------------------------------------
# Structural analysis helpers
# ---------------------------------------------------------------------------

def classify_structure(root: etree._Element) -> str:
    """
    Determine which broad structural type this document uses.

    Returns one of:
      "div-hierarchy"       — nested <div type="textpart"> elements
      "milestone-sections"  — milestone[@unit="section"] inside divs/p
      "milestone-cards"     — milestone[@unit="card"] (prose divided by card)
      "flat-lines"          — <l> elements without book-level nesting
      "unknown"
    """
    ms_units: dict[str, int] = {}
    for m in root.xpath("//tei:milestone[@unit]", namespaces=NS):
        u = m.get("unit", "")
        ms_units[u] = ms_units.get(u, 0) + 1

    textpart_divs = root.xpath(
        "//tei:div[@type='textpart']", namespaces=NS
    )
    leaf_lines = root.xpath("//tei:l", namespaces=NS)

    if "section" in ms_units and textpart_divs:
        return "milestone-sections"
    if "card" in ms_units:
        return "milestone-cards"
    if textpart_divs:
        return "div-hierarchy"
    if leaf_lines:
        return "flat-lines"
    return "unknown"


def get_citation_levels(root: etree._Element, base_urn: str) -> list[CitationLevel]:
    """
    Walk the document structure and characterise each citation level.

    For div-hierarchy and milestone-sections documents the levels are the
    distinct (element, subtype) pairs found under the edition div.  For
    flat-lines documents we also include <l>.  For milestone-sections we
    describe the milestone unit as a pseudo-level.
    """
    levels: list[CitationLevel] = []

    # --- div levels ---
    # Collect all distinct (subtype, depth) combinations
    edition_div = root.xpath("//tei:div[@type='edition']", namespaces=NS)
    if not edition_div:
        return levels
    ed = edition_div[0]

    depth_map: dict[tuple[str, int], list[etree._Element]] = {}
    for div in ed.xpath(".//tei:div[@type='textpart']", namespaces=NS):
        subtype = div.get("subtype", "")
        # Compute depth relative to edition div
        depth = 0
        parent = div.getparent()
        while parent is not None and parent != ed:
            if parent.get("type") == "textpart":
                depth += 1
            parent = parent.getparent()
        key = (subtype, depth)
        depth_map.setdefault(key, []).append(div)

    for (subtype, depth), divs in sorted(depth_map.items(), key=lambda x: x[0][1]):
        with_n = sum(1 for d in divs if d.get("n"))
        with_base = sum(1 for d in divs if d.get(XML_BASE))
        with_id = sum(1 for d in divs if d.get(XML_ID))

        # Check xml:base correctness for this level
        correct, wrong, wrong_examples = _check_div_base_correctness(
            divs, base_urn, depth
        )

        levels.append(CitationLevel(
            element="div",
            subtype=subtype,
            depth=depth,
            count=len(divs),
            with_n=with_n,
            with_base=with_base,
            with_id=with_id,
            base_correct=correct,
            base_wrong_examples=wrong_examples,
        ))

    # --- leaf line/para levels ---
    for tag in ("l", "p", "ab", "seg"):
        elems = ed.xpath(f".//tei:{tag}", namespaces=NS)
        if not elems:
            continue
        with_n = sum(1 for e in elems if e.get("n"))
        with_base = sum(1 for e in elems if e.get(XML_BASE))
        with_id = sum(1 for e in elems if e.get(XML_ID))

        correct, wrong, wrong_examples = _check_leaf_base_correctness(
            elems, base_urn, root, tag
        )

        # Compute nominal depth
        sample = elems[0]
        depth = 0
        parent = sample.getparent()
        while parent is not None and parent != ed:
            if parent.get("type") == "textpart":
                depth += 1
            parent = parent.getparent()

        levels.append(CitationLevel(
            element=tag,
            subtype="",
            depth=depth + 1,
            count=len(elems),
            with_n=with_n,
            with_base=with_base,
            with_id=with_id,
            base_correct=correct,
            base_wrong_examples=wrong_examples,
        ))

    return levels


def _ancestor_ns(elem: etree._Element, n: int) -> list[etree._Element]:
    """Return the first n textpart div ancestors, innermost first."""
    ancestors = []
    parent = elem.getparent()
    while parent is not None:
        if (parent.get("type") == "textpart" or
                parent.get("type") == "edition"):
            ancestors.append(parent)
            if len(ancestors) == n:
                break
        parent = parent.getparent()
    return ancestors


def _expected_div_base(div: etree._Element, base_urn: str) -> str:
    """
    Compute the correct xml:base value for a textpart div.
    Walks up the tree collecting @n values from textpart ancestors.
    """
    # Collect @n from this div and all textpart ancestors (not edition)
    chain: list[str] = []
    node: Optional[etree._Element] = div
    while node is not None:
        t = node.get("type", "")
        if t == "textpart":
            n = node.get("n", "?")
            chain.append(n)
        elif t == "edition":
            break
        node = node.getparent()
    chain.reverse()  # outermost first
    if not chain:
        return base_urn
    return f"{base_urn}:{'.'.join(chain)}"


def _expected_leaf_base(
    elem: etree._Element, base_urn: str, tag: str
) -> Optional[str]:
    """
    Compute the correct xml:base for a leaf element (l, p, ab, seg).
    Only meaningful when the element has @n.
    """
    n = elem.get("n")
    if not n:
        return None
    # Collect textpart ancestor chain
    chain: list[str] = []
    node = elem.getparent()
    while node is not None:
        if node.get("type") == "textpart":
            chain.append(node.get("n", "?"))
        elif node.get("type") == "edition":
            break
        node = node.getparent()
    chain.reverse()
    chain.append(n)
    return f"{base_urn}:{'.'.join(chain)}"


def _check_div_base_correctness(
    divs: list[etree._Element], base_urn: str, depth: int
) -> tuple[int, int, list[tuple[str, str]]]:
    correct = wrong = 0
    wrong_examples: list[tuple[str, str]] = []
    for div in divs:
        expected = _expected_div_base(div, base_urn)
        actual = div.get(XML_BASE, "MISSING")
        if actual == expected:
            correct += 1
        else:
            wrong += 1
            if len(wrong_examples) < 3:
                wrong_examples.append((expected, actual))
    return correct, wrong, wrong_examples


def _check_leaf_base_correctness(
    elems: list[etree._Element], base_urn: str, root: etree._Element, tag: str
) -> tuple[int, int, list[tuple[str, str]]]:
    correct = wrong = 0
    wrong_examples: list[tuple[str, str]] = []
    for elem in elems:
        if not elem.get("n"):
            continue
        expected = _expected_leaf_base(elem, base_urn, tag)
        actual = elem.get(XML_BASE, "MISSING")
        if actual == expected:
            correct += 1
        else:
            wrong += 1
            if len(wrong_examples) < 3:
                wrong_examples.append((str(expected), actual))
    return correct, wrong, wrong_examples


# ---------------------------------------------------------------------------
# citeStructure proposal
# ---------------------------------------------------------------------------

def propose_cite_structure(
    citation_levels: list[CitationLevel],
    cref_patterns: list[str],
    structural_type: str,
) -> str:
    """
    Build a <citeStructure> XML fragment reflecting the discovered hierarchy.
    This is a proposal only — it needs human review before being inserted
    into the TEIHeader.
    """
    # Build from deepest cRefPattern name outward, or fall back to levels
    level_names = list(reversed(cref_patterns)) if cref_patterns else [
        lv.subtype or lv.element
        for lv in sorted(citation_levels, key=lambda x: x.depth)
    ]

    if not level_names:
        return "<!-- citeStructure: insufficient information to propose -->"

    def _wrap(name: str, inner: str, indent: int) -> str:
        pad = "  " * indent
        unit = name
        xpath = f"tei:{_element_for_level(name)}[@n]"
        delim = "." if inner else ""
        use = "@n"
        if inner:
            return (
                f'{pad}<citeStructure unit="{unit}" '
                f'match="{xpath}" use="{use}" delim="{delim}">\n'
                f"{inner}\n"
                f"{pad}</citeStructure>"
            )
        else:
            return (
                f'{pad}<citeStructure unit="{unit}" '
                f'match="{xpath}" use="{use}"/>'
            )

    def _element_for_level(name: str) -> str:
        if name in ("book", "chapter", "section", "poem", "act", "scene"):
            return "div"
        if name in ("line", "l"):
            return "l"
        if name in ("paragraph", "p", "section"):
            return "p"
        return "div"

    # Build inside-out
    result = ""
    for name in reversed(level_names):
        result = _wrap(name, result, indent=0)

    # Indent the whole thing
    lines = result.splitlines()
    indented = "\n".join("        " + ln for ln in lines)
    return (
        "<!-- Proposed citeStructure (verify before inserting into TEIHeader) -->\n"
        "      <citeStructure>\n"
        f"{indented}\n"
        "      </citeStructure>"
    )


# ---------------------------------------------------------------------------
# Phase 1: Audit
# ---------------------------------------------------------------------------

def phase1_audit(path: Path, verbose: bool = False) -> AuditReport:
    parser = etree.XMLParser(recover=True, remove_comments=False)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()

    base_urn = extract_base_urn(root)
    cref_patterns = parse_cref_patterns(root)
    structural_type = classify_structure(root)
    citation_levels = get_citation_levels(root, base_urn)

    # Milestones
    ms_map: dict[str, int] = {}
    for m in root.xpath("//tei:milestone[@unit]", namespaces=NS):
        u = m.get("unit", "?")
        ms_map[u] = ms_map.get(u, 0) + 1
    milestones = [MilestoneInfo(u, c) for u, c in sorted(ms_map.items())]

    # Issues
    issues: list[str] = []
    if not base_urn:
        issues.append("CRITICAL: no CTS URN found on edition div @n")
    for lv in citation_levels:
        if lv.with_n < lv.count:
            issues.append(
                f"WARNING: {lv.count - lv.with_n} "
                f"<{lv.element} subtype='{lv.subtype}'> elements missing @n"
            )
        if lv.with_base == 0 and lv.count > 0:
            issues.append(
                f"INFO: <{lv.element} subtype='{lv.subtype}'> "
                f"has no xml:base attributes ({lv.count} elements)"
            )
        elif lv.base_correct < lv.with_base:
            wrong = lv.with_base - lv.base_correct
            issues.append(
                f"FIX NEEDED: {wrong} <{lv.element} subtype='{lv.subtype}'> "
                f"have incorrect xml:base"
            )

    proposed = propose_cite_structure(
        citation_levels, cref_patterns, structural_type
    )

    return AuditReport(
        path=path,
        base_urn=base_urn,
        citation_levels=citation_levels,
        milestones=milestones,
        cref_patterns=cref_patterns,
        structural_type=structural_type,
        issues=issues,
        proposed_cite_structure=proposed,
    )


def print_audit_report(report: AuditReport) -> None:
    print(f"\n{'='*70}")
    print(f"FILE: {report.path.name}")
    print(f"{'='*70}")
    print(f"Base URN:         {report.base_urn or '(none found)'}")
    print(f"Structural type:  {report.structural_type}")
    print(f"cRefPatterns:     {', '.join(report.cref_patterns) or '(none)'}")

    print("\nCITATION LEVELS:")
    print(f"  {'element':<8} {'subtype':<12} {'depth':>5} {'count':>7} "
          f"{'@n':>7} {'xml:base':>9} {'xml:id':>7} {'base OK':>8}")
    print(f"  {'-'*8} {'-'*12} {'-'*5} {'-'*7} {'-'*7} {'-'*9} {'-'*7} {'-'*8}")
    for lv in report.citation_levels:
        print(
            f"  {lv.element:<8} {lv.subtype:<12} {lv.depth:>5} {lv.count:>7} "
            f"{lv.with_n:>7} {lv.with_base:>9} {lv.with_id:>7} "
            f"{lv.base_correct:>8}"
        )
        if lv.base_wrong_examples:
            print("    xml:base problems (examples):")
            for expected, actual in lv.base_wrong_examples:
                print(f"      expected: {expected}")
                print(f"      actual:   {actual}")

    if report.milestones:
        print("\nMILESTONES:")
        for ms in report.milestones:
            print(f"  unit='{ms.unit}': {ms.count}")

    if report.issues:
        print("\nISSUES:")
        for issue in report.issues:
            print(f"  {issue}")
    else:
        print("\nNo issues found.")

    print(f"\nPROPOSED citeStructure:\n{report.proposed_cite_structure}")


# ---------------------------------------------------------------------------
# Phase 2: xml:base normalization
# ---------------------------------------------------------------------------

def phase2_normalize(
    path: Path, output_path: Path, verbose: bool = False
) -> dict[str, int]:
    """
    Repair xml:base on all citable elements.  Returns a dict of change counts.
    """
    parser = etree.XMLParser(recover=True, remove_comments=False)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()

    base_urn = extract_base_urn(root)
    if not base_urn:
        raise ValueError(f"Cannot normalize {path.name}: no base URN found")

    counts = {"div_fixed": 0, "div_added": 0,
              "leaf_fixed": 0, "leaf_added": 0}

    # Fix textpart divs
    edition_div = root.xpath("//tei:div[@type='edition']", namespaces=NS)
    if edition_div:
        for div in edition_div[0].xpath(
            ".//tei:div[@type='textpart']", namespaces=NS
        ):
            expected = _expected_div_base(div, base_urn)
            actual = div.get(XML_BASE)
            if actual is None:
                div.set(XML_BASE, expected)
                counts["div_added"] += 1
            elif actual != expected:
                div.set(XML_BASE, expected)
                counts["div_fixed"] += 1

        # Fix leaf elements
        for tag in ("l", "p", "ab", "seg"):
            for elem in edition_div[0].xpath(f".//tei:{tag}", namespaces=NS):
                if not elem.get("n"):
                    continue
                expected = _expected_leaf_base(elem, base_urn, tag)
                if expected is None:
                    continue
                actual = elem.get(XML_BASE)
                if actual is None:
                    elem.set(XML_BASE, expected)
                    counts["leaf_added"] += 1
                elif actual != expected:
                    elem.set(XML_BASE, expected)
                    counts["leaf_fixed"] += 1

    _write_tree(tree, output_path)

    if verbose:
        print(f"  Phase 2 changes: {counts}")

    return counts


# ---------------------------------------------------------------------------
# Phase 3: xml:id addition
# ---------------------------------------------------------------------------

def phase3_add_ids(
    path: Path, output_path: Path, verbose: bool = False
) -> dict[str, int]:
    """
    Add xml:id to all citable elements.  If xml:base is present and correct,
    derive xml:id from it; otherwise compute from scratch.

    xml:id values are the URN citation reference with ':' replaced by '.'
    (since xml:id must be a valid XML Name and cannot contain ':').
    e.g. urn:cts:greekLit:tlg0001.tlg001.perseus-grc2:1.247
    becomes tlg0001.tlg001.perseus-grc2.1.247
    """
    parser = etree.XMLParser(recover=True, remove_comments=False)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()

    base_urn = extract_base_urn(root)
    if not base_urn:
        raise ValueError(f"Cannot add IDs to {path.name}: no base URN found")

    counts = {"div_added": 0, "div_skipped": 0,
              "leaf_added": 0, "leaf_skipped": 0}

    def urn_to_id(urn: str) -> str:
        """Convert a full CTS URN to a valid xml:id."""
        # Strip the urn:cts: prefix and replace remaining ':' with '.'
        # e.g. urn:cts:greekLit:tlg0001.tlg001.perseus-grc2:1.247
        #   -> greekLit.tlg0001.tlg001.perseus-grc2.1.247
        if urn.startswith("urn:cts:"):
            urn = urn[len("urn:cts:"):]
        return urn.replace(":", ".")

    edition_div = root.xpath("//tei:div[@type='edition']", namespaces=NS)
    if edition_div:
        for div in edition_div[0].xpath(
            ".//tei:div[@type='textpart']", namespaces=NS
        ):
            if div.get(XML_ID):
                counts["div_skipped"] += 1
                continue
            # Prefer xml:base if present, else compute
            base = div.get(XML_BASE) or _expected_div_base(div, base_urn)
            div.set(XML_ID, urn_to_id(base))
            counts["div_added"] += 1

        for tag in ("l", "p", "ab", "seg"):
            for elem in edition_div[0].xpath(f".//tei:{tag}", namespaces=NS):
                if elem.get(XML_ID):
                    counts["leaf_skipped"] += 1
                    continue
                if not elem.get("n"):
                    continue
                base = elem.get(XML_BASE) or _expected_leaf_base(
                    elem, base_urn, tag
                )
                if not base:
                    continue
                elem.set(XML_ID, urn_to_id(base))
                counts["leaf_added"] += 1

    _write_tree(tree, output_path)

    if verbose:
        print(f"  Phase 3 changes: {counts}")

    return counts


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _write_tree(tree: etree._ElementTree, output_path: Path) -> None:
    """Write the tree to output_path with XML declaration, preserving encoding."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(
        str(output_path),
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=False,   # preserve original whitespace
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="+", type=Path, metavar="FILE")
    p.add_argument(
        "--phase", type=int, choices=[1, 2, 3], default=1,
        help="Phase to run (default: 1)",
    )
    p.add_argument(
        "--fix", action="store_true",
        help="Phase 2/3: write repaired output file(s)",
    )
    p.add_argument(
        "--output", type=Path, metavar="PATH",
        help="Output path (single file only)",
    )
    p.add_argument(
        "--output-dir", type=Path, metavar="DIR",
        help="Output directory for multiple files",
    )
    p.add_argument("--verbose", action="store_true")
    return p


def resolve_output(
    path: Path,
    args: argparse.Namespace,
    index: int,
    total: int,
) -> Path:
    if args.output and total == 1:
        return args.output
    if args.output_dir:
        return args.output_dir / path.name
    # Default: write to same directory with _fixed / _with_ids suffix
    suffix = "_fixed" if args.phase == 2 else "_with_ids"
    return path.with_stem(path.stem + suffix)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.phase in (2, 3) and not args.fix:
        print(
            f"Phase {args.phase} selected but --fix not given; "
            "running in dry-run mode (audit only).",
            file=sys.stderr,
        )

    errors = 0
    for i, path in enumerate(args.files):
        if not path.exists():
            print(f"ERROR: {path} does not exist", file=sys.stderr)
            errors += 1
            continue

        try:
            if args.phase == 1:
                report = phase1_audit(path, verbose=args.verbose)
                print_audit_report(report)

            elif args.phase == 2:
                # Always audit first so the user sees the starting state
                report = phase1_audit(path, verbose=args.verbose)
                print_audit_report(report)
                if args.fix:
                    out = resolve_output(path, args, i, len(args.files))
                    counts = phase2_normalize(path, out, verbose=args.verbose)
                    total = sum(counts.values())
                    print(f"\nPhase 2 complete: {total} changes written to {out}")
                    print(f"  div fixed: {counts['div_fixed']}, "
                          f"div added: {counts['div_added']}, "
                          f"leaf fixed: {counts['leaf_fixed']}, "
                          f"leaf added: {counts['leaf_added']}")

            elif args.phase == 3:
                report = phase1_audit(path, verbose=args.verbose)
                print_audit_report(report)
                if args.fix:
                    # Phase 3 implies Phase 2 has already been run (or we run both)
                    # Run phase 2 into a temp location then phase 3
                    import tempfile
                    with tempfile.NamedTemporaryFile(
                        suffix=".xml", delete=False
                    ) as tmp:
                        tmp_path = Path(tmp.name)
                    counts2 = phase2_normalize(path, tmp_path, verbose=args.verbose)
                    out = resolve_output(path, args, i, len(args.files))
                    counts3 = phase3_add_ids(tmp_path, out, verbose=args.verbose)
                    tmp_path.unlink()
                    print(f"\nPhase 2+3 complete → {out}")
                    print(f"  Phase 2 — div fixed: {counts2['div_fixed']}, "
                          f"div added: {counts2['div_added']}, "
                          f"leaf fixed: {counts2['leaf_fixed']}, "
                          f"leaf added: {counts2['leaf_added']}")
                    print(f"  Phase 3 — div IDs added: {counts3['div_added']}, "
                          f"leaf IDs added: {counts3['leaf_added']}")

        except Exception as exc:
            print(f"ERROR processing {path.name}: {exc}", file=sys.stderr)
            if args.verbose:
                import traceback
                traceback.print_exc()
            errors += 1

    return errors


if __name__ == "__main__":
    sys.exit(main())
