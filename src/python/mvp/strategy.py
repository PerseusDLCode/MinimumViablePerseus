# mvp/strategy.py
#
# ChunkingStrategy and StrategySelector.
#
# A ChunkingStrategy encapsulates the logic for determining how a TEI
# document should be divided into navigable chunks.  Compilers receive
# a strategy as a collaborator; they do not contain chunking logic.
#
# StrategySelector inspects a TEIDocument and returns the appropriate
# strategy using a structural heuristic: <div> elements with subtypes
# are always preferred over milestone elements.  An editorial override
# via <refState n='chunk' unit='...'> in encodingDesc is consulted
# first and returned immediately when present.
#
# TODO (multiple chunking strategies): select() returns a single strategy.
# Perseus 4 supported user-selectable chunking schemes for texts that encode
# multiple valid chunking axes (e.g. Plato's Alcibiades I has both
# milestone unit="page" and milestone unit="section").  select_all() is
# provided as groundwork; a future revision should expose it through the
# UI.  See Open Question 6 in wiki/Roadmap.org and the deferred items in
# wiki/Object-Model.org.
#
# TODO (card-milestone priority): currently divs-with-subtypes always beat
# card milestones.  A future iteration should allow card milestones to win
# for texts like Sophocles that have both.  See #refactor-strategy-selector.

from __future__ import annotations

from abc import ABC, abstractmethod

from mvp.document import TEIDocument

TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}

# Thresholds for the structural heuristic (mean direct-text char length).
# Defined as module constants so they are easy to tune after corpus testing.
MIN_CHUNK_CHARS = 150
MAX_CHUNK_CHARS = 8000

# When a single div type has more than this many distinct subtypes, treat it as
# a flat dramatic structure and chunk at the type level (no subtype filter).
# Aristophanes-style texts have 20+ one-off section labels; prose texts have 1-2.
MAX_SUBTYPES_PER_DIV_TYPE = 5

# Milestone units tried in order when no structural divs with subtypes exist.
_MILESTONE_FALLBACKS = ["card", "section", "line"]


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
    def chunk_strategy(self) -> str:
        """Value of the chunk-strategy parameter passed to driver.xsl."""
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
        return "html/driver.xsl"

    @property
    def chunk_strategy(self) -> str:
        return "milestone"

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
        return "html/driver.xsl"

    @property
    def chunk_strategy(self) -> str:
        return "div"

    def describes(self, doc: TEIDocument) -> bool:
        root = doc.tree.getroot()
        xpath = f".//tei:text//tei:div[@type='{self._div_type}']"
        if self._subtype:
            xpath += f"[@subtype='{self._subtype}']"
        return root.find(xpath, NS) is not None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _editorial_override(doc: TEIDocument) -> str | None:
    """Return the chunk unit declared by <refState n='chunk' unit='...'>, or None."""
    root = doc.tree.getroot()
    el = root.find(".//tei:encodingDesc//tei:refState[@n='chunk']", NS)
    if el is not None:
        return el.get("unit")
    return None


def _direct_text_length(el) -> int:
    """Character count of direct text content of el, excluding descendant <div> text.

    The tail of a child <div> is intentionally excluded: it is formatting
    whitespace, not meaningful text, and counting it inflates the apparent
    size of container divs that have no prose content of their own.
    """
    count = len(el.text or "")
    for child in el:
        tag = child.tag if isinstance(child.tag, str) else ""
        is_div = tag.endswith("}div") or tag == "div"
        if not is_div:
            count += len("".join(child.itertext()))
            count += len(child.tail or "")
    return count


def _is_edition_div(el) -> bool:
    """True if el is the outermost edition/translation div carrying the CTS URN as @n."""
    n = el.get("n", "")
    return n.startswith("urn:cts:")


def _collect_div_candidates(doc: TEIDocument) -> list[tuple[str, str | None, list]]:
    """Return [(div_type, subtype_or_None, [element, ...]), ...] for content divs.

    Skips the outermost div whose @n is a CTS URN.  When a div type has more
    than MAX_SUBTYPES_PER_DIV_TYPE distinct subtype values (flat drama structure,
    e.g. Aristophanes), all elements for that type are collapsed into a single
    candidate with subtype=None so the XSLT chunks at the type level.

    Result is sorted with subtype-bearing candidates first.
    """
    root = doc.tree.getroot()

    # First pass: group by (div_type, subtype).
    by_pair: dict[tuple[str, str | None], list] = {}
    for div in root.findall(".//tei:text//tei:div", NS):
        if _is_edition_div(div):
            continue
        div_type = div.get("type", "")
        if not div_type:
            continue
        subtype: str | None = div.get("subtype") or None
        by_pair.setdefault((div_type, subtype), []).append(div)

    # Second pass: group by div_type to detect flat drama structure.
    by_type: dict[str, dict[str | None, list]] = {}
    for (dt, st), els in by_pair.items():
        by_type.setdefault(dt, {})[st] = els

    result: list[tuple[str, str | None, list]] = []
    for div_type, subtype_map in by_type.items():
        distinct = [st for st in subtype_map if st is not None]
        if len(distinct) > MAX_SUBTYPES_PER_DIV_TYPE:
            # Flat structure: collapse all elements to type-level chunking.
            all_els = [el for els in subtype_map.values() for el in els]
            result.append((div_type, None, all_els))
        else:
            for subtype, els in subtype_map.items():
                result.append((div_type, subtype, els))

    result.sort(key=lambda g: (g[1] is None,))
    return result


