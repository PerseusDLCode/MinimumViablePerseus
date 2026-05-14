from __future__ import annotations

from pathlib import Path

from lxml import etree

from mvp.tei_document import (
    NS,
    XML_BASE,
    XML_ID,
    TEIDocument,
    expected_div_base,
    expected_leaf_base,
)


def _write_tree(tree: etree._ElementTree, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(
        str(output_path),
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=False,
    )


def phase2_normalize(
    path: Path, output_path: Path, verbose: bool = False
) -> dict[str, int]:
    """Repair xml:base on all citable elements. Returns a dict of change counts."""
    doc = TEIDocument(path)
    base_urn = doc.extract_base_urn()
    if not base_urn:
        raise ValueError(f"Cannot normalize {path.name}: no base URN found")

    counts = {"div_fixed": 0, "div_added": 0, "leaf_fixed": 0, "leaf_added": 0}

    edition_div = doc.root.xpath("//tei:div[@type='edition']", namespaces=NS)
    if edition_div:
        for div in edition_div[0].xpath(
            ".//tei:div[@type='textpart']", namespaces=NS
        ):
            expected = expected_div_base(div, base_urn)
            actual = div.get(XML_BASE)
            if actual is None:
                div.set(XML_BASE, expected)
                counts["div_added"] += 1
            elif actual != expected:
                div.set(XML_BASE, expected)
                counts["div_fixed"] += 1

        for tag in ("l", "p", "ab", "seg"):
            for elem in edition_div[0].xpath(f".//tei:{tag}", namespaces=NS):
                if not elem.get("n"):
                    continue
                expected = expected_leaf_base(elem, base_urn)
                if expected is None:
                    continue
                actual = elem.get(XML_BASE)
                if actual is None:
                    elem.set(XML_BASE, expected)
                    counts["leaf_added"] += 1
                elif actual != expected:
                    elem.set(XML_BASE, expected)
                    counts["leaf_fixed"] += 1

    _write_tree(doc.tree, output_path)

    if verbose:
        print(f"  Phase 2 changes: {counts}")

    return counts


def phase3_add_ids(
    path: Path, output_path: Path, verbose: bool = False
) -> dict[str, int]:
    """Add xml:id to all citable elements derived from (corrected) xml:base."""
    doc = TEIDocument(path)
    base_urn = doc.extract_base_urn()
    if not base_urn:
        raise ValueError(f"Cannot add IDs to {path.name}: no base URN found")

    counts = {
        "div_added": 0, "div_skipped": 0,
        "leaf_added": 0, "leaf_skipped": 0,
    }

    def urn_to_id(urn: str) -> str:
        if urn.startswith("urn:cts:"):
            urn = urn[len("urn:cts:"):]
        return urn.replace(":", ".")

    edition_div = doc.root.xpath("//tei:div[@type='edition']", namespaces=NS)
    if edition_div:
        for div in edition_div[0].xpath(
            ".//tei:div[@type='textpart']", namespaces=NS
        ):
            if div.get(XML_ID):
                counts["div_skipped"] += 1
                continue
            base = div.get(XML_BASE) or expected_div_base(div, base_urn)
            div.set(XML_ID, urn_to_id(base))
            counts["div_added"] += 1

        for tag in ("l", "p", "ab", "seg"):
            for elem in edition_div[0].xpath(f".//tei:{tag}", namespaces=NS):
                if elem.get(XML_ID):
                    counts["leaf_skipped"] += 1
                    continue
                if not elem.get("n"):
                    continue
                base = elem.get(XML_BASE) or expected_leaf_base(elem, base_urn)
                if not base:
                    continue
                elem.set(XML_ID, urn_to_id(base))
                counts["leaf_added"] += 1

    _write_tree(doc.tree, output_path)

    if verbose:
        print(f"  Phase 3 changes: {counts}")

    return counts
