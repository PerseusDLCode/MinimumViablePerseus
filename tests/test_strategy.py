# tests/test_strategy.py
#
# Tests for ChunkingStrategy subclasses and StrategySelector.
#
# Three layers:
#   1. Unit tests for describes() against synthetic XML fixtures
#   2. Unit tests for StrategySelector.select() — strategy selection logic
#   3. Integration tests against known corpus files in tests/data/
#
# NOTE on StrategySelector._STRATEGIES: the current implementation uses
# a class-level list of pre-constructed instances.  Tests use the public
# select() interface throughout; they do not depend on the internal
# representation.

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mvp.document import TEIDocument
from mvp.strategy import (
    ChunkingStrategy,
    DivisionStrategy,
    MilestoneStrategy,
    StrategySelector,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"


def make_tei(body: str) -> str:
    """Return a minimal TEI document string with the given body content."""
    return textwrap.dedent(f"""\
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt>
                <title>Test</title><author>Test</author>
              </titleStmt>
              <publicationStmt><p>Test</p></publicationStmt>
              <sourceDesc><p>Test</p></sourceDesc>
            </fileDesc>
          </teiHeader>
          <text xml:lang="grc">
            <body>
              {body}
            </body>
          </text>
        </TEI>
    """)


def make_tei_with_hint(body: str, hint_unit: str) -> str:
    """Return a minimal TEI document with a <refState n='chunk'> hint."""
    return textwrap.dedent(f"""\
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt>
                <title>Test</title><author>Test</author>
              </titleStmt>
              <publicationStmt><p>Test</p></publicationStmt>
              <sourceDesc><p>Test</p></sourceDesc>
            </fileDesc>
            <encodingDesc>
              <refsDecl>
                <refState unit="work"/>
                <refState unit="{hint_unit}" n="chunk"/>
              </refsDecl>
            </encodingDesc>
          </teiHeader>
          <text xml:lang="lat">
            <body>
              {body}
            </body>
          </text>
        </TEI>
    """)


def write_doc(tmp_path: Path, body: str) -> TEIDocument:
    """Write a minimal TEI document with body and return a TEIDocument."""
    p = tmp_path / "test.xml"
    p.write_text(make_tei(body), encoding="utf-8")
    return TEIDocument.from_path(p)


def write_doc_with_hint(tmp_path: Path, body: str,
                        hint_unit: str) -> TEIDocument:
    """Write a TEI document with a refState chunk hint."""
    p = tmp_path / "test_hint.xml"
    p.write_text(make_tei_with_hint(body, hint_unit), encoding="utf-8")
    return TEIDocument.from_path(p)


# ---------------------------------------------------------------------------
# Body fragments for strategy detection
# ---------------------------------------------------------------------------

CARD_MILESTONES = """\
    <milestone unit="card" n="1"/>
    <p>text</p>
    <milestone unit="card" n="2"/>
"""

SECTION_MILESTONES = """\
    <milestone unit="section" n="1"/>
    <p>text</p>
    <milestone unit="section" n="2"/>
"""

LINE_MILESTONES = """\
    <milestone unit="line" n="1"/>
    <p>text</p>
    <milestone unit="line" n="2"/>
"""

# Division-based structure with no milestones — the pure Sophocles case
# (the real corpus file has both; this synthetic fixture isolates
# DivisionStrategy.describes() from MilestoneStrategy interference)
TEXTPART_DIVS_ONLY = """\
    <div type="edition" n="urn:cts:greekLit:tlg0011.tlg001.test">
      <div type="textpart" subtype="episode">
        <l n="1">line one</l>
        <l n="2">line two</l>
      </div>
      <div type="textpart" subtype="episode">
        <l n="3">line three</l>
      </div>
    </div>
"""

CHAPTER_DIVS_ONLY = """\
    <div type="edition" n="urn:cts:latinLit:phi2331.phi013.test">
      <div type="textpart" subtype="chapter" n="1">
        <p><milestone unit="section" n="1"/>first section of chapter one.</p>
      </div>
      <div type="textpart" subtype="chapter" n="2">
        <p><milestone unit="section" n="1"/>first section of chapter two.</p>
      </div>
    </div>
"""

BOOK_DIVS_ONLY = """\
    <div type="edition" n="urn:cts:greekLit:tlg9999.tlg001.test">
      <div type="book">
        <p>book one</p>
      </div>
      <div type="book">
        <p>book two</p>
      </div>
    </div>
"""

FEATURELESS = "<p>plain prose, no milestones or structural divs</p>"


# ---------------------------------------------------------------------------
# Layer 1: Unit tests for describes() against synthetic fixtures
# ---------------------------------------------------------------------------

class TestMilestoneStrategyDescribes:

    def test_card_describes_card_doc(self, tmp_path):
        doc = write_doc(tmp_path, CARD_MILESTONES)
        assert MilestoneStrategy(unit="card").describes(doc)

    def test_card_does_not_describe_section_doc(self, tmp_path):
        doc = write_doc(tmp_path, SECTION_MILESTONES)
        assert not MilestoneStrategy(unit="card").describes(doc)

    def test_section_describes_section_doc(self, tmp_path):
        doc = write_doc(tmp_path, SECTION_MILESTONES)
        assert MilestoneStrategy(unit="section").describes(doc)

    def test_section_does_not_describe_card_doc(self, tmp_path):
        doc = write_doc(tmp_path, CARD_MILESTONES)
        assert not MilestoneStrategy(unit="section").describes(doc)

    def test_line_describes_line_doc(self, tmp_path):
        doc = write_doc(tmp_path, LINE_MILESTONES)
        assert MilestoneStrategy(unit="line").describes(doc)

    def test_milestone_strategy_does_not_describe_featureless(self, tmp_path):
        doc = write_doc(tmp_path, FEATURELESS)
        assert not MilestoneStrategy(unit="card").describes(doc)
        assert not MilestoneStrategy(unit="section").describes(doc)
        assert not MilestoneStrategy(unit="line").describes(doc)

    def test_chunk_unit_reflects_constructor_argument(self):
        assert MilestoneStrategy(unit="card").chunk_unit == "card"
        assert MilestoneStrategy(unit="section").chunk_unit == "section"
        assert MilestoneStrategy(unit="line").chunk_unit == "line"


class TestDivisionStrategyDescribes:

    def test_textpart_describes_textpart_doc(self, tmp_path):
        doc = write_doc(tmp_path, TEXTPART_DIVS_ONLY)
        assert DivisionStrategy(div_type="textpart").describes(doc)

    def test_book_describes_book_doc(self, tmp_path):
        doc = write_doc(tmp_path, BOOK_DIVS_ONLY)
        assert DivisionStrategy(div_type="book").describes(doc)

    def test_textpart_does_not_describe_book_doc(self, tmp_path):
        doc = write_doc(tmp_path, BOOK_DIVS_ONLY)
        assert not DivisionStrategy(div_type="textpart").describes(doc)

    def test_division_strategy_does_not_describe_featureless(self, tmp_path):
        doc = write_doc(tmp_path, FEATURELESS)
        assert not DivisionStrategy(div_type="textpart").describes(doc)

    def test_chunk_unit_reflects_div_type_when_no_subtype(self):
        assert DivisionStrategy(div_type="textpart").chunk_unit == "textpart"
        assert DivisionStrategy(div_type="book").chunk_unit == "book"

    def test_chunk_unit_reflects_subtype_when_given(self):
        assert DivisionStrategy(div_type="textpart",
                                subtype="chapter").chunk_unit == "chapter"
        assert DivisionStrategy(div_type="textpart",
                                subtype="scene").chunk_unit == "scene"

    def test_subtype_filter_matches_chapter_divs(self, tmp_path):
        doc = write_doc(tmp_path, CHAPTER_DIVS_ONLY)
        assert DivisionStrategy(div_type="textpart",
                                subtype="chapter").describes(doc)

    def test_subtype_filter_does_not_match_wrong_subtype(self, tmp_path):
        doc = write_doc(tmp_path, CHAPTER_DIVS_ONLY)
        assert not DivisionStrategy(div_type="textpart",
                                    subtype="scene").describes(doc)

    def test_xslt_stylesheet_returns_generate_div_chunks(self):
        assert DivisionStrategy(div_type="textpart").xslt_stylesheet == \
            "html/generate_div_chunks.xsl"


class TestChunkingStrategyIsAbstract:

    def test_cannot_instantiate_base_class(self):
        with pytest.raises(TypeError):
            ChunkingStrategy()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Layer 2: StrategySelector.select()
# ---------------------------------------------------------------------------

class TestStrategySelectorSelect:

    @pytest.fixture
    def selector(self):
        return StrategySelector()

    def test_selects_card_milestone_strategy(self, tmp_path, selector):
        doc = write_doc(tmp_path, CARD_MILESTONES)
        strategy = selector.select(doc)
        assert isinstance(strategy, MilestoneStrategy)
        assert strategy.chunk_unit == "card"

    def test_selects_section_milestone_strategy(self, tmp_path, selector):
        doc = write_doc(tmp_path, SECTION_MILESTONES)
        strategy = selector.select(doc)
        assert isinstance(strategy, MilestoneStrategy)
        assert strategy.chunk_unit == "section"

    def test_selects_line_milestone_strategy(self, tmp_path, selector):
        doc = write_doc(tmp_path, LINE_MILESTONES)
        strategy = selector.select(doc)
        assert isinstance(strategy, MilestoneStrategy)
        assert strategy.chunk_unit == "line"

    def test_selects_division_strategy_for_textpart_only_document(
            self, tmp_path, selector):
        doc = write_doc(tmp_path, TEXTPART_DIVS_ONLY)
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "episode"

    def test_selects_division_strategy_for_book_div_only_document(
            self, tmp_path, selector):
        doc = write_doc(tmp_path, BOOK_DIVS_ONLY)
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "book"

    def test_hint_overrides_section_milestone(self, tmp_path, selector):
        """A chapter hint causes DivisionStrategy to win over section milestones."""
        doc = write_doc_with_hint(tmp_path, CHAPTER_DIVS_ONLY, hint_unit="chapter")
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "chapter"

    def test_hint_card_selects_card_milestone(self, tmp_path, selector):
        """A card hint selects MilestoneStrategy(card) when card milestones exist."""
        doc = write_doc_with_hint(tmp_path, CARD_MILESTONES, hint_unit="card")
        strategy = selector.select(doc)
        assert isinstance(strategy, MilestoneStrategy)
        assert strategy.chunk_unit == "card"

    def test_no_hint_selects_div_over_embedded_milestones(self, tmp_path, selector):
        """Without a hint, chapter divs win over embedded section milestones.

        CHAPTER_DIVS_ONLY has <milestone unit='section'> inside each chapter
        div.  The old ordered-list implementation incorrectly picked
        MilestoneStrategy(section); the heuristic now correctly prefers the
        structural div level.
        """
        doc = write_doc(tmp_path, CHAPTER_DIVS_ONLY)
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "chapter"

    def test_raises_for_featureless_document(self, tmp_path, selector):
        doc = write_doc(tmp_path, FEATURELESS)
        with pytest.raises(ValueError, match="No chunking strategy"):
            selector.select(doc)

    def test_card_takes_precedence_over_section(self, tmp_path, selector):
        """A document with both card and section milestones gets card.

        This tests the ordering guarantee of _STRATEGIES: card is tried
        before section.
        """
        body = CARD_MILESTONES + "\n" + SECTION_MILESTONES
        doc = write_doc(tmp_path, body)
        strategy = selector.select(doc)
        assert strategy.chunk_unit == "card"

    def test_div_takes_precedence_over_card_milestone(self, tmp_path, selector):
        """A document with both card milestones and textpart divs gets DivisionStrategy.

        Divs-with-subtypes always win over milestones in the current heuristic.
        A future iteration will allow card milestones to win for texts like
        Sophocles where that is more appropriate.
        See #refactor-strategy-selector for the deferred relaxation.
        """
        body = CARD_MILESTONES + "\n" + TEXTPART_DIVS_ONLY
        doc = write_doc(tmp_path, body)
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)

    def test_returns_chunking_strategy_instance(self, tmp_path, selector):
        doc = write_doc(tmp_path, CARD_MILESTONES)
        strategy = selector.select(doc)
        assert isinstance(strategy, ChunkingStrategy)


