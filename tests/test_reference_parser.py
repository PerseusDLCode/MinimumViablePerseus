from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mvp.corpus.tei_document import LenientTEIDocument
from mvp.corpus.reference_parser import CitationError, ConfigurationError, ReferenceParser

# ---------------------------------------------------------------------------
# Helpers and fixture XML
# ---------------------------------------------------------------------------

TEI_NS = "http://www.tei-c.org/ns/1.0"


def write_xml(tmp_path: Path, xml: str) -> Path:
    p = tmp_path / "test.xml"
    p.write_text(textwrap.dedent(xml), encoding="utf-8")
    return p


APOLOGY_BASE = "urn:cts:greekLit:tlg0059.tlg002.perseus-grc2"

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
          <div type="textpart" subtype="section" n="17"><p>ὅτι μέν...</p></div>
          <div type="textpart" subtype="section" n="18"><p>τοῦτο...</p></div>
          <div type="textpart" subtype="section" n="19"><p>ἴσως...</p></div>
        </body>
      </text>
    </TEI>
"""

THUCYDIDES_BASE = "urn:cts:greekLit:tlg0003.tlg001.perseus-grc2"

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
              <div type="textpart" subtype="section" n="3"><p>text</p></div>
            </div>
            <div type="textpart" subtype="chapter" n="2">
              <div type="textpart" subtype="section" n="1"><p>text</p></div>
              <div type="textpart" subtype="section" n="2"><p>text</p></div>
            </div>
          </div>
          <div type="textpart" subtype="book" n="2">
            <div type="textpart" subtype="chapter" n="1">
              <div type="textpart" subtype="section" n="1"><p>text</p></div>
            </div>
          </div>
        </body>
      </text>
    </TEI>
"""

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def apology_doc(tmp_path):
    return LenientTEIDocument(write_xml(tmp_path, APOLOGY_XML))


@pytest.fixture
def apology_parser(apology_doc):
    return ReferenceParser(apology_doc)


@pytest.fixture
def thucydides_doc(tmp_path):
    return LenientTEIDocument(write_xml(tmp_path, THUCYDIDES_XML))


@pytest.fixture
def thucydides_parser(thucydides_doc):
    return ReferenceParser(thucydides_doc)


# ---------------------------------------------------------------------------
# Apology — constructor
# ---------------------------------------------------------------------------


class TestApologyConstructor:

    def test_no_default_single_cs_succeeds(self, tmp_path):
        xml = f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <TEI xmlns="http://www.tei-c.org/ns/1.0">
              <teiHeader>
                <encodingDesc>
                  <refsDecl xml:id="cite_by_section">
                    <citeStructure match="/tei:TEI/tei:text/tei:body" use="@xml:base">
                      <citeStructure unit="section" delim=":" match="tei:div[@type='textpart']" use="@n"/>
                    </citeStructure>
                  </refsDecl>
                </encodingDesc>
              </teiHeader>
              <text>
                <body xml:base="{APOLOGY_BASE}">
                  <div type="textpart" n="1"><p>text</p></div>
                </body>
              </text>
            </TEI>
        """
        doc = LenientTEIDocument(write_xml(tmp_path, xml))
        assert ReferenceParser(doc) is not None

    def test_no_cite_structure_raises(self, tmp_path):
        xml = f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <TEI xmlns="http://www.tei-c.org/ns/1.0">
              <teiHeader>
                <encodingDesc>
                  <refsDecl n="CTS">
                    <cRefPattern n="section" matchPattern="(\\w+)"
                                 replacementPattern="#xpath(...)">
                      <p>section</p>
                    </cRefPattern>
                  </refsDecl>
                </encodingDesc>
              </teiHeader>
              <text>
                <body xml:base="{APOLOGY_BASE}">
                  <div type="textpart" n="1"><p>text</p></div>
                </body>
              </text>
            </TEI>
        """
        doc = LenientTEIDocument(write_xml(tmp_path, xml))
        with pytest.raises(ConfigurationError):
            ReferenceParser(doc)

    def test_body_n_without_xml_base_raises(self, tmp_path):
        xml = f"""\
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
                <body n="{APOLOGY_BASE}">
                  <div type="textpart" n="1"><p>text</p></div>
                </body>
              </text>
            </TEI>
        """
        doc = LenientTEIDocument(write_xml(tmp_path, xml))
        with pytest.raises(ConfigurationError):
            ReferenceParser(doc)

    def test_nonexistent_refsDecl_id_raises(self, apology_doc):
        with pytest.raises(ConfigurationError):
            ReferenceParser(apology_doc, refsDecl_id="no_such_id")

    def test_explicit_refsDecl_id_selects_correct_decl(self, apology_doc):
        assert ReferenceParser(apology_doc, refsDecl_id="cite_by_section") is not None


# ---------------------------------------------------------------------------
# Apology — resolve
# ---------------------------------------------------------------------------


class TestApologyResolve:

    def test_resolve_known_section(self, apology_parser):
        elem = apology_parser.resolve(f"{APOLOGY_BASE}:17")
        assert elem.get("n") == "17"
        assert elem.get("type") == "textpart"

    def test_resolve_wrong_base_raises(self, apology_parser):
        with pytest.raises(CitationError):
            apology_parser.resolve("urn:cts:greekLit:tlg9999.tlg001.foo:17")

    def test_resolve_nonexistent_section_raises(self, apology_parser):
        with pytest.raises(CitationError):
            apology_parser.resolve(f"{APOLOGY_BASE}:99")