def _div_depth(doc: TEIDocument, div_type: str, subtype: str | None) -> int:
    """Return the maximum absolute div-nesting depth at which a matching element appears.

    Depth counts every ancestor <div> from tei:text downward, so a div nested
    inside two other divs has depth 3 regardless of whether those ancestors
    match the target.  When subtype is None, matches any <div type=div_type>.

    This absolute measure lets the selector prefer 'chapter' (depth 3) over
    'book' (depth 2) when the two are actually nested, even if 'book' also
    passes the size filter.
    """
    root = doc.tree.getroot()
    text_el = root.find("tei:text", NS)
    if text_el is None:
        return 0

    max_depth: list[int] = [0]

    def walk(el: object, div_depth: int = 0) -> None:
        for child in el:  # type: ignore[union-attr]
            tag = child.tag if isinstance(child.tag, str) else ""
            is_div = tag.endswith("}div") or tag == "div"
            child_depth = div_depth + 1 if is_div else div_depth
            if is_div:
                child_type = child.get("type", "")
                child_sub = child.get("subtype") or None
                matches = child_type == div_type and (
                    subtype is None or child_sub == subtype
                )
                if matches:
                    max_depth[0] = max(max_depth[0], child_depth)
            walk(child, child_depth)

    walk(text_el)
    return max_depth[0]


class StrategySelector:
    """Selects a ChunkingStrategy for a TEIDocument.

    Selection order:
    1. Editorial override: <refState n='chunk' unit='...'> in encodingDesc.
    2. Structural heuristic: prefer <div> elements with subtypes, choosing
       the deepest level whose mean direct-text length falls within
       [MIN_CHUNK_CHARS, MAX_CHUNK_CHARS].  If all candidates are filtered
       out, fall back to the deepest regardless.
    3. Milestone fallback: tried only when no divs with subtypes exist at all.
    4. Hard fallback: raises ValueError.
    """

    def select(self, doc: TEIDocument) -> ChunkingStrategy:
        """Return the best strategy for doc.

        Raises:
            ValueError: If no implemented strategy matches.
        """
        # 1. Editorial override
        hint = _editorial_override(doc)
        if hint:
            for candidate in [
                MilestoneStrategy(unit=hint),
                DivisionStrategy(div_type="textpart", subtype=hint),
                DivisionStrategy(div_type=hint),
            ]:
                if candidate.describes(doc):
                    return candidate

        # 2. Structural heuristic — wins over milestones when any content divs exist.
        groups = _collect_div_candidates(doc)
        if groups:
            strategy = self._pick_div_strategy(doc, groups)
            if strategy is not None:
                return strategy

        # 3. Milestone fallback — only when no content divs were found at all.
        for unit in _MILESTONE_FALLBACKS:
            ms = MilestoneStrategy(unit=unit)
            if ms.describes(doc):
                return ms

        raise ValueError(
            f"No chunking strategy found for {doc.path} "
            f"(URN: {doc.metadata.urn})"
        )

    def select_all(self, doc: TEIDocument) -> list[ChunkingStrategy]:
        """Return all applicable strategies, ranked by specificity.

        Does not raise; returns an empty list if nothing matches.
        """
        results: list[ChunkingStrategy] = []

        hint = _editorial_override(doc)
        if hint:
            for candidate in [
                MilestoneStrategy(unit=hint),
                DivisionStrategy(div_type="textpart", subtype=hint),
                DivisionStrategy(div_type=hint),
            ]:
                if candidate.describes(doc) and candidate not in results:
                    results.append(candidate)

        groups = _collect_div_candidates(doc)
        ranked = sorted(
            groups,
            key=lambda g: (g[1] is None, -_div_depth(doc, g[0], g[1])),
        )
        for div_type, subtype, _ in ranked:
            s = DivisionStrategy(div_type=div_type, subtype=subtype)
            if s not in results:
                results.append(s)

        for unit in _MILESTONE_FALLBACKS:
            ms = MilestoneStrategy(unit=unit)
            if ms.describes(doc) and ms not in results:
                results.append(ms)

        return results

    # ------------------------------------------------------------------
    # Private

    def _pick_div_strategy(
        self,
        doc: TEIDocument,
        groups: list[tuple[str, str | None, list]],
    ) -> ChunkingStrategy | None:
        """Choose the best DivisionStrategy from the candidate groups.

        Applies the size filter and returns the deepest surviving candidate.

        - If some candidates pass [MIN, MAX]: pick the deepest.
        - If all fail because they are too small: fall back to deepest
          too-small rather than raising (better than nothing for short texts).
        - If the only failures are too large: return None so that the milestone
          fallback in select() can handle the document (a single enormous div
          is not a useful chunk boundary).
        """
        def mean_length(els) -> float:
            if not els:
                return 0.0
            return sum(_direct_text_length(e) for e in els) / len(els)

        # Prefer subtype-bearing candidates; only consider no-subtype groups if
        # there are no subtype groups at all.
        subtype_groups = [(dt, st, els) for dt, st, els in groups if st is not None]
        pool = subtype_groups if subtype_groups else groups

        passing = [
            (dt, st, els) for dt, st, els in pool
            if MIN_CHUNK_CHARS <= mean_length(els) <= MAX_CHUNK_CHARS
        ]
        if passing:
            best = max(passing, key=lambda g: _div_depth(doc, g[0], g[1]))
            return DivisionStrategy(div_type=best[0], subtype=best[1])

        too_small = [
            (dt, st, els) for dt, st, els in pool
            if mean_length(els) < MIN_CHUNK_CHARS
        ]
        if too_small:
            best = max(too_small, key=lambda g: _div_depth(doc, g[0], g[1]))
            return DivisionStrategy(div_type=best[0], subtype=best[1])

        # Only too-large candidates — let milestone fallback try.
        return None