# ---------------------------------------------------------------------------
# Layer 3: Integration tests against known corpus files
# ---------------------------------------------------------------------------

class TestStrategySelectorOnCorpusFixtures:
    """Strategy selection against the real TEI fixtures in tests/data/.

    These assertions reflect the *current* behavior of the selector
    against the actual corpus files, including known encoding quirks.
    """

    @pytest.fixture(scope="class")
    def selector(self):
        return StrategySelector()

    def test_seneca_agamemnon_gets_card(self, selector):
        """phi1017.phi007 -- Latin drama, card milestones."""
        doc = TEIDocument.from_path(
            DATA_DIR / "phi1017.phi007.perseus-lat2.xml"
        )
        strategy = selector.select(doc)
        assert isinstance(strategy, MilestoneStrategy)
        assert strategy.chunk_unit == "card"

    def test_sophocles_trachiniae_gets_division_strategy(self, selector):
        """tlg0011.tlg001 -- Greek drama.

        The file contains both card milestones and div[@type='textpart'].
        Under the current heuristic, divs-with-subtypes always win, so
        the selector returns a DivisionStrategy.  A future iteration will
        revisit whether card milestones should win for texts like this;
        see #refactor-strategy-selector.
        """
        doc = TEIDocument.from_path(
            DATA_DIR / "tlg0011.tlg001.perseus-grc2.xml"
        )
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)

    def test_galen_gets_division_strategy(self, selector):
        """tlg0057.tlg069 -- Greek prose, Galenus verbatim revised encoding.

        This file has div[@type='textpart'] structure (9 sections).  The
        milestone units present -- ed1page and ed2page -- are bibliographic
        apparatus, not chunking boundaries.  DivisionStrategy(textpart) is
        the correct selection now that generate_div_chunks.xsl is implemented.
        """
        doc = TEIDocument.from_path(
            DATA_DIR / "tlg0057.tlg069.1st1K-grc1.xml"
        )
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "chapter"

    def test_caracallus_gets_chapter_division_strategy(self, selector):
        """phi2331.phi013 -- SHA Antoninus Caracallus.

        Has <refState unit='chapter' n='chunk'> in the header and
        div[@type='textpart'][@subtype='chapter'] in the body.  The hint
        should steer selection to DivisionStrategy(textpart, subtype=chapter).
        """
        doc = TEIDocument.from_path(
            DATA_DIR / "phi2331.phi013.perseus-lat2.xml"
        )
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "chapter"


