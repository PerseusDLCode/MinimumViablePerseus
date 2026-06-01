"""ProtopageCompiler — compiles a TEI document into Protopage XML chunks."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from mvp.corpus.models import CitationChunk
from mvp.corpus.reference_parser import ReferenceParser
from mvp.corpus.tei_document import LenientTEIDocument
from mvp.site.compilers.base import Compiler
from mvp.compilers.transformers import Transformer, TransformerFactory

TEI_NS = "http://www.tei-c.org/ns/1.0"


@dataclass
class ProtopageChunk:
    """Protopage XML output for one citation chunk."""
    content: etree._Element
    cts_urn: str


def _sub(parent: etree._Element, tag: str, text: str) -> etree._Element:
    """Append a child element with text content to parent."""
    el = etree.SubElement(parent, tag)
    el.text = text
    return el


class ProtopageCompiler(Compiler[LenientTEIDocument]):
    """Compiles a TEI document into a sequence of ProtopageChunk objects."""

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

        The root element is <protopage> (no attributes) containing <meta> and
        <content>.  Per-chunk navigation data lives in <meta>.
        """
        root = etree.Element("protopage")
        root.append(self._build_meta(chunk))

        content_el = etree.SubElement(root, "content")
        for out_el in self.transformer.apply_all(chunk.elements):
            content_el.append(out_el)

        return ProtopageChunk(content=root, cts_urn=chunk.cts_urn)

    def compile(self, source: LenientTEIDocument, output_path: Path, **kwargs) -> None:
        """Serialize all compiled chunks to output_path as XML files + index.json + metadata.json.

        Writes one ``protopage_{passage}.xml`` file per CitationChunk, an
        ``index.json`` manifest, and a ``metadata.json`` sidecar containing
        document-level bibliographic data and the full TOC hierarchy.

        Args:
            source:      Ignored (the compiler was already constructed with a
                         document); present only to satisfy the Compiler ABC.
            output_path: Directory to write into (created if absent).
        """
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        index_entries = []
        for pc in self.compiled_chunks:
            filename = self._protopage_filename(pc.cts_urn)
            (output_path / filename).write_bytes(
                etree.tostring(pc.content, encoding="utf-8", xml_declaration=True,
                               pretty_print=True)
            )
            index_entries.append({"file": filename, "cts_urn": pc.cts_urn})

        (output_path / "index.json").write_text(
            json.dumps({"chunks": index_entries}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        metadata = {
            "version": "1",
            "document": self._build_document_metadata(),
            "toc": self.reference_parser.toc(),
        }
        (output_path / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_meta(self, chunk: CitationChunk) -> etree._Element:
        """Build a <meta> element with per-chunk navigation data.

        Document-level bibliographic data lives in metadata.json.  <meta>
        carries only the four fields that vary per chunk: base-urn, ctsurn,
        prev-urn, next-urn.
        """
        meta = etree.Element("meta")
        _sub(meta, "base-urn", self.reference_parser.base_urn)
        _sub(meta, "ctsurn",   chunk.cts_urn)
        if chunk.prev_urn:
            _sub(meta, "prev-urn", chunk.prev_urn)
        if chunk.next_urn:
            _sub(meta, "next-urn", chunk.next_urn)
        return meta

    def _build_document_metadata(self) -> dict:
        """Extract document-level bibliographic metadata for metadata.json.

        Prefers <sourceDesc>/<biblStruct>/<monogr> (the source edition record);
        falls back to <titleStmt>/<publicationStmt> (the encoding record).
        """
        NS = {"tei": TEI_NS}
        root = self.tei_doc.root

        # Language: xml:lang on <text> or <body> first, then langUsage/@ident
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
            title   = (monogr.findtext("tei:title",  namespaces=NS) or "").strip()
            author  = (monogr.findtext("tei:author", namespaces=NS) or "").strip()
            editors = [(ed.text or "").strip() for ed in monogr.findall("tei:editor", NS)]
            imprint = monogr.find("tei:imprint", NS)
            pub_place = (imprint.findtext("tei:pubPlace", namespaces=NS) or "").strip() \
                        if imprint is not None else ""
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
            title   = (root.findtext(".//tei:titleStmt/tei:title",  namespaces=NS) or "").strip()
            author  = (root.findtext(".//tei:titleStmt/tei:author", namespaces=NS) or "").strip()
            editors = [(ed.text or "").strip()
                       for ed in root.findall(".//tei:titleStmt/tei:editor", NS)]
            pub_stmt  = root.find(".//tei:publicationStmt", NS)
            pub_place = (pub_stmt.findtext("tei:pubPlace", namespaces=NS) or "").strip() \
                        if pub_stmt is not None else ""
            pub_date  = (pub_stmt.findtext("tei:date",     namespaces=NS) or "").strip() \
                        if pub_stmt is not None else ""

        return {
            "base_urn":  self.reference_parser.base_urn,
            "title":     title,
            "author":    author,
            "language":  language,
            "editors":   editors,
            "pub_place": pub_place,
            "pub_date":  pub_date,
        }

    @staticmethod
    def _protopage_filename(cts_urn: str) -> str:
        """Return a safe XML filename for a protopage URN."""
        passage = cts_urn.rsplit(":", 1)[-1].strip().replace(" ", "_")
        return f"protopage_{passage}.xml"
