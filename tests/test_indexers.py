# tests/test_indexers.py
#
# Tests for WordIndexer and WordIndex.
#
# Three layers:
#   1. Unit tests against minimal synthetic XML fixtures
#   2. Regression tests for tail text and Greek elision
#   3. Integration test against a real corpus file

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from lxml import etree

from mvp.indexers import ChunkIndexer, WordIndexer
from mvp.models import ChunkIndex, ChunkOccurrence, WordIndex, WordOccurrence

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


class TestXpathFor:

    def test_returns_string(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        p_elem = indexer.root.find(f".//{{{NS}}}p")
        assert isinstance(indexer.xpath_for(p_elem), str)

    def test_path_starts_with_slash(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        p_elem = indexer.root.find(f".//{{{NS}}}p")
        assert indexer.xpath_for(p_elem).startswith("/")

    def test_path_uses_tei_prefix(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        p_elem = indexer.root.find(f".//{{{NS}}}p")
        assert "tei:" in indexer.xpath_for(p_elem)

    def test_path_ends_with_element_local_name(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        indexer = WordIndexer(path)
        p_elem = indexer.root.find(f".//{{{NS}}}p")
        result = indexer.xpath_for(p_elem)
        assert result.endswith("]")
        assert "tei:p[" in result

    def test_sibling_position_increments(self, tmp_path):
        body = "<p>first</p><p>second</p><p>third</p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        # Scope to body to avoid <p> elements in teiHeader
        body_elem = indexer.root.find(f".//{{{NS}}}body")
        paragraphs = body_elem.findall(f"{{{NS}}}p")
        assert len(paragraphs) == 3
        paths = [indexer.xpath_for(p) for p in paragraphs]
        assert "tei:p[1]" in paths[0]
        assert "tei:p[2]" in paths[1]
        assert "tei:p[3]" in paths[2]


class TestWordIndex:

    def test_returns_word_index_instance(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        indexer = WordIndexer(path)
        assert isinstance(indexer.word_index, WordIndex)

    def test_entries_is_dict(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        indexer = WordIndexer(path)
        assert isinstance(indexer.word_index.entries, dict)

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
        assert "hello" in indexer.word_index.entries
        assert "world" in indexer.word_index.entries

    def test_words_are_lowercased(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>Hello World</p>"))
        indexer = WordIndexer(path)
        assert "hello" in indexer.word_index.entries
        assert "world" in indexer.word_index.entries
        assert "Hello" not in indexer.word_index.entries

    def test_values_are_sets_of_word_occurrences(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        indexer = WordIndexer(path)
        locations = indexer.word_index.entries["hello"]
        assert isinstance(locations, set)
        assert all(isinstance(loc, WordOccurrence) for loc in locations)

    def test_same_word_in_multiple_locations(self, tmp_path):
        body = "<p>word one</p><p>word two</p>"
        path = write_tei(tmp_path, make_tei(body))
        indexer = WordIndexer(path)
        assert len(indexer.word_index.entries["word"]) == 2

    def test_empty_body_returns_empty_entries(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p></p>"))
        indexer = WordIndexer(path)
        assert indexer.word_index.entries == {}

    def test_whitespace_only_text_not_indexed(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>   </p>"))
        indexer = WordIndexer(path)
        assert indexer.word_index.entries == {}

    def test_punctuation_only_not_indexed(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>... --- .</p>"))
        indexer = WordIndexer(path)
        assert indexer.word_index.entries == {}


class TestExclusions:

    def test_tei_header_words_excluded(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>body</p>"))
        entries = indexer = WordIndexer(path).word_index.entries
        # "Test" and "Author" come from teiHeader — must not appear
        assert "test" not in entries
        assert "author" not in entries

    def test_del_words_excluded(self, tmp_path):
        # "after" is in a separate <p> so it hits elem.text, not a tail
        body = "<p>keep</p><del>deleted</del><p>after</p>"
        path = write_tei(tmp_path, make_tei(body))
        entries = WordIndexer(path).word_index.entries
        assert "deleted" not in entries
        assert "keep" in entries
        assert "after" in entries

    def test_note_words_excluded(self, tmp_path):
        body = "<p>text <note>editorial note</note></p>"
        path = write_tei(tmp_path, make_tei(body))
        entries = WordIndexer(path).word_index.entries
        assert "editorial" not in entries
        assert "note" not in entries
        assert "text" in entries

    def test_rdg_words_excluded(self, tmp_path):
        body = "<p>text <app><rdg>variant</rdg></app></p>"
        path = write_tei(tmp_path, make_tei(body))
        entries = WordIndexer(path).word_index.entries
        assert "variant" not in entries

    def test_nested_exclusion_excludes_descendants(self, tmp_path):
        body = "<note><p>deeply nested excluded text</p></note>"
        path = write_tei(tmp_path, make_tei(body))
        entries = WordIndexer(path).word_index.entries
        assert "deeply" not in entries
        assert "nested" not in entries

    def test_bibl_words_excluded(self, tmp_path):
        body = "<p>prose <bibl>Hom. Il. 1.1</bibl></p>"
        path = write_tei(tmp_path, make_tei(body))
        entries = WordIndexer(path).word_index.entries
        assert "hom" not in entries
        assert "prose" in entries


# ---------------------------------------------------------------------------
# Layer 2: Regression tests for tail text and Greek elision
# ---------------------------------------------------------------------------

class TestTailText:

    def test_tail_text_collected(self, tmp_path):
        body = "<p><hi>head</hi>tail word</p>"
        path = write_tei(tmp_path, make_tei(body))
        entries = WordIndexer(path).word_index.entries
        assert "tail" in entries
        assert "word" in entries

    def test_tail_attributed_to_parent(self, tmp_path):
        body = "<p><hi>head</hi>tail</p>"
        path = write_tei(tmp_path, make_tei(body))
        entries = WordIndexer(path).word_index.entries
        # "tail" is in <hi>.tail but logically belongs to <p>
        locations = entries["tail"]
        assert all("tei:p[" in loc.xpath for loc in locations)

    def test_tail_after_excluded_element_is_indexed(self, tmp_path):
        # "this" sits in <del>.tail — it belongs to <p>, not <del>
        body = "<p>keep <del>deleted</del> this</p>"
        path = write_tei(tmp_path, make_tei(body))
        entries = WordIndexer(path).word_index.entries
        assert "deleted" not in entries
        assert "keep" in entries
        assert "this" in entries


class TestGreekElision:

    def test_u2019_apostrophe_matched(self, tmp_path):
        body = "<p>αλλ'</p>"  # αλλ' with U+2019
        path = write_tei(tmp_path, make_tei(body))
        entries = WordIndexer(path).word_index.entries
        assert "αλλ'" in entries

    def test_ascii_apostrophe_matched(self, tmp_path):
        body = "<p>don't</p>"
        path = write_tei(tmp_path, make_tei(body))
        entries = WordIndexer(path).word_index.entries
        assert "don't" in entries


# ---------------------------------------------------------------------------
# ChunkIndexer tests
# ---------------------------------------------------------------------------

class TestChunkIndexer:

    def test_returns_chunk_index(self, tmp_path):
        body = "<p>first paragraph</p><p>second paragraph</p>"
        path = write_tei(tmp_path, make_tei(body))
        result = ChunkIndexer(path).chunk_index
        assert isinstance(result, ChunkIndex)

    def test_entries_are_chunk_occurrences(self, tmp_path):
        body = "<p>hello world</p>"
        path = write_tei(tmp_path, make_tei(body))
        result = ChunkIndexer(path).chunk_index
        assert all(isinstance(e, ChunkOccurrence) for e in result.entries)

    def test_chunk_text_content(self, tmp_path):
        body = "<p>hello world</p>"
        path = write_tei(tmp_path, make_tei(body))
        result = ChunkIndexer(path).chunk_index
        texts = [e.chunk for e in result.entries]
        assert "hello world" in texts

    def test_chunk_xpath_starts_with_slash(self, tmp_path):
        body = "<p>hello</p>"
        path = write_tei(tmp_path, make_tei(body))
        result = ChunkIndexer(path).chunk_index
        assert all(e.xpath.startswith("/") for e in result.entries)

    def test_multiple_paragraphs_produce_multiple_chunks(self, tmp_path):
        body = "<p>first</p><p>second</p><p>third</p>"
        path = write_tei(tmp_path, make_tei(body))
        result = ChunkIndexer(path).chunk_index
        texts = [e.chunk for e in result.entries]
        assert "first" in texts
        assert "second" in texts
        assert "third" in texts

    def test_excluded_content_stripped_from_chunk(self, tmp_path):
        body = "<p>keep <del>deleted</del> this</p>"
        path = write_tei(tmp_path, make_tei(body))
        result = ChunkIndexer(path).chunk_index
        body_chunk = next(e for e in result.entries if "tei:body" in e.xpath)
        assert "deleted" not in body_chunk.chunk
        assert "keep" in body_chunk.chunk

    def test_tail_after_excluded_element_preserved(self, tmp_path):
        # "this" is in <del>.tail — must appear in the chunk despite <del> being excluded
        body = "<p>keep <del>deleted</del> this</p>"
        path = write_tei(tmp_path, make_tei(body))
        result = ChunkIndexer(path).chunk_index
        body_chunk = next(e for e in result.entries if "tei:body" in e.xpath)
        assert "this" in body_chunk.chunk

    def test_empty_chunks_omitted(self, tmp_path):
        body = "<p></p><p>content</p>"
        path = write_tei(tmp_path, make_tei(body))
        result = ChunkIndexer(path).chunk_index
        assert all(e.chunk.strip() for e in result.entries)

    def test_verse_lines_chunked(self, tmp_path):
        body = "<lg><l>first line</l><l>second line</l></lg>"
        path = write_tei(tmp_path, make_tei(body))
        result = ChunkIndexer(path).chunk_index
        texts = [e.chunk for e in result.entries]
        assert any("first line" in t for t in texts)
        assert any("second line" in t for t in texts)

    def test_tei_header_excluded(self, tmp_path):
        body = "<p>body text</p>"
        path = write_tei(tmp_path, make_tei(body))
        result = ChunkIndexer(path).chunk_index
        # "Test" and "Author" live in teiHeader — must not appear in any chunk
        all_text = " ".join(e.chunk for e in result.entries)
        assert "Author" not in all_text


# ---------------------------------------------------------------------------
# Layer 3: Integration test against real corpus file
# ---------------------------------------------------------------------------

class TestArgonauticaIntegration:
    """tlg0001.tlg001.perseus-grc2.xml — Greek verse."""

    @pytest.fixture(scope="class")
    def word_index(self):
        path = DATA_DIR / "tlg0001.tlg001.perseus-grc2.xml"
        return WordIndexer(path).word_index

    def test_returns_word_index_instance(self, word_index):
        assert isinstance(word_index, WordIndex)

    def test_entries_is_nonempty(self, word_index):
        assert len(word_index.entries) > 0

    def test_all_keys_are_lowercase(self, word_index):
        for key in word_index.entries:
            assert key == key.lower(), f"Key not lowercase: {key!r}"

    def test_all_values_are_nonempty_sets(self, word_index):
        for word, locations in word_index.entries.items():
            assert isinstance(locations, set), f"{word!r}: expected set"
            assert len(locations) > 0, f"{word!r}: empty location set"

    def test_all_locations_are_word_occurrences(self, word_index):
        for word, locations in word_index.entries.items():
            for loc in locations:
                assert isinstance(loc, WordOccurrence), f"{word!r}: expected WordOccurrence"

    def test_occurrence_xpaths_start_with_slash(self, word_index):
        for word, locations in word_index.entries.items():
            for loc in locations:
                assert loc.xpath.startswith("/"), f"{word!r}: {loc.xpath!r} missing leading slash"

    def test_occurrence_spans_are_valid(self, word_index):
        for word, locations in word_index.entries.items():
            for loc in locations:
                assert loc.start >= 0, f"{word!r}: negative start"
                assert loc.end > loc.start, f"{word!r}: end not after start"

    def test_tei_header_content_absent(self, word_index):
        # "apollonius" lives only in teiHeader — must be excluded
        assert "apollonius" not in word_index.entries
