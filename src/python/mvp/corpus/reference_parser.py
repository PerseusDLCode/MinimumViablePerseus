from __future__ import annotations

from collections.abc import Iterator
from typing import Optional

from lxml import etree

from mvp.corpus.chunking import elements_between
from mvp.corpus.models import CitationChunk, CitationRecord
from mvp.corpus.tei_document import LenientTEIDocument, NS, XML_BASE, XML_ID


class ConfigurationError(Exception):
    """Raised when no usable citeStructure can be found or selected."""


class CitationError(Exception):
    """Raised when a URN is syntactically invalid or resolves to nothing."""


class ReferenceParser:
    def __init__(
        self,
        tei_doc: LenientTEIDocument,
        refsDecl_id: str | None = None,
    ) -> None:
        root = tei_doc.root

        body = root.find(".//tei:body", NS)
        if body is None:
            raise ConfigurationError("No <body> element found in document")
        self._body = body

        self._base_urn = body.get(XML_BASE, "")
        if not self._base_urn:
            raise ConfigurationError(
                "No base URN found in <body @xml:base>. "
                "Ensure the document encodes the CTS URN as xml:base on <body>."
            )

        refs_decls = root.findall(".//tei:refsDecl", NS)

        if refsDecl_id is not None:
            target = next(
                (rd for rd in refs_decls if rd.get(XML_ID) == refsDecl_id),
                None,
            )
            if target is None:
                raise ConfigurationError(
                    f"No <refsDecl> with xml:id={refsDecl_id!r}"
                )
            cs = target.find("tei:citeStructure", NS)
            if cs is None:
                raise ConfigurationError(
                    f"<refsDecl xml:id={refsDecl_id!r}> contains no <citeStructure>"
                )
            self._root_cs = cs
        else:
            cs_decls = [
                (rd, rd.find("tei:citeStructure", NS))
                for rd in refs_decls
            ]
            cs_decls = [(rd, cs) for rd, cs in cs_decls if cs is not None]

            if not cs_decls:
                raise ConfigurationError(
                    "No <refsDecl> with a <citeStructure> found. "
                    "Run conversion tooling to add <citeStructure> declarations first."
                )

            defaults = [
                (rd, cs) for rd, cs in cs_decls if rd.get("default") == "true"
            ]
            if defaults:
                self._root_cs = defaults[0][1]
            elif len(cs_decls) == 1:
                self._root_cs = cs_decls[0][1]
            else:
                raise ConfigurationError(
                    "Multiple <refsDecl> elements contain <citeStructure>; "
                    "supply refsDecl_id to select one explicitly."
                )

    def resolve(self, urn: str) -> etree._Element:
        """Return the element identified by the full CTS URN.

        Partial citations (e.g. book only when book/chapter/section is the full
        hierarchy) are valid and resolve to the element at that level.
        Raises CitationError if the URN is malformed or matches nothing.
        """
        prefix = self._base_urn + ":"
        if not urn.startswith(prefix):
            raise CitationError(
                f"URN base does not match document. "
                f"Expected prefix {prefix!r}, got {urn!r}"
            )
        passage = urn[len(prefix):]
        if not passage:
            raise CitationError(f"URN has no passage component: {urn!r}")

        # The root <citeStructure> is an anchor only: its @match binds <body>
        # as context and its @use provides the base URN. It is not itself a
        # citation level, so resolution begins with its children.
        children = list(self._root_cs.findall("tei:citeStructure", NS))
        if not children:
            raise CitationError("Root <citeStructure> has no children to resolve against")

        return self._resolve_passage(passage, children, self._body)

    def _resolve_passage(
        self,
        passage: str,
        cs_list: list[etree._Element],
        context: etree._Element,
    ) -> etree._Element:
        last_error: CitationError = CitationError(f"Cannot resolve passage {passage!r}")
        for cs in cs_list:
            try:
                return self._resolve_with_cs(passage, cs, context)
            except CitationError as exc:
                last_error = exc
        raise last_error

    def _resolve_with_cs(
        self,
        passage: str,
        cs: etree._Element,
        context: etree._Element,
    ) -> etree._Element:
        children = list(cs.findall("tei:citeStructure", NS))

        if children:
            next_delim = children[0].get("delim", ".")
            token, sep, rest = passage.partition(next_delim)
            if not sep:
                # Delimiter not found — partial citation stopping at this level.
                token = passage
                rest = ""
        else:
            token = passage
            rest = ""

        match_expr = cs.get("match", "")
        use_attr = cs.get("use", "@n")
        candidates: list[etree._Element] = context.xpath(match_expr, namespaces=NS)

        matched: Optional[etree._Element] = None
        if use_attr.startswith("@"):
            attr_name = use_attr[1:]
            for cand in candidates:
                if cand.get(attr_name) == token:
                    matched = cand
                    break

        if matched is None:
            raise CitationError(
                f"No element with {use_attr}={token!r} "
                f"via match={match_expr!r}"
            )

        if rest:
            if not children:
                raise CitationError(
                    f"Passage has trailing component {rest!r} "
                    f"but citation hierarchy is exhausted"
                )
            return self._resolve_passage(rest, children, matched)
        return matched

    def generate(self, element: etree._Element) -> str:
        """Return the full CTS URN for a citable element.

        Raises CitationError if the element is not reachable from any
        level of the active citeStructure.
        """
        path = self._find_path_to(element, self._root_cs, self._body)
        if path is None:
            raise CitationError(
                f"Element <{etree.QName(element.tag).localname}> "
                f"is not reachable via the active citeStructure"
            )
        parts: list[str] = []
        for cs, elem in path:
            delim = cs.get("delim")
            if delim is None:
                raise ConfigurationError(
                    f"<citeStructure unit={cs.get('unit')!r}> is missing required @delim"
                )
            use_attr = cs.get("use", "@n")
            val = elem.get(use_attr[1:], "") if use_attr.startswith("@") else ""
            parts.append(delim + val)
        return self._base_urn + "".join(parts)

    def _find_path_to(
        self,
        target: etree._Element,
        parent_cs: etree._Element,
        context: etree._Element,
    ) -> Optional[list[tuple[etree._Element, etree._Element]]]:
        # The root <citeStructure>'s @match is never evaluated here: the caller
        # passes self._body as context and self._root_cs as parent_cs, so we
        # begin immediately at the root's children (the real citation levels).
        for cs in parent_cs.findall("tei:citeStructure", NS):
            match_expr = cs.get("match", "")
            candidates: list[etree._Element] = context.xpath(match_expr, namespaces=NS)

            if any(cand is target for cand in candidates):
                return [(cs, target)]

            for cand in candidates:
                result = self._find_path_to(target, cs, cand)
                if result is not None:
                    return [(cs, cand)] + result

        return None

    @property
    def base_urn(self) -> str:
        return self._base_urn

    def citation_records(self, depth: int = -1) -> Iterator[CitationRecord]:
        """Like citations() but yields CitationRecord objects carrying unit and depth."""
        children = list(self._root_cs.findall("tei:citeStructure", NS))
        yield from self._records_recursive("", children, self._body, 0, depth)

    def _records_recursive(
        self,
        suffix: str,
        cs_list: list[etree._Element],
        context: etree._Element,
        current_depth: int,
        max_depth: int,
    ) -> Iterator[CitationRecord]:
        for cs in cs_list:
            match_expr = cs.get("match", "")
            use_attr = cs.get("use", "@n")
            delim = cs.get("delim", ":")
            unit = cs.get("unit", "")
            children = list(cs.findall("tei:citeStructure", NS))
            candidates: list[etree._Element] = context.xpath(match_expr, namespaces=NS)

            for cand in candidates:
                val = cand.get(use_attr[1:], "") if use_attr.startswith("@") else ""
                new_suffix = suffix + delim + val

                if max_depth == -1 or current_depth <= max_depth:
                    yield CitationRecord(
                        urn=self._base_urn + new_suffix,
                        unit=unit,
                        depth=current_depth,
                    )

                if (max_depth == -1 or current_depth < max_depth) and children:
                    yield from self._records_recursive(
                        new_suffix, children, cand, current_depth + 1, max_depth
                    )

    def citations(self, depth: int = -1) -> Iterator[str]:
        """Yield every resolvable CTS URN in document order.

        depth=-1 (default): yield citations at every level of the hierarchy.
        depth=0: yield only root-level citations.
        depth=N (positive): yield citations up to and including level N (0-based).
        """
        children = list(self._root_cs.findall("tei:citeStructure", NS))
        yield from (r.urn for r in self._records_recursive("", children, self._body, 0, depth))

    # ------------------------------------------------------------------
    # chunks() — public API for compilation
    # ------------------------------------------------------------------

    def chunks(self) -> Iterator[CitationChunk]:
        """Yield CitationChunk objects at the designated chunking level.

        The chunking level is determined by the first <citeStructure> bearing
        @n="chunk".  If none is found, the penultimate citation level is used
        (one level above the finest granularity); for a single-level hierarchy
        the sole level is used.

        Div-based citeStructures (match does not reference "milestone") yield
        one-element chunks.  Milestone-based citeStructures yield multi-element
        chunks assembled by LCA extraction.
        """
        target_cs = self._find_chunk_cs()
        match_expr = target_cs.get("match", "")
        if "milestone" in match_expr:
            yield from self._milestone_chunks(target_cs)
        else:
            yield from self._div_chunks(target_cs)

    def _find_chunk_cs(self) -> etree._Element:
        """Return the citeStructure that defines chunk boundaries."""
        found = self._find_cs_with_attr(self._root_cs, "n", "chunk")
        if found is not None:
            return found
        return self._penultimate_cs()

    def _find_cs_with_attr(
        self,
        parent_cs: etree._Element,
        attr: str,
        value: str,
    ) -> Optional[etree._Element]:
        for cs in parent_cs.findall("tei:citeStructure", NS):
            if cs.get(attr) == value:
                return cs
            found = self._find_cs_with_attr(cs, attr, value)
            if found is not None:
                return found
        return None

    def _penultimate_cs(self) -> etree._Element:
        """Return the second-to-deepest citeStructure (first-branch traversal).

        For a single-level hierarchy returns that sole level.
        """
        path: list[etree._Element] = []
        cs = self._root_cs
        while True:
            children = cs.findall("tei:citeStructure", NS)
            if not children:
                break
            cs = children[0]
            path.append(cs)
        if not path:
            return self._root_cs
        if len(path) == 1:
            return path[0]
        return path[-2]

    def _div_chunks(self, target_cs: etree._Element) -> Iterator[CitationChunk]:
        unit = target_cs.get("unit", "")
        pairs = self._candidates_at_level(target_cs)
        for i, (elem, urn) in enumerate(pairs):
            yield CitationChunk(
                cts_urn=urn,
                unit=unit,
                elements=[elem],
                prev_urn=pairs[i - 1][1] if i > 0 else None,
                next_urn=pairs[i + 1][1] if i + 1 < len(pairs) else None,
            )

    def _milestone_chunks(self, target_cs: etree._Element) -> Iterator[CitationChunk]:
        match_expr = target_cs.get("match", "")
        use_attr = target_cs.get("use", "@n")
        unit = target_cs.get("unit", "")
        delim = target_cs.get("delim", " ")

        milestones: list[etree._Element] = self._body.xpath(match_expr, namespaces=NS)

        def _urn(ms: etree._Element) -> str:
            val = ms.get(use_attr[1:], "") if use_attr.startswith("@") else ""
            return self._base_urn + delim + val

        for i, ms in enumerate(milestones):
            ms_next = milestones[i + 1] if i + 1 < len(milestones) else None
            yield CitationChunk(
                cts_urn=_urn(ms),
                unit=unit,
                elements=elements_between(self._body, ms, ms_next),
                prev_urn=_urn(milestones[i - 1]) if i > 0 else None,
                next_urn=_urn(ms_next) if ms_next is not None else None,
            )

    def _candidates_at_level(
        self,
        target_cs: etree._Element,
    ) -> list[tuple[etree._Element, str]]:
        """Return all (element, urn) pairs at the given citeStructure level."""
        result: list[tuple[etree._Element, str]] = []
        self._collect_cs_elements(
            "",
            list(self._root_cs.findall("tei:citeStructure", NS)),
            self._body,
            target_cs,
            result,
        )
        return result

    def _collect_cs_elements(
        self,
        suffix: str,
        cs_list: list[etree._Element],
        context: etree._Element,
        target_cs: etree._Element,
        result: list[tuple[etree._Element, str]],
    ) -> None:
        for cs in cs_list:
            match_expr = cs.get("match", "")
            use_attr = cs.get("use", "@n")
            delim = cs.get("delim", ":")
            children = list(cs.findall("tei:citeStructure", NS))
            candidates: list[etree._Element] = context.xpath(match_expr, namespaces=NS)

            for cand in candidates:
                val = cand.get(use_attr[1:], "") if use_attr.startswith("@") else ""
                new_suffix = suffix + delim + val
                if cs is target_cs:
                    result.append((cand, self._base_urn + new_suffix))
                elif children:
                    self._collect_cs_elements(new_suffix, children, cand, target_cs, result)