# ---------------------------------------------------------------------------
# Layer 4: Heuristic-specific unit tests
# ---------------------------------------------------------------------------

# Body fixtures for heuristic tests
# Each chapter div has ~50 chars of direct text — below MIN_CHUNK_CHARS.
SMALL_CHAPTER_DIVS = """\
    <div type="edition" n="urn:cts:latinLit:test.test.test">
      <div type="textpart" subtype="chapter" n="1">
        <p>Short.</p>
      </div>
      <div type="textpart" subtype="chapter" n="2">
        <p>Also short.</p>
      </div>
    </div>
"""

# Each book div has ~200+ chars — above MIN_CHUNK_CHARS.
LARGE_BOOK_DIVS = """\
    <div type="edition" n="urn:cts:latinLit:test.test.test2">
      <div type="textpart" subtype="book" n="1">
        <p>""" + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 4) + """</p>
      </div>
      <div type="textpart" subtype="book" n="2">
        <p>""" + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 4) + """</p>
      </div>
    </div>
"""

# Nested: outer book (large), inner chapter (large) — chapter is deeper.
NESTED_BOOK_CHAPTER = """\
    <div type="edition" n="urn:cts:latinLit:test.test.test3">
      <div type="textpart" subtype="book" n="1">
        <div type="textpart" subtype="chapter" n="1">
          <p>""" + ("Chapter text with enough content to pass the size filter. " * 3) + """</p>
        </div>
        <div type="textpart" subtype="chapter" n="2">
          <p>""" + ("Chapter text with enough content to pass the size filter. " * 3) + """</p>
        </div>
      </div>
    </div>
"""


