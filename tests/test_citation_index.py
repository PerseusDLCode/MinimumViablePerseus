from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from mvp.indexers.citation_index import CitationIndexGenerator, _xml_id
from mvp.models import CitationRecord
from mvp.cts_resolver import ConfigurationError, CTSResolver as ReferenceParser
from mvp.models.document import LenientTEIDocument

# ---------------------------------------------------------------------------
# Shared XML fixtures (reuse patterns from test_reference_parser)
# ---------------------------------------------------------------------------

TEI_NS = "http://www.tei-c.org/ns/1.0"

APOLOGY_BASE = "urn:cts:greekLit:tlg0059.tlg002.perseus-grc2"
THUCYDIDES_BASE = "urn:cts:greekLit:tlg0003.tlg001.perseus-grc2"


def write_xml(tmp_path: Path, xml: str) -> Path:
    p = tmp_path / "test.xml"
    p.write_text(textwrap.dedent(xml), encoding="utf-8")
    return p


APOLOGY_XML = f"""\
    <?xml version="1.0" encoding="UTF-8"?>
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <teiHeader>
        <encodingDesc>
          <refsDecl xml:id="cite_by_section" default="true">
            <citeStructure match="/tei:TEI/tei:text/tei:body" use="@xml:base">
              <citeStructure unit="section" delim=":" match="tei:div[@type='textpart']" use="@n"/>
            </citeStructure>
          </refsDecl>
        </encodingDesc>
      </teiHeader>
      <text>
        <body xml:base="{APOLOGY_BASE}">
          <div type="textpart" n="17"><p>ὅτι μέν...</p></div>
          <div type="textpart" n="18"><p>τοῦτο...</p></div>
          <div type="textpart" n="19"><p>ἴσως...</p></div>
        </body>
      </text>
    </TEI>
"""

THUCYDIDES_XML = f"""\
    <?xml version="1.0" encoding="UTF-8"?>
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <teiHeader>
        <encodingDesc>
          <refsDecl xml:id="cite_by_section" default="true">
            <citeStructure match="/tei:TEI/tei:text/tei:body" use="@xml:base">
              <citeStructure unit="book" delim=":" match="tei:div[@subtype='book']" use="@n">
                <citeStructure unit="chapter" delim="." match="tei:div[@subtype='chapter']" use="@n">
                  <citeStructure unit="section" delim="." match="tei:div[@subtype='section']" use="@n"/>
                </citeStructure>
              </citeStructure>
            </citeStructure>
          </refsDecl>
        </encodingDesc>
      </teiHeader>
      <text>
        <body xml:base="{THUCYDIDES_BASE}">
          <div type="textpart" subtype="book" n="1">
            <div type="textpart" subtype="chapter" n="1">
              <div type="textpart" subtype="section" n="1"><p>Θουκυδίδης...</p></div>
              <div type="textpart" subtype="section" n="2"><p>text</p></div>
            </div>
            <div type="textpart" subtype="chapter" n="2">
              <div type="textpart" subtype="section" n="1"><p>text</p></div>
            </div>
          </div>
        </body>
      </text>
    </TEI>
"""


@pytest.fixture
def apology_doc(tmp_path):
    return LenientTEIDocument(write_xml(tmp_path, APOLOGY_XML))


@pytest.fixture
def thucydides_doc(tmp_path):
    return LenientTEIDocument(write_xml(tmp_path, THUCYDIDES_XML))


# ---------------------------------------------------------------------------
# _xml_id helper
# ---------------------------------------------------------------------------


class TestXmlId:

    def test_single_level_passage(self):
        assert _xml_id("section", "17") == "section-17"

    def test_multi_level_passage_dots_become_hyphens(self):
        assert _xml_id("section", "1.1.3") == "section-1-1-3"

    def test_chapter_passage(self):
        assert _xml_id("chapter", "1.2") == "chapter-1-2"

    def test_book_passage(self):
        assert _xml_id("book", "2") == "book-2"


# ---------------------------------------------------------------------------
# ReferenceParser.citation_records and base_urn property
# ---------------------------------------------------------------------------


class TestCitationRecords:

    def test_base_urn_property(self, apology_doc):
        parser = ReferenceParser(apology_doc)
        assert parser.base_urn == APOLOGY_BASE

    def test_apology_record_count(self, apology_doc):
        parser = ReferenceParser(apology_doc)
        records = list(parser.citation_records())
        assert len(records) == 3

    def test_apology_record_fields(self, apology_doc):
        parser = ReferenceParser(apology_doc)
        records = list(parser.citation_records())
        r = records[0]
        assert isinstance(r, CitationRecord)
        assert r.urn == f"{APOLOGY_BASE}:17"
        assert r.unit == "section"
        assert r.depth == 0

    def test_thucydides_record_depth_zero_unit(self, thucydides_doc):
        parser = ReferenceParser(thucydides_doc)
        records = list(parser.citation_records(depth=0))
        assert all(r.unit == "book" for r in records)
        assert all(r.depth == 0 for r in records)

    def test_thucydides_record_depths(self, thucydides_doc):
        parser = ReferenceParser(thucydides_doc)
        records = list(parser.citation_records(depth=-1))
        depths = {r.depth for r in records}
        assert depths == {0, 1, 2}
        units_by_depth = {d: {r.unit for r in records if r.depth == d} for d in depths}
        assert units_by_depth[0] == {"book"}
        assert units_by_depth[1] == {"chapter"}
        assert units_by_depth[2] == {"section"}

    def test_citation_records_document_order(self, thucydides_doc):
        parser = ReferenceParser(thucydides_doc)
        records = list(parser.citation_records(depth=-1))
        urns = [r.urn for r in records]
        assert urns[0] == f"{THUCYDIDES_BASE}:1"
        assert urns[1] == f"{THUCYDIDES_BASE}:1.1"
        assert urns[2] == f"{THUCYDIDES_BASE}:1.1.1"


