"""Chunker - compiles a TEI document into chunks."""
from __future__ import annotations

import re
import json
from pathlib import Path

from lxml import etree
from mvp.constants import TEI_NS
from mvp.cts_resolver import CTSResolver
from mvp.models import LenientTEIDocument, CitationChunk


class Chunker:
    """Compiles a TEI document into CitationChunk XML files.

    Writes one XML file per chunk plus index.json and metadata.json."""

    def __init__(self, tei_doc:LenientTEIDocument) -> None:
        self.tei_doc:LenientTEIDocument = tei_doc
        self.cts_resolver = CTSResolver(tei_doc)
        self._citation_chunks: list[CitationChunk] | None = None


    @property
    def citation_chunks(self) -> list[CitationChunk]:
        if self._citation_chunks is None:
            self._citation_chunks = self.cts_resolver.chunks()
        return self._citation_chunks

    def compile(self, output_path:Path, **kwargs):
        output_path.mkdir(parents=True, exist_ok=True)
        index_entries: list[dict] = []
        for chunk in self.citation_chunks:
            fname = self._chunk_filename(chunk)
            index_entries.append({"file": fname, "cts_urn": chunk.cts_urn})
            (output_path / fname).write_bytes(
                etree.tostring(chunk.to_xml(), encoding="utf-8", xml_declaration=True,
                               pretty_print=True)
                )

        (output_path / "index.json").write_text(
            json.dumps({"chunks": index_entries}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        metadata = {
            "version": "1",
            "document": self._build_document_metadata(),
            "toc": self.cts_resolver.toc(),
        }
        (output_path / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    _CTS_PATTERN = re.compile(
        r"urn:cts:[^:]+:[^:]+:(?P<passage>.+)$"
    )

    @staticmethod
    def _chunk_filename(chunk: CitationChunk) -> str:
        """Return a safe XML filename derived from the passage component of the URN."""
        m = Chunker._CTS_PATTERN.match(chunk.cts_urn)
        if m is None:
            safe = re.sub(r"[^\w.-]", "_", chunk.cts_urn)
            return f"{safe}.xml"
        return f"{m['passage']}.xml"

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
            "base_urn":  self.cts_resolver.base_urn,
            "title":     title,
            "author":    author,
            "language":  language,
            "editors":   editors,
            "pub_place": pub_place,
            "pub_date":  pub_date,
        }