# One huge div (> MAX_CHUNK_CHARS) plus card milestones — tests Gap 1 fix.
_LONG_TEXT = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 150
HUGE_SINGLE_DIV = f"""\
    <div type="edition" n="urn:cts:latinLit:test.test.test4">
      <div type="textpart" subtype="book" n="1">
        <p>{_LONG_TEXT}</p>
      </div>
    </div>
    <milestone unit="card" n="1"/>
    <p>some text</p>
    <milestone unit="card" n="2"/>
"""

# Many distinct one-off subtypes for the same div type — tests Gap 2 fix.
FLAT_DRAMA = """\
    <div type="edition" n="urn:cts:greekLit:test.test.test5">
      <div type="textpart" subtype="Prologue">
        <p>""" + ("Prologue text. " * 20) + """</p>
      </div>
      <div type="textpart" subtype="Parodos">
        <p>""" + ("Parodos text. " * 20) + """</p>
      </div>
      <div type="textpart" subtype="Episode1">
        <p>""" + ("Episode one text. " * 20) + """</p>
      </div>
      <div type="textpart" subtype="Stasimon1">
        <p>""" + ("Stasimon one text. " * 20) + """</p>
      </div>
      <div type="textpart" subtype="Episode2">
        <p>""" + ("Episode two text. " * 20) + """</p>
      </div>
      <div type="textpart" subtype="Stasimon2">
        <p>""" + ("Stasimon two text. " * 20) + """</p>
      </div>
      <div type="textpart" subtype="Exodos">
        <p>""" + ("Exodos text. " * 20) + """</p>
      </div>
    </div>
"""