# ---------------------------------------------------------------------------
# CitationIndexGenerator.generate
# ---------------------------------------------------------------------------


class TestCitationIndexGeneratorGenerate:

    def test_apology_base_urn(self, apology_doc):
        gen = CitationIndexGenerator(apology_doc)
        data = gen.generate()
        assert data["base_urn"] == APOLOGY_BASE

    def test_apology_citation_count(self, apology_doc):
        gen = CitationIndexGenerator(apology_doc)
        data = gen.generate()
        assert len(data["citations"]) == 3

    def test_apology_citation_shape(self, apology_doc):
        gen = CitationIndexGenerator(apology_doc)
        first = gen.generate()["citations"][0]
        assert first["urn"] == f"{APOLOGY_BASE}:17"
        assert first["unit"] == "section"
        assert first["xml_id"] == "section-17"
        assert first["depth"] == 0

    def test_thucydides_total_citations(self, thucydides_doc):
        gen = CitationIndexGenerator(thucydides_doc)
        data = gen.generate()
        # 1 book + 2 chapters + 3 sections = 6
        assert len(data["citations"]) == 6

    def test_thucydides_xml_ids(self, thucydides_doc):
        gen = CitationIndexGenerator(thucydides_doc)
        citations = gen.generate()["citations"]
        by_urn = {c["urn"]: c for c in citations}
        assert by_urn[f"{THUCYDIDES_BASE}:1"]["xml_id"] == "book-1"
        assert by_urn[f"{THUCYDIDES_BASE}:1.1"]["xml_id"] == "chapter-1-1"
        assert by_urn[f"{THUCYDIDES_BASE}:1.1.1"]["xml_id"] == "section-1-1-1"

    def test_no_cite_structure_raises(self, tmp_path):
        xml = f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <TEI xmlns="http://www.tei-c.org/ns/1.0">
              <teiHeader><encodingDesc>
                <refsDecl n="CTS"><cRefPattern n="s" matchPattern="(\\w+)"
                  replacementPattern="#xpath(...)"><p>s</p></cRefPattern></refsDecl>
              </encodingDesc></teiHeader>
              <text><body xml:base="{APOLOGY_BASE}">
                <div type="textpart" n="1"><p>text</p></div>
              </body></text>
            </TEI>
        """
        doc = LenientTEIDocument(write_xml(tmp_path, xml))
        with pytest.raises(ConfigurationError):
            CitationIndexGenerator(doc)


# ---------------------------------------------------------------------------
# CitationIndexGenerator.write
# ---------------------------------------------------------------------------


class TestCitationIndexGeneratorWrite:

    def test_write_creates_file(self, apology_doc, tmp_path):
        out = tmp_path / "output" / "citations.json"
        CitationIndexGenerator(apology_doc).write(out)
        assert out.exists()

    def test_write_valid_json(self, apology_doc, tmp_path):
        out = tmp_path / "citations.json"
        CitationIndexGenerator(apology_doc).write(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "base_urn" in data
        assert "citations" in data

    def test_write_content_matches_generate(self, apology_doc, tmp_path):
        out = tmp_path / "citations.json"
        gen = CitationIndexGenerator(apology_doc)
        gen.write(out)
        assert json.loads(out.read_text(encoding="utf-8")) == gen.generate()

    def test_write_creates_parent_dirs(self, apology_doc, tmp_path):
        out = tmp_path / "a" / "b" / "c" / "citations.json"
        CitationIndexGenerator(apology_doc).write(out)
        assert out.exists()


# ---------------------------------------------------------------------------
# SiteMap.citations_path
# ---------------------------------------------------------------------------


class TestSiteMapCitationsPath:

    def test_citations_path_under_chunk_dir(self, tmp_path):
        from mvp.site_map import SiteMap
        sm = SiteMap(tmp_path)
        urn = APOLOGY_BASE
        p = sm.citations_path(urn)
        assert p == sm.chunk_dir(urn) / "citations.json"

    def test_citations_path_filename(self, tmp_path):
        from mvp.site_map import SiteMap
        p = SiteMap(tmp_path).citations_path(APOLOGY_BASE)
        assert p.name == "citations.json"
