"""Proof-of-concept: Python recursive descent TEI → Protopage XML compiler.

This module is a sketchpad for the new Python-based pipeline that replaces
generate_protopages.xsl.  Once validated against Thucydides it will be
promoted and the XSLT-based ProtopageCompiler retired.

Architecture
------------
SchemaRegistry
    Associates a TEI schema key (derived from the document's xml-model PI)
    with a concrete Transformer subclass.

Transformer (base)
    Holds a registry of (matcher, handler) pairs.  apply(element) finds the
    best-matching handler and calls it, returning a list of output elements.
    Subclasses call self.register() in __init__ to populate their rule set;
    later registrations take priority (checked first), so subclasses can
    override base-class rules.

Family1ProseTransformer(Transformer)
    Concrete rule set matching the current generate_protopages.xsl content-
    mode templates for Family-1 (hierarchical-div) prose texts.

ProtopageCompiler
    Wires everything together: uses ReferenceParser.chunks() to enumerate
    CitationChunk objects, TransformerFactory to select the right Transformer,
    and compile_chunk() to produce ProtopageChunk XML.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from lxml import etree

from mvp.corpus.models import CitationChunk
from mvp.corpus.reference_parser import ReferenceParser
from mvp.corpus.tei_document import LenientTEIDocument
from mvp.site.compilers.base import Compiler

TEI_NS = "http://www.tei-c.org/ns/1.0"


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class ProtopageChunk:
    """Protopage XML output for one citation chunk."""
    content: etree._Element


# ---------------------------------------------------------------------------
# Transformer base class
# ---------------------------------------------------------------------------

# A handler receives (transformer, element) and returns a list of output
# elements.  Returning [] suppresses the element.
Handler = Callable[["Transformer", etree._Element], list[etree._Element]]
Matcher = Callable[[etree._Element], bool]


def _localname(element: etree._Element) -> str:
    return etree.QName(element.tag).localname


def _tag_matcher(localname: str) -> Matcher:
    return lambda el: _localname(el) == localname


def _tag_attr_matcher(localname: str, attr: str, value: str) -> Matcher:
    return lambda el: _localname(el) == localname and el.get(attr) == value


class Transformer:
    """Base class for TEI → Protopage element transformers.

    Subclasses register handlers in __init__.  Each handler is a callable
    (transformer, element) -> list[etree._Element].  The first registered
    handler whose matcher returns True is used; register() prepends, so the
    last call to register() wins.
    """

    def __init__(self, tei_doc: LenientTEIDocument) -> None:
        self.tei_doc = tei_doc
        self._handlers: list[tuple[Matcher, Handler]] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the built-in catch-all: descend without wrapping."""
        self._handlers.append((lambda el: True, Transformer._descend))

    def register(self, matcher: Matcher | str, handler: Handler) -> None:
        """Prepend a (matcher, handler) pair.

        matcher may be a tag-localname string as shorthand for a tag matcher.
        """
        if isinstance(matcher, str):
            matcher = _tag_matcher(matcher)
        self._handlers.insert(0, (matcher, handler))

    def apply(self, element: etree._Element) -> list[etree._Element]:
        """Dispatch element to its handler; return list of output elements."""
        for matcher, handler in self._handlers:
            if matcher(element):
                return handler(self, element)
        return []   # unreachable: default catch-all always matches

    def apply_all(self, elements: list[etree._Element]) -> list[etree._Element]:
        """Apply to every element in the list, flattening results."""
        out: list[etree._Element] = []
        for el in elements:
            out.extend(self.apply(el))
        return out

    @staticmethod
    def _descend(t: Transformer, element: etree._Element) -> list[etree._Element]:
        """Default handler: recurse into children, no wrapper element."""
        return t.apply_all(list(element))

    @staticmethod
    def _suppress(_t: Transformer, _el: etree._Element) -> list[etree._Element]:
        return []

    # ------------------------------------------------------------------
    # Helpers available to subclass handlers
    # ------------------------------------------------------------------

    @staticmethod
    def _copy_inline(
        t: Transformer,
        element: etree._Element,
        out_tag: str,
        copy_attrs: list[str] | None = None,
    ) -> list[etree._Element]:
        """Wrap element's children (recursively transformed) in out_tag.

        Preserves element.text directly; tail text is handled by the caller
        via _rescue_tail.
        """
        out = etree.Element(out_tag)
        out.text = element.text
        for child in element:
            children_out = t.apply(child)
            if children_out:
                out.extend(children_out)
            else:
                # Suppressed child: rescue its tail onto the preceding sibling
                # or the parent's text.
                _rescue_tail(child, out)
        if copy_attrs:
            for attr in copy_attrs:
                val = element.get(attr)
                if val is not None:
                    out.set(attr, val)
        return [out]