class TestStrategySelectorHeuristic:
    """Tests for the structural heuristic introduced in #refactor-strategy-selector."""

    @pytest.fixture
    def selector(self):
        return StrategySelector()

    def test_div_with_subtype_beats_milestone(self, tmp_path, selector):
        """A div-with-subtype always wins over any milestone, even card."""
        body = CARD_MILESTONES + "\n" + LARGE_BOOK_DIVS
        doc = write_doc(tmp_path, body)
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)

    def test_size_filter_small_falls_back_to_deepest(self, tmp_path, selector):
        """When all div candidates are below MIN_CHUNK_CHARS, fall back to deepest."""
        doc = write_doc(tmp_path, SMALL_CHAPTER_DIVS)
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "chapter"

    def test_large_divs_pass_size_filter(self, tmp_path, selector):
        """Div candidates above MIN_CHUNK_CHARS pass the filter and are selected."""
        doc = write_doc(tmp_path, LARGE_BOOK_DIVS)
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "book"

    def test_deepest_surviving_div_is_chosen(self, tmp_path, selector):
        """With nested book > chapter, chapter (deeper) is preferred."""
        doc = write_doc(tmp_path, NESTED_BOOK_CHAPTER)
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "chapter"

    # --- Gap 1: too-large divs fall through to milestones ---

    def test_single_too_large_div_falls_through_to_milestones(
            self, tmp_path, selector):
        """A single div >> MAX_CHUNK_CHARS falls through to card milestones.

        Covers the Argonautica case: one book-level div wraps the entire text
        and is far too large to be a useful chunk.  Milestone chunking wins.
        """
        doc = write_doc(tmp_path, HUGE_SINGLE_DIV)
        strategy = selector.select(doc)
        assert isinstance(strategy, MilestoneStrategy)
        assert strategy.chunk_unit == "card"

    # --- Gap 2: flat drama collapses to type-level chunking ---

    def test_flat_drama_collapses_to_type_level(self, tmp_path, selector):
        """Many distinct one-off subtypes collapse to DivisionStrategy with no subtype.

        When a div type has > MAX_SUBTYPES_PER_DIV_TYPE distinct subtypes,
        chunking at any one subtype would miss all the others.  The heuristic
        collapses to type-level chunking instead, so the XSLT chunks at every
        <div type='textpart'> regardless of subtype.
        """
        doc = write_doc(tmp_path, FLAT_DRAMA)
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "textpart"  # no subtype filter

    def test_select_all_returns_list(self, tmp_path, selector):
        """select_all() returns a non-empty list for a document with multiple axes."""
        body = CARD_MILESTONES + "\n" + LARGE_BOOK_DIVS
        doc = write_doc(tmp_path, body)
        strategies = selector.select_all(doc)
        assert isinstance(strategies, list)
        assert len(strategies) >= 1

    def test_select_all_includes_div_strategy(self, tmp_path, selector):
        """select_all() includes the DivisionStrategy for a div-structured doc."""
        doc = write_doc(tmp_path, LARGE_BOOK_DIVS)
        strategies = selector.select_all(doc)
        assert any(isinstance(s, DivisionStrategy) for s in strategies)

    def test_select_all_empty_for_featureless_doc(self, tmp_path, selector):
        """select_all() returns an empty list when nothing matches."""
        doc = write_doc(tmp_path, FEATURELESS)
        strategies = selector.select_all(doc)
        assert strategies == []

    def test_milestone_fallback_used_when_no_content_divs_at_all(
            self, tmp_path, selector):
        """Milestone fallback fires only when there are NO content divs (only edition div)."""
        body = """\
            <div type="edition" n="urn:cts:greekLit:test.test.test">
              <milestone unit="card" n="1"/>
              <p>text</p>
            </div>
        """
        doc = write_doc(tmp_path, body)
        strategy = selector.select(doc)
        assert isinstance(strategy, MilestoneStrategy)
        assert strategy.chunk_unit == "card"


