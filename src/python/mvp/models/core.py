# mvp/models/core.py
#
# Core data objects shared across the mvp package.
#
# Plain dataclasses — no significant behavior beyond field access and
# construction.  They carry data between pipeline stages and do not
# implement compilation or transformation logic.
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from mvp.constants import TEI_NS



@dataclass
class TEIMetadata:
    """Descriptive metadata extracted from a TEI document header.

    Carries everything the catalog and build pipeline need to know
    about a document without holding the document tree itself.
    """

    urn: str
    title: str
    author: str
    language: str  # BCP 47 / ISO 639-3: 'grc', 'lat', 'eng', etc.
    text_type: str  # 'verse' | 'prose' | 'drama'
    source_path: Path


@dataclass(frozen=True)
class WordOccurrence:
    xpath: str
    start: int
    end: int
    urn: str | None = None


@dataclass
class WordIndex:
    """Word-location index built from a TEI document body.

    Maps each lowercased word form to the set of XPath locations
    (tei:-prefixed strings) where it appears in the document.
    """

    entries: dict[str, set[WordOccurrence]]


@dataclass(frozen=True)
class ChunkOccurrence:
    xpath: str
    element: str  # tag name of the source element: "l", "p", "lg", "ab"
    chunk: str
    urn: str | None = None


@dataclass
class ChunkIndex:
    """Chunk-location index built from a TEI document body.

    Maps an XPath expression to the contents of the element
    stripped of markup.
    """

    entries: list[ChunkOccurrence] = field(default_factory=list)


@dataclass(frozen=True)
class CitationRecord:
    """One citable location in a TEI document, derived from citeStructure."""

    urn: str
    unit: str
    depth: int


@dataclass
class CitationChunk:
    """A citable chunk of a TEI document at a designated citation level.

    For div-based citeStructures, elements contains a single element (the
    matched div).  For milestone-based citeStructures, elements contains
    the sequence of top-level elements between two consecutive milestones,
    possibly truncated at the boundary (LCA extraction).
    """

    base_urn: str
    cts_urn: str
    unit: str
    elements: list[etree._Element]
    prev_urn: str | None = None
    next_urn: str | None = None

    def to_xml(self) -> etree._Element:
        root = etree.Element("citationChunk", nsmap={"tei": TEI_NS})
        root.set("unit", self.unit)
        root.set("base_urn", self.base_urn)
        root.set("cts_urn", self.cts_urn)
        if self.prev_urn is not None:
            root.set("prev_urn", self.prev_urn)
        if self.next_urn is not None:
            root.set("next_urn", self.next_urn)

        elements = etree.SubElement(root, "elements")
        for e in self.elements:
            elements.append(e)
        return root
