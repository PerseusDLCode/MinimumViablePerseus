from __future__ import annotations

from pathlib import Path
from typing import Optional

from lxml import etree

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI_NS, "xml": XML_NS}

XML_BASE = f"{{{XML_NS}}}base"
XML_ID = f"{{{XML_NS}}}id"
XML_LANG = f"{{{XML_NS}}}lang"


def _expected_div_base(div: etree._Element, base_urn: str) -> str:
    """Compute the correct xml:base for a textpart div by walking its ancestor chain."""
    chain: list[str] = []
    node: Optional[etree._Element] = div
    while node is not None:
        t = node.get("type", "")
        if t == "textpart":
            chain.append(node.get("n", "?"))
        elif t == "edition":
            break
        node = node.getparent()
    chain.reverse()
    if not chain:
        return base_urn
    return f"{base_urn}:{'.'.join(chain)}"


def _expected_leaf_base(
    elem: etree._Element, base_urn: str
) -> Optional[str]:
    """Compute the correct xml:base for a leaf element (l, p, ab, seg).

    Returns None when the element has no @n.
    """
    n = elem.get("n")
    if not n:
        return None
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


class TEIDocument:
    """Thin wrapper around a parsed TEI lxml tree for the citation pipeline.

    Uses recover=True to tolerate the malformed XML present in the corpus.
    This class is distinct from mvp.document.TEIDocument, which serves the
    compilation pipeline and uses a strict parser.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        parser = etree.XMLParser(recover=True, remove_comments=False)
        self._tree: etree._ElementTree = etree.parse(str(self._path), parser)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def root(self) -> etree._Element:
        return self._tree.getroot()

    @property
    def tree(self) -> etree._ElementTree:
        return self._tree

    def extract_base_urn(self) -> str:
        """Return the CTS work/version URN from the edition div's @n attribute."""
        edition_divs = self.root.xpath(
            "//tei:div[@type='edition']", namespaces=NS
        )
        if not edition_divs:
            return ""
        ed = edition_divs[0]
        urn = ed.get("n", "") or ed.get(XML_BASE, "")
        return urn.rstrip(":")

    def parse_cref_patterns(self) -> list[str]:
        """Return cRefPattern @n values from the CTS refsDecl, deepest first."""
        return list(
            self.root.xpath(
                "//tei:refsDecl[@n='CTS']/tei:cRefPattern/@n",
                namespaces=NS,
            )
        )