# ---------------------------------------------------------------------------
# Layer 5: Integration tests against structure-data corpus fixtures
# ---------------------------------------------------------------------------

STRUCTURE_DATA_DIR = Path(__file__).parent / "data" / "structure-data"


@pytest.mark.skipif(
    not STRUCTURE_DATA_DIR.exists(),
    reason="tests/data/structure-data/ not yet populated",
)
class TestStrategySelectorOnStructureData:
    """Strategy selection against the four representative corpus fixtures.

    Files in tests/data/structure-data/ and the rationale for each result:

    my-argonautica-grc.xml
        1 book-level div (entire text — >> MAX_CHUNK_CHARS) + 23 card milestones.
        The single book div is too large to be a useful chunk, so it falls
        through to milestone fallback.  Gap 1 fix.

    poetics-grc.xml (Aristotle Poetics, tlg0086.tlg034)
        26 chapter divs with no subtype + bibliographic milestones (page, column,
        line).  Chapter divs pass the size filter; bibliographic milestones are
        never reached.  Demonstrates correct structural preference.

    tlg0012.tlg001.perseus-grc2.xml (Homer Iliad)
        24 Book divs (each >> MAX_CHUNK_CHARS) + 425 card milestones.
        Like Argonautica: book-level divs are too large; card milestones win.
        NOTE: This file does NOT represent the Politics-like "section milestones
        inside structural divs" case.  A Politics file should be added to cover
        that primary bug fix.

    tlg0019.tlg005.perseus-grc2.xml (Aristophanes, a comedy)
        23 distinct textpart subtypes (Prologue, Episode, Parodos, Exodos …),
        each appearing 1-8 times.  Exceeds MAX_SUBTYPES_PER_DIV_TYPE so the
        heuristic collapses to type-level chunking.  Gap 2 fix.
    """

    @pytest.fixture(scope="class")
    def selector(self):
        return StrategySelector()

    def test_argonautica_gets_card_milestone(self, selector):
        """my-argonautica-grc.xml — single too-large book div falls through to card."""
        doc = TEIDocument.from_path(
            STRUCTURE_DATA_DIR / "my-argonautica-grc.xml"
        )
        strategy = selector.select(doc)
        assert isinstance(strategy, MilestoneStrategy)
        assert strategy.chunk_unit == "card"

    def test_poetics_gets_chapter_division(self, selector):
        """poetics-grc.xml — 26 chapter divs selected over bibliographic milestones."""
        doc = TEIDocument.from_path(
            STRUCTURE_DATA_DIR / "poetics-grc.xml"
        )
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "chapter"

    def test_iliad_gets_card_milestone(self, selector):
        """tlg0012 (Iliad) — 24 Book divs too large; 425 card milestones win."""
        doc = TEIDocument.from_path(
            STRUCTURE_DATA_DIR / "tlg0012.tlg001.perseus-grc2.xml"
        )
        strategy = selector.select(doc)
        assert isinstance(strategy, MilestoneStrategy)
        assert strategy.chunk_unit == "card"

    def test_aristophanes_gets_textpart_division(self, selector):
        """tlg0019 (Aristophanes) — 23 distinct subtypes collapse to textpart level."""
        doc = TEIDocument.from_path(
            STRUCTURE_DATA_DIR / "tlg0019.tlg005.perseus-grc2.xml"
        )
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "textpart"

    def test_politics_gets_bekker_page_division(self, selector):
        """tlg0086.tlg035 (Aristotle Politics) — primary bug-fix case.

        The Politics has section milestones inside a book > bekker_page div
        hierarchy.  The old selector picked MilestoneStrategy(section) because
        milestone detection ran first.  The new heuristic correctly prefers the
        bekker_page structural level: book divs have 4 chars of container
        whitespace, bekker_page divs have ~2100 chars of real text.
        """
        doc = TEIDocument.from_path(
            STRUCTURE_DATA_DIR / "tlg0086.tlg035.perseus-grc2.xml"
        )
        strategy = selector.select(doc)
        assert isinstance(strategy, DivisionStrategy)
        assert strategy.chunk_unit == "bekker_page"