# ---------------------------------------------------------------------------
# Apology — generate
# ---------------------------------------------------------------------------


class TestApologyGenerate:

    def test_generate_known_section(self, apology_doc, apology_parser):
        body = apology_doc.root.find(f".//{{{TEI_NS}}}body")
        div_17 = next(
            d for d in body.findall(f"{{{TEI_NS}}}div") if d.get("n") == "17"
        )
        assert apology_parser.generate(div_17) == f"{APOLOGY_BASE}:17"

    def test_generate_unreachable_element_raises(self, apology_doc, apology_parser):
        # <p> elements are not citable at any citeStructure level.
        p = apology_doc.root.find(f".//{{{TEI_NS}}}p")
        with pytest.raises(CitationError):
            apology_parser.generate(p)


# ---------------------------------------------------------------------------
# Apology — citations
# ---------------------------------------------------------------------------


class TestApologyCitations:

    def test_citations_all_levels_count(self, apology_parser):
        assert len(list(apology_parser.citations(depth=-1))) == 3

    def test_citations_depth_zero_same_as_all(self, apology_parser):
        # Single-level hierarchy: depth=0 (root) is also the leaf level.
        assert len(list(apology_parser.citations(depth=0))) == 3

    def test_citations_document_order(self, apology_parser):
        assert list(apology_parser.citations()) == [
            f"{APOLOGY_BASE}:17",
            f"{APOLOGY_BASE}:18",
            f"{APOLOGY_BASE}:19",
        ]


# ---------------------------------------------------------------------------
# Thucydides — resolve
# ---------------------------------------------------------------------------


class TestThucydidesResolve:

    def test_resolve_full_three_level(self, thucydides_parser):
        # Book 1, chapter 1 has sections 1-3; use 1.1.3 as the full citation.
        elem = thucydides_parser.resolve(f"{THUCYDIDES_BASE}:1.1.3")
        assert elem.get("subtype") == "section"
        assert elem.get("n") == "3"
        chapter = elem.getparent()
        assert chapter.get("subtype") == "chapter"
        assert chapter.get("n") == "1"
        book = chapter.getparent()
        assert book.get("subtype") == "book"
        assert book.get("n") == "1"

    def test_resolve_partial_book(self, thucydides_parser):
        elem = thucydides_parser.resolve(f"{THUCYDIDES_BASE}:1")
        assert elem.get("subtype") == "book"
        assert elem.get("n") == "1"

    def test_resolve_partial_chapter(self, thucydides_parser):
        elem = thucydides_parser.resolve(f"{THUCYDIDES_BASE}:1.2")
        assert elem.get("subtype") == "chapter"
        assert elem.get("n") == "2"


# ---------------------------------------------------------------------------
# Thucydides — generate
# ---------------------------------------------------------------------------


class TestThucydidesGenerate:

    def _get(self, doc, **attrs):
        """Find a div by keyword attrs (subtype, n)."""
        root = doc.root
        for div in root.iter(f"{{{TEI_NS}}}div"):
            if all(div.get(k) == v for k, v in attrs.items()):
                return div
        raise KeyError(attrs)

    def test_generate_section_full_urn(self, thucydides_doc, thucydides_parser):
        # Section 3 of chapter 1 of book 1 (1.1.3 exists in the fixture).
        book1 = self._get(thucydides_doc, subtype="book", n="1")
        ch1 = next(
            d for d in book1 if d.get("subtype") == "chapter" and d.get("n") == "1"
        )
        sec3 = next(
            d for d in ch1 if d.get("subtype") == "section" and d.get("n") == "3"
        )
        assert thucydides_parser.generate(sec3) == f"{THUCYDIDES_BASE}:1.1.3"

    def test_generate_book_partial_urn(self, thucydides_doc, thucydides_parser):
        book1 = self._get(thucydides_doc, subtype="book", n="1")
        assert thucydides_parser.generate(book1) == f"{THUCYDIDES_BASE}:1"


# ---------------------------------------------------------------------------
# Thucydides — citations
# ---------------------------------------------------------------------------


class TestThucydidesCitations:

    def test_citations_depth_zero_books_only(self, thucydides_parser):
        urns = list(thucydides_parser.citations(depth=0))
        assert urns == [
            f"{THUCYDIDES_BASE}:1",
            f"{THUCYDIDES_BASE}:2",
        ]

    def test_citations_depth_one_books_and_chapters(self, thucydides_parser):
        urns = list(thucydides_parser.citations(depth=1))
        # 2 books + 3 chapters (book1→2 chapters, book2→1 chapter)
        assert len(urns) == 5
        assert f"{THUCYDIDES_BASE}:1" in urns
        assert f"{THUCYDIDES_BASE}:1.1" in urns
        assert f"{THUCYDIDES_BASE}:1.2" in urns
        assert f"{THUCYDIDES_BASE}:2" in urns
        assert f"{THUCYDIDES_BASE}:2.1" in urns

    def test_citations_all_levels_count(self, thucydides_parser):
        # 2 books + 3 chapters + 6 sections = 11
        assert len(list(thucydides_parser.citations(depth=-1))) == 11

    def test_citations_document_order(self, thucydides_parser):
        urns = list(thucydides_parser.citations(depth=-1))
        assert urns[0] == f"{THUCYDIDES_BASE}:1"
        assert urns[1] == f"{THUCYDIDES_BASE}:1.1"
        assert urns[2] == f"{THUCYDIDES_BASE}:1.1.1"
        assert urns[-1] == f"{THUCYDIDES_BASE}:2.1.1"
