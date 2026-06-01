from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mvp.corpus.models import CitationChunk
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


# ---------------------------------------------------------------------------
# toc()
# ---------------------------------------------------------------------------


class TestTOC:

    def test_returns_list(self, thucydides_parser):
        result = thucydides_parser.toc()
        assert isinstance(result, list)

    def test_top_level_count_equals_book_count(self, thucydides_parser):
        # THUCYDIDES_XML has 2 books
        result = thucydides_parser.toc()
        assert len(result) == 2

    def test_top_level_depth_is_zero(self, thucydides_parser):
        result = thucydides_parser.toc()
        assert all(e["depth"] == 0 for e in result)

    def test_top_level_index_is_one_based(self, thucydides_parser):
        result = thucydides_parser.toc()
        assert [e["index"] for e in result] == [1, 2]

    def test_top_level_subtype_is_book(self, thucydides_parser):
        result = thucydides_parser.toc()
        assert all(e["subtype"] == "book" for e in result)

    def test_top_level_label(self, thucydides_parser):
        result = thucydides_parser.toc()
        assert result[0]["label"] == "Book 1"
        assert result[1]["label"] == "Book 2"

    def test_top_level_urn(self, thucydides_parser):
        result = thucydides_parser.toc()
        assert result[0]["urn"] == f"{THUCYDIDES_BASE}:1"
        assert result[1]["urn"] == f"{THUCYDIDES_BASE}:2"

    def test_subpassages_are_chapters(self, thucydides_parser):
        result = thucydides_parser.toc()
        for entry in result[0]["subpassages"]:
            assert entry["subtype"] == "chapter"
            assert entry["depth"] == 1

    def test_chapter_index_restarts_per_book(self, thucydides_parser):
        result = thucydides_parser.toc()
        assert [e["index"] for e in result[0]["subpassages"]] == [1, 2]
        assert [e["index"] for e in result[1]["subpassages"]] == [1]

    def test_chapter_subpassages_contain_sections(self, thucydides_parser):
        result = thucydides_parser.toc()
        sections = result[0]["subpassages"][0]["subpassages"]
        assert len(sections) == 3
        assert all(e["subtype"] == "section" for e in sections)
        assert all(e["depth"] == 2 for e in sections)

    def test_leaf_subpassages_empty(self, thucydides_parser):
        result = thucydides_parser.toc()
        for section in result[0]["subpassages"][0]["subpassages"]:
            assert section["subpassages"] == []

    def test_single_level_doc(self, apology_parser):
        result = apology_parser.toc()
        assert len(result) == 3
        assert all(e["depth"] == 0 for e in result)
        assert all(e["subpassages"] == [] for e in result)

    def test_toc_without_n_attr_uses_idx_for_label_not_urn(self, tmp_path):
        # When structural elements carry no @n, toc() should fall back to the
        # 1-based sibling index for the display label but leave the URN suffix
        # empty (consistent with citation_records()).  This pins the deliberate
        # val-fallback resolution made during the _walk_cs refactor.
        base = "urn:cts:greekLit:tlg0001.tlg001.test"
        xml = textwrap.dedent(f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <TEI xmlns="{TEI_NS}">
              <teiHeader>
                <encodingDesc>
                  <refsDecl default="true">
                    <citeStructure match="/tei:TEI/tei:text/tei:body" use="@xml:base">
                      <citeStructure unit="book" delim=":" match="tei:div[@type='textpart']"/>
                    </citeStructure>
                  </refsDecl>
                </encodingDesc>
              </teiHeader>
              <text>
                <body xml:base="{base}">
                  <div type="textpart"><p>one</p></div>
                  <div type="textpart"><p>two</p></div>
                </body>
              </text>
            </TEI>
        """)
        path = tmp_path / "no_n.xml"
        path.write_text(xml, encoding="utf-8")
        doc = LenientTEIDocument(path)
        result = ReferenceParser(doc).toc()
        assert len(result) == 2
        # Labels use 1-based index as fallback
        assert result[0]["label"] == "Book 1"
        assert result[1]["label"] == "Book 2"
        # URN suffix uses val="" — consistent with citation_records()
        assert result[0]["urn"] == base + ":"
        assert result[1]["urn"] == base + ":"


# ---------------------------------------------------------------------------
# chunks() — div-based
# ---------------------------------------------------------------------------


class TestChunksDivBased:
    """chunks() on a 3-level hierarchy defaults to the penultimate (chapter) level."""

    def test_returns_citation_chunk_objects(self, thucydides_parser):
        result = list(thucydides_parser.chunks())
        assert all(isinstance(c, CitationChunk) for c in result)

    def test_chunk_count_equals_chapter_count(self, thucydides_parser):
        # THUCYDIDES_XML has 3 chapters (book1:ch1, book1:ch2, book2:ch1)
        result = list(thucydides_parser.chunks())
        assert len(result) == 3

    def test_chunks_are_chapter_level(self, thucydides_parser):
        result = list(thucydides_parser.chunks())
        assert all(c.unit == "chapter" for c in result)

    def test_each_chunk_has_one_element(self, thucydides_parser):
        result = list(thucydides_parser.chunks())
        assert all(len(c.elements) == 1 for c in result)

    def test_chunk_urns_are_correct(self, thucydides_parser):
        urns = [c.cts_urn for c in thucydides_parser.chunks()]
        assert urns == [
            f"{THUCYDIDES_BASE}:1.1",
            f"{THUCYDIDES_BASE}:1.2",
            f"{THUCYDIDES_BASE}:2.1",
        ]

    def test_prev_next_navigation(self, thucydides_parser):
        chunks = list(thucydides_parser.chunks())
        assert chunks[0].prev_urn is None
        assert chunks[0].next_urn == f"{THUCYDIDES_BASE}:1.2"
        assert chunks[1].prev_urn == f"{THUCYDIDES_BASE}:1.1"
        assert chunks[1].next_urn == f"{THUCYDIDES_BASE}:2.1"
        assert chunks[2].prev_urn == f"{THUCYDIDES_BASE}:1.2"
        assert chunks[2].next_urn is None

    def test_single_level_uses_that_level(self, apology_parser):
        # Apology has only one citation level (section); penultimate == leaf
        result = list(apology_parser.chunks())
        assert len(result) == 3
        assert all(c.unit == "section" for c in result)

    def test_n_chunk_attr_overrides_penultimate(self, tmp_path):
        # Mark sections (leaf) as the chunk level explicitly on a 3-level doc
        xml = f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <TEI xmlns="http://www.tei-c.org/ns/1.0">
              <teiHeader>
                <encodingDesc>
                  <refsDecl default="true">
                    <citeStructure match="/tei:TEI/tei:text/tei:body" use="@xml:base">
                      <citeStructure unit="book" delim=":" match="tei:div[@subtype='book']" use="@n">
                        <citeStructure unit="chapter" delim="." match="tei:div[@subtype='chapter']" use="@n">
                          <citeStructure unit="section" delim="." match="tei:div[@subtype='section']" use="@n" n="chunk"/>
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
                      <div type="textpart" subtype="section" n="1"><p>A</p></div>
                      <div type="textpart" subtype="section" n="2"><p>B</p></div>
                    </div>
                  </div>
                </body>
              </text>
            </TEI>"""
        from pathlib import Path
        p = tmp_path / "chunk.xml"
        p.write_text(xml, encoding="utf-8")
        from mvp.corpus.tei_document import LenientTEIDocument
        parser = ReferenceParser(LenientTEIDocument(p))
        result = list(parser.chunks())
        assert len(result) == 2
        assert all(c.unit == "section" for c in result)


# ---------------------------------------------------------------------------
# chunks() — milestone-based
# ---------------------------------------------------------------------------

MILESTONE_BASE = "urn:cts:myexample:author.work.edition"

MILESTONE_XML = f"""\
    <?xml version="1.0" encoding="UTF-8"?>
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <teiHeader>
        <encodingDesc>
          <refsDecl default="true">
            <citeStructure match="//tei:milestone[@unit='card']"
                           unit="card" delim=" " use="@n" n="chunk"/>
          </refsDecl>
        </encodingDesc>
      </teiHeader>
      <text>
        <body xml:base="{MILESTONE_BASE}">
          <milestone unit="card" n="1"/>
          <div><p>card 1 content</p></div>
          <milestone unit="card" n="2"/>
          <div><p>card 2 content</p></div>
          <milestone unit="card" n="3"/>
          <div><p>card 3 content</p></div>
        </body>
      </text>
    </TEI>"""


@pytest.fixture
def milestone_parser(tmp_path):
    p = tmp_path / "milestone.xml"
    p.write_text(MILESTONE_XML, encoding="utf-8")
    from mvp.corpus.tei_document import LenientTEIDocument
    return ReferenceParser(LenientTEIDocument(p))


class TestChunksMilestoneBased:

    def test_returns_citation_chunk_objects(self, milestone_parser):
        result = list(milestone_parser.chunks())
        assert all(isinstance(c, CitationChunk) for c in result)

    def test_chunk_count_equals_milestone_count(self, milestone_parser):
        result = list(milestone_parser.chunks())
        assert len(result) == 3

    def test_chunks_are_card_unit(self, milestone_parser):
        result = list(milestone_parser.chunks())
        assert all(c.unit == "card" for c in result)

    def test_chunk_urns(self, milestone_parser):
        urns = [c.cts_urn for c in milestone_parser.chunks()]
        assert urns == [
            f"{MILESTONE_BASE} 1",
            f"{MILESTONE_BASE} 2",
            f"{MILESTONE_BASE} 3",
        ]

    def test_prev_next_navigation(self, milestone_parser):
        chunks = list(milestone_parser.chunks())
        assert chunks[0].prev_urn is None
        assert chunks[0].next_urn == f"{MILESTONE_BASE} 2"
        assert chunks[2].prev_urn == f"{MILESTONE_BASE} 2"
        assert chunks[2].next_urn is None

    def test_each_chunk_contains_correct_content(self, milestone_parser):
        from lxml import etree as _etree
        chunks = list(milestone_parser.chunks())
        # Elements are TEI-namespaced; check localname and text content.
        divs0 = [e for e in chunks[0].elements if _etree.QName(e.tag).localname == "div"]
        assert len(divs0) == 1
        assert divs0[0][0].text == "card 1 content"
        divs1 = [e for e in chunks[1].elements if _etree.QName(e.tag).localname == "div"]
        assert divs1[0][0].text == "card 2 content"
