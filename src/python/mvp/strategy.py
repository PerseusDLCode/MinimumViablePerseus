# mvp/strategy.py
#
# ChunkingStrategy and StrategySelector.
#
# A ChunkingStrategy encapsulates the logic for determining how a TEI
# document should be divided into navigable chunks.  Compilers receive
# a strategy as a collaborator; they do not contain chunking logic.
#
# StrategySelector inspects a TEIDocument and returns the appropriate
# strategy.  It reads refsDecl as a hint but also inspects the actual
# document structure, since encoding inconsistencies in the Perseus
# corpus mean that refsDecl cannot always be trusted.
#
# TODO (multiple chunking strategies): StrategySelector.select() currently
# returns a single strategy — the first match in _STRATEGIES.  Perseus 4
# supported user-selectable chunking schemes for texts that encode multiple
# valid chunking axes (e.g. Plato's Alcibiades I has both milestone unit="page"
# and milestone unit="section").  A future revision should introduce a
# select_all() method (or replace select()) that returns all applicable
# strategies for a document.  See Open Question 6 in wiki/Roadmap.org and
# the deferred items in wiki/Object-Model.org.

from __future__ import annotations

from abc import ABC, abstractmethod

from mvp.document import TEIDocument

TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}


class ChunkingStrategy(ABC):
    """Abstract base for document segmentation strategies."""

    @abstractmethod
    def describes(self, doc: TEIDocument) -> bool:
        """Return True if this strategy is applicable to doc."""
        ...

    @property
    @abstractmethod
    def xslt_stylesheet(self) -> str:
        """Filename of the XSLT stylesheet that implements this strategy."""
        ...

    @property
    @abstractmethod
    def chunk_unit(self) -> str:
        """The unit value passed to the XSLT stylesheet."""
        ...


class MilestoneStrategy(ChunkingStrategy):
    """Chunk at <milestone unit='{unit}'/> elements.

    Applies to texts that use TEI milestone elements to mark
    page or section boundaries that cut across the element hierarchy.
    This is the most common case in the Perseus corpus.
    """

    def __init__(self, unit: str = "card") -> None:
        self._unit = unit

    @property
    def chunk_unit(self) -> str:
        return self._unit

    @property
    def xslt_stylesheet(self) -> str:
        return "html/generate_chunks.xsl"

    def describes(self, doc: TEIDocument) -> bool:
        root = doc.tree.getroot()
        ms = root.find(f".//tei:text//tei:milestone[@unit='{self._unit}']", NS)
        return ms is not None


class DivisionStrategy(ChunkingStrategy):
    """Chunk at <div type='{div_type}'> elements.

    Applies to texts structured as nested divisions rather than
    milestone-delimited sections.  Optionally filters by @subtype so that
    e.g. DivisionStrategy('textpart', subtype='chapter') matches only
    chapter-level divs within a textpart hierarchy.
    """

    def __init__(self, div_type: str = "textpart",
                 subtype: str | None = None) -> None:
        self._div_type = div_type
        self._subtype = subtype

    @property
    def chunk_unit(self) -> str:
        return self._subtype if self._subtype else self._div_type

    @property
    def xslt_stylesheet(self) -> str:
        return "html/generate_div_chunks.xsl"

    def describes(self, doc: TEIDocument) -> bool:
        root = doc.tree.getroot()
        xpath = f".//tei:text//tei:div[@type='{self._div_type}']"
        if self._subtype:
            xpath += f"[@subtype='{self._subtype}']"
        return root.find(xpath, NS) is not None


class StrategySelector:
    """Selects a ChunkingStrategy for a TEIDocument.

    Inspects the document structure to determine the appropriate
    strategy.  The order of preference reflects the current state
    of the corpus: milestone-based chunking is the common case.

    Per-document overrides are not yet implemented.  When they are,
    a configuration file mapping URNs to strategy names would be
    consulted first.

    TODO (multiple chunking strategies): select() returns the first
    matching strategy.  For documents with multiple valid chunking axes,
    a select_all() method should be added.  See module docstring above.
    """

    # Strategies tried in order; first match wins.
    # TODO (multiple chunking strategies): when select_all() is introduced,
    # this list should be exhaustively searched rather than short-circuited.
    _STRATEGIES: list[ChunkingStrategy] = [
        MilestoneStrategy(unit="card"),
        MilestoneStrategy(unit="section"),
        MilestoneStrategy(unit="line"),
        DivisionStrategy(div_type="textpart"),
        DivisionStrategy(div_type="book"),
    ]

    def select(self, doc: TEIDocument) -> ChunkingStrategy:
        """Return the best strategy for doc.

        Consults <refState n='chunk'> in the TEI header first; if a hint is
        present, candidate strategies matching that unit are tried before
        falling back to the ordered _STRATEGIES list.  Strategies whose
        xslt_stylesheet raises NotImplementedError are silently skipped.

        Raises:
            ValueError: If no implemented strategy matches.
        """
        hint = doc.chunk_hint()
        candidates: list[ChunkingStrategy] = []
        if hint:
            candidates = [
                MilestoneStrategy(unit=hint),
                DivisionStrategy(div_type="textpart", subtype=hint),
                DivisionStrategy(div_type=hint),
            ]
        for strategy in candidates + list(self._STRATEGIES):
            if strategy.describes(doc):
                try:
                    _ = strategy.xslt_stylesheet
                    return strategy
                except NotImplementedError:
                    continue
        raise ValueError(
            f"No chunking strategy found for {doc.path} "
            f"(URN: {doc.metadata.urn})"
        )
