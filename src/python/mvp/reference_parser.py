from __future__ import annotations

from collections.abc import Iterator
from typing import Optional

from lxml import etree

from mvp.models import CitationRecord
from mvp.tei_document import LenientTEIDocument, NS, XML_BASE, XML_ID


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
