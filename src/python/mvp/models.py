# mvp/models.py
#
# Core data objects for the Perseus6 build pipeline.
#
# These are plain dataclasses: no significant behavior beyond field
# access and construction.  They carry data between pipeline stages;
# they do not implement compilation or transformation logic.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TEIMetadata:
    """Descriptive metadata extracted from a TEI document header.

    Carries everything the catalog and build pipeline need to know
    about a document without holding the document tree itself.
    """
    urn: str
    title: str
    author: str
    language: str       # BCP 47 / ISO 639-3: 'grc', 'lat', 'eng', etc.
    text_type: str      # 'verse' | 'prose' | 'drama'
    source_path: Path



@dataclass(frozen=True)
class WordOccurrence:
    xpath: str
    start: int
    end: int

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
    chunk: str


@dataclass
class ChunkIndex:
    """Chunk-location index built from a TEI document body.

    Maps an XPath expression to the contents of the element
    stripped of markup.
    """
    entries: list[ChunkOccurrence] = field(default_factory=list)


@dataclass
class WordIndex:
    """Word-location index built from a TEI document body.

    Maps each lowercased word form to the set of XPath locations
    (tei:-prefixed strings) where it appears in the document.
    """
    entries: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class ChunkManifestEntry:
    """A single entry in a chunk manifest: one compiled HTML page.

    Corresponds to one entry in the index.json produced by the
    XSLT chunking pipeline.
    """
    n: str              # chunk identifier (milestone/@n or div/@n)
    file: str           # relative path of the compiled HTML file
    urn: str            # full CTS URN range for this chunk


@dataclass(frozen=True)
class CitationRecord:
    """One citable location in a TEI document, derived from citeStructure."""
    urn: str
    unit: str
    depth: int


@dataclass
class ChunkManifest:
    """The full manifest for a compiled document.

    Python representation of the index.json file produced by the
    XSLT chunking pipeline.  Not passed between pipeline stages in
    memory; each stage that needs it deserializes it from disk.
    """
    base_urn: str
    title: str
    chunks: list[ChunkManifestEntry] = field(default_factory=list)