def _rescue_tail(
    suppressed: etree._Element,
    parent_out: etree._Element,
) -> None:
    """Append the tail of a suppressed element to sibling or parent text."""
    tail = suppressed.tail
    if not tail:
        return
    siblings = list(parent_out)
    if siblings:
        last = siblings[-1]
        last.tail = (last.tail or "") + tail
    else:
        parent_out.text = (parent_out.text or "") + tail


# ---------------------------------------------------------------------------
# Family-1 prose transformer
# ---------------------------------------------------------------------------

class Family1ProseTransformer(Transformer):
    """Transformer for Family-1 hierarchical-div prose TEI texts.

    Implements the generate_protopages.xsl content-mode rule set.
    """

    def __init__(self, tei_doc: LenientTEIDocument) -> None:
        super().__init__(tei_doc)
        self._register_prose_rules()

    def _register_prose_rules(self) -> None:
        suppress = Transformer._suppress

        # Suppressed elements
        for tag in ("milestone", "pb", "note", "head"):
            self.register(tag, suppress)

        # Pass-through with element rename
        self.register("p",     lambda t, el: Transformer._copy_inline(t, el, "p"))
        self.register("q",     lambda t, el: Transformer._copy_inline(t, el, "q"))
        self.register("quote", lambda t, el: Transformer._copy_inline(t, el, "q"))
        self.register("del",   lambda t, el: Transformer._copy_inline(t, el, "del"))
        self.register("add",   lambda t, el: Transformer._copy_inline(t, el, "add"))

        # Empty output element
        self.register("gap", lambda _t, _el: [etree.Element("gap")])

        # Named entities — copy optional @key attribute
        self.register(
            "placeName",
            lambda t, el: Transformer._copy_inline(t, el, "place", ["key"]),
        )
        self.register(
            "persName",
            lambda t, el: Transformer._copy_inline(t, el, "person", ["key"]),
        )


# ---------------------------------------------------------------------------
# Schema registry and factory
# ---------------------------------------------------------------------------

class SchemaRegistry:
    """Maps TEI schema keys to Transformer subclasses."""

    def __init__(self) -> None:
        self._registry: dict[str, type[Transformer]] = {}

    def register(self, key: str, transformer_class: type[Transformer]) -> None:
        self._registry[key] = transformer_class

    def look_up(self, key: str) -> type[Transformer] | None:
        return self._registry.get(key)


_default_registry = SchemaRegistry()
_default_registry.register("perseus_prose", Family1ProseTransformer)
_default_registry.register("perseus_base",  Family1ProseTransformer)


class TransformerFactory:
    def __init__(self, registry: SchemaRegistry = _default_registry) -> None:
        self._registry = registry

    def transformer_for(self, doc: LenientTEIDocument) -> Transformer:
        # TEIDocument has .schema; LenientTEIDocument does not — default gracefully.
        key = getattr(doc, "schema", None) or "perseus_prose"
        cls = self._registry.look_up(key) or Family1ProseTransformer
        return cls(doc)


# ---------------------------------------------------------------------------
# ProtopageCompiler
# ---------------------------------------------------------------------------

def _sub(parent: etree._Element, tag: str, text: str) -> etree._Element:
    """Append a child element with text content to parent."""
    el = etree.SubElement(parent, tag)
    el.text = text
    return el

