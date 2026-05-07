# tests/test_indexers.py
#
# Tests for WordIndexer.
#
# Three layers:
#   1. Unit tests against minimal synthetic XML fixtures
#   2. Regression tests that expose known issues / gaps
#   3. Integration test against a real corpus file

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from lxml import etree

from mvp.indexers import WordIndexer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
NS = "http://www.tei-c.org/ns/1.0"


def make_tei(body: str) -> str:
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="{NS}">
          <teiHeader>
            <fileDesc>
              <titleStmt><title>Test</title><author>Author</author></titleStmt>
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


def write_tei(tmp_path: Path, xml: str) -> Path:
    p = tmp_path / "test.xml"
    p.write_text(xml, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Layer 1: Unit tests against synthetic fixtures
# ---------------------------------------------------------------------------

class TestWordIndexerInit:

    def test_accepts_path(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        assert indexer.doc == path

    def test_accepts_string(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(str(path))
        assert indexer.doc == str(path)

    def test_exclusion_set_contains_tei_namespace(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        assert f"{{{NS}}}teiHeader" in indexer.exclusions
        assert f"{{{NS}}}del" in indexer.exclusions
        assert f"{{{NS}}}note" in indexer.exclusions


class TestTreeLoading:

    def test_tree_is_lazy(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        assert indexer._tree is None

    def test_tree_loads_on_access(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        tree = indexer.tree
        assert tree is not None

    def test_tree_cached_after_first_access(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        t1 = indexer.tree
        t2 = indexer.tree
        assert t1 is t2

    def test_root_is_tei_element(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        assert etree.QName(indexer.root).localname == "TEI"


class TestGetTeiPath:

    def test_returns_string(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        p_elem = indexer.root.find(f".//{{{NS}}}p")
        result = indexer.get_tei_path(p_elem)
        assert isinstance(result, str)

    def test_path_starts_with_slash(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        p_elem = indexer.root.find(f".//{{{NS}}}p")
        assert indexer.get_tei_path(p_elem).startswith("/")

    def test_path_uses_tei_prefix(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        p_elem = indexer.root.find(f".//{{{NS}}}p")
        assert "tei:" in indexer.get_tei_path(p_elem)

    def test_path_ends_with_element_local_name(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        p_elem = indexer.root.find(f".//{{{NS}}}p")
        assert indexer.get_tei_path(p_elem).endswith("]")
        assert "tei:p[" in indexer.get_tei_path(p_elem)

    def test_sibling_position_increments(self, tmp_path):
        body = "<p>first</p><p>second</p><p>third</p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        # Scope to body to avoid <p> elements in teiHeader
        body_elem = indexer.root.find(f".//{{{NS}}}body")
        paragraphs = body_elem.findall(f"{{{NS}}}p")
        assert len(paragraphs) == 3
        paths = [indexer.get_tei_path(p) for p in paragraphs]
        assert "tei:p[1]" in paths[0]
        assert "tei:p[2]" in paths[1]
        assert "tei:p[3]" in paths[2]


class TestWordIndex:

    def test_returns_dict(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        indexer = WordIndexer(path)
        assert isinstance(indexer.word_index, dict)

    def test_cached_after_first_access(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        indexer = WordIndexer(path)
        i1 = indexer.word_index
        i2 = indexer.word_index
        assert i1 is i2

    def test_word_index_none_before_access(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        assert indexer._word_index is None

    def test_basic_word_extraction(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        indexer = WordIndexer(path)
        assert "hello" in indexer.word_index
        assert "world" in indexer.word_index

    def test_words_are_lowercased(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>Hello World</p>"))
        indexer = WordIndexer(path)
        assert "hello" in indexer.word_index
        assert "world" in indexer.word_index
        assert "Hello" not in indexer.word_index

    def test_values_are_sets(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        indexer = WordIndexer(path)
        assert isinstance(indexer.word_index["hello"], set)

    def test_same_word_in_multiple_locations(self, tmp_path):
        body = "<p>word one</p><p>word two</p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        assert len(indexer.word_index["word"]) == 2

    def test_empty_body_returns_empty_index(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p></p>"))
        indexer = WordIndexer(path)
        assert indexer.word_index == {}

    def test_whitespace_only_text_not_indexed(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>   </p>"))
        indexer = WordIndexer(path)
        assert indexer.word_index == {}

    def test_punctuation_only_not_indexed(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>... --- .</p>"))
        indexer = WordIndexer(path)
        assert indexer.word_index == {}


class TestExclusions:

    def test_tei_header_words_excluded(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>body</p>"))
        indexer = WordIndexer(path)
        index = indexer.word_index
        # "Test" and "Author" come from teiHeader — must not appear
        assert "test" not in index
        assert "author" not in index

    def test_del_words_excluded(self, tmp_path):
        # "after" is in a separate <p> so it hits elem.text, not a tail
        body = "<p>keep</p><del>deleted</del><p>after</p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        index = indexer.word_index
        assert "deleted" not in index
        assert "keep" in index
        assert "after" in index

    def test_note_words_excluded(self, tmp_path):
        body = "<p>text <note>editorial note</note></p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        index = indexer.word_index
        assert "editorial" not in index
        assert "note" not in index
        assert "text" in index

    def test_rdg_words_excluded(self, tmp_path):
        body = "<p>text <app><rdg>variant</rdg></app></p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        index = indexer.word_index
        assert "variant" not in index

    def test_nested_exclusion_excludes_descendants(self, tmp_path):
        body = "<note><p>deeply nested excluded text</p></note>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        index = indexer.word_index
        assert "deeply" not in index
        assert "nested" not in index

    def test_bibl_words_excluded(self, tmp_path):
        body = "<p>prose <bibl>Hom. Il. 1.1</bibl></p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        index = indexer.word_index
        assert "hom" not in index
        assert "prose" in index


# ---------------------------------------------------------------------------
# Layer 2: Regression tests for known gaps
# ---------------------------------------------------------------------------

class TestTailText:

    def test_tail_text_collected(self, tmp_path):
        body = "<p><hi>head</hi>tail word</p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        assert "tail" in indexer.word_index
        assert "word" in indexer.word_index

    def test_tail_attributed_to_parent(self, tmp_path):
        body = "<p><hi>head</hi>tail</p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        # "tail" is in <hi>.tail but logically belongs to <p>
        locations = indexer.word_index["tail"]
        assert all("tei:p[" in loc for loc in locations)

    def test_tail_after_excluded_element_is_indexed(self, tmp_path):
        # "this" sits in <del>.tail — it belongs to <p>, not <del>
        body = "<p>keep <del>deleted</del> this</p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        assert "deleted" not in indexer.word_index
        assert "keep" in indexer.word_index
        assert "this" in indexer.word_index


class TestGreekElision:

    def test_u2019_apostrophe_matched(self, tmp_path):
        body = "<p>αλλ’</p>"  # αλλ’ with U+2019
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        assert "αλλ’" in indexer.word_index

    def test_ascii_apostrophe_matched(self, tmp_path):
        body = "<p>don’t</p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        assert "don’t" in indexer.word_index


# ---------------------------------------------------------------------------
# Layer 3: Integration test against real corpus file
# ---------------------------------------------------------------------------

class TestArgonauticaIntegration:
    """tlg0001.tlg001.perseus-grc2.xml — Greek verse."""

    @pytest.fixture(scope="class")
    def index(self):
        path = DATA_DIR / "tlg0001.tlg001.perseus-grc2.xml"
        return WordIndexer(path).word_index

    def test_index_is_nonempty(self, index):
        assert len(index) > 0

    def test_all_keys_are_lowercase(self, index):
        for key in index:
            assert key == key.lower(), f"Key not lowercase: {key!r}"

    def test_all_values_are_nonempty_sets(self, index):
        for word, locations in index.items():
            assert isinstance(locations, set), f"{word!r}: expected set"
            assert len(locations) > 0, f"{word!r}: empty location set"

    def test_all_locations_are_strings(self, index):
        for word, locations in index.items():
            for loc in locations:
                assert isinstance(loc, str), f"{word!r}: non-string location"

    def test_locations_start_with_slash(self, index):
        for word, locations in index.items():
            for loc in locations:
                assert loc.startswith("/"), f"{word!r}: {loc!r} missing leading slash"

    def test_tei_header_content_absent(self, index):
        # "apollonius" lives only in teiHeader — must be excluded
        assert "apollonius" not in index