class ProtopageCompiler(Compiler[LenientTEIDocument]):
    """Compiles a TEI document into a sequence of ProtopageChunk objects.

    Proof-of-concept: replaces the Saxon/XSLT step of the protopage pipeline.
    """

    def __init__(
        self,
        tei_doc: LenientTEIDocument,
        factory: TransformerFactory | None = None,
    ) -> None:
        self.tei_doc = tei_doc
        self.reference_parser = ReferenceParser(tei_doc)
        self.transformer = (factory or TransformerFactory()).transformer_for(tei_doc)
        self._chunks: list[CitationChunk] | None = None
        self._compiled: list[ProtopageChunk] | None = None

    @property
    def chunks(self) -> list[CitationChunk]:
        if self._chunks is None:
            self._chunks = list(self.reference_parser.chunks())
        return self._chunks

    @property
    def compiled_chunks(self) -> list[ProtopageChunk]:
        if self._compiled is None:
            self._compiled = [self.compile_chunk(c) for c in self.chunks]
        return self._compiled

    def compile_chunk(self, chunk: CitationChunk) -> ProtopageChunk:
        """Transform one CitationChunk into a complete Protopage XML tree.

        The root element is <protopage cts-urn="…"> containing <meta> and
        <content>, matching the format expected by ProtopageRenderer.
        """
        attrs = {"cts-urn": chunk.cts_urn}
        if chunk.prev_urn:
            attrs["prev-urn"] = chunk.prev_urn
        if chunk.next_urn:
            attrs["next-urn"] = chunk.next_urn
        root = etree.Element("protopage", attrib=attrs)

        root.append(self._build_meta(chunk))

        content_el = etree.SubElement(root, "content")
        for out_el in self.transformer.apply_all(chunk.elements):
            content_el.append(out_el)

        return ProtopageChunk(content=root)

    def compile(self, source: LenientTEIDocument, output_path: Path, **kwargs) -> None:
        """Serialize all compiled chunks to output_path as XML files + index.json.

        Writes one ``protopage_{passage}.xml`` file per CitationChunk plus an
        ``index.json`` manifest listing them in document order.  The output
        format is compatible with ProtopageRenderer.

        Args:
            source:      Ignored (the compiler was already constructed with a
                         document); present only to satisfy the Compiler ABC.
            output_path: Directory to write into (created if absent).
        """
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        index_entries = []
        for pc in self.compiled_chunks:
            filename = self._protopage_filename(pc.content.get("cts-urn", ""))
            (output_path / filename).write_bytes(
                etree.tostring(pc.content, encoding="utf-8", xml_declaration=True,
                               pretty_print=True)
            )
            index_entries.append({"file": filename, "cts_urn": pc.content.get("cts-urn", "")})

        (output_path / "index.json").write_text(
            json.dumps({"chunks": index_entries}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        (output_path / "toc.json").write_text(
            json.dumps(self.reference_parser.toc(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_meta(self, chunk: CitationChunk) -> etree._Element:
        """Build a <meta> element from the document's teiHeader.

        Bibliographic metadata (author, title, editors, place, date) is drawn
        from <sourceDesc>/<biblStruct>/<monogr>, which records the source
        edition that was encoded.  Language is taken from <langUsage> or
        xml:lang on <text>/<body>.  Falls back to <titleStmt> values when
        <sourceDesc> does not carry structured data.
        """
        NS = {"tei": TEI_NS}
        root = self.tei_doc.root

        # Language: xml:lang on <text>/<body> first, then langUsage/@ident
        XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
        language = ""
        for tag in ("tei:text", "tei:body"):
            el = root.find(f".//{tag}", NS)
            if el is not None and el.get(XML_LANG):
                language = el.get(XML_LANG)
                break
        if not language:
            lang_el = root.find(".//tei:langUsage/tei:language", NS)
            if lang_el is not None:
                language = lang_el.get("ident", "")

        # Bibliographic source: prefer sourceDesc/biblStruct/monogr
        monogr = root.find(".//tei:sourceDesc/tei:biblStruct/tei:monogr", NS)
        if monogr is not None:
            title  = (monogr.findtext("tei:title",  namespaces=NS) or "").strip()
            author = (monogr.findtext("tei:author", namespaces=NS) or "").strip()
            editors = [(ed.text or "").strip()
                       for ed in monogr.findall("tei:editor", NS)]
            imprint = monogr.find("tei:imprint", NS)
            pub_place = (imprint.findtext("tei:pubPlace",   namespaces=NS) or "").strip() \
                        if imprint is not None else ""
            # Prefer date[@type='published']; fall back to first <date>
            pub_date = ""
            if imprint is not None:
                for d in imprint.findall("tei:date", NS):
                    if d.get("type") == "published":
                        pub_date = (d.text or "").strip()
                        break
                if not pub_date:
                    pub_date = (imprint.findtext("tei:date", namespaces=NS) or "").strip()
        else:
            # Fallback: titleStmt / publicationStmt
            title  = (root.findtext(".//tei:titleStmt/tei:title",  namespaces=NS) or "").strip()
            author = (root.findtext(".//tei:titleStmt/tei:author", namespaces=NS) or "").strip()
            editors = [(ed.text or "").strip()
                       for ed in root.findall(".//tei:titleStmt/tei:editor", NS)]
            pub_stmt = root.find(".//tei:publicationStmt", NS)
            pub_place = (pub_stmt.findtext("tei:pubPlace", namespaces=NS) or "").strip() \
                        if pub_stmt is not None else ""
            pub_date  = (pub_stmt.findtext("tei:date",     namespaces=NS) or "").strip() \
                        if pub_stmt is not None else ""

        meta = etree.Element("meta")
        _sub(meta, "title",    title)
        _sub(meta, "base-urn", self.reference_parser.base_urn)
        _sub(meta, "language", language)
        _sub(meta, "ctsurn",   chunk.cts_urn)
        if chunk.prev_urn:
            _sub(meta, "prev-urn", chunk.prev_urn)
        if chunk.next_urn:
            _sub(meta, "next-urn", chunk.next_urn)

        pub_info = etree.SubElement(meta, "pubInfo")
        _sub(pub_info, "title",    title)
        _sub(pub_info, "author",   author)
        _sub(pub_info, "pubPlace", pub_place)
        _sub(pub_info, "pubDate",  pub_date)
        for ed in editors:
            _sub(pub_info, "editor", ed)

        return meta

    @staticmethod
    def _protopage_filename(cts_urn: str) -> str:
        """Return a safe XML filename for a protopage URN."""
        passage = cts_urn.rsplit(":", 1)[-1].strip().replace(" ", "_")
        return f"protopage_{passage}.xml"
