# tests/test_index_serializers.py
#
# Tests for ChunkIndexSerializer and WordIndexSerializer.

from __future__ import annotations

import json
import textwrap
from pathlib import Path


from mvp.indexers.index_serializers import ChunkIndexSerializer, WordIndexSerializer
from mvp.indexers.indexers import ChunkIndexer, WordIndexer
from mvp.models import TEIMetadata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def make_meta(source_path: Path) -> TEIMetadata:
    return TEIMetadata(
        urn="urn:cts:greekLit:tlg0001.tlg001.perseus-grc2",
        title="Test Work",
        author="Test Author",
        language="grc",
        text_type="verse",
        source_path=source_path,
    )


# ---------------------------------------------------------------------------
# ChunkIndexSerializer
# ---------------------------------------------------------------------------

class TestChunkIndexSerializerGenerate:

    def test_returns_dict(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        assert isinstance(result, dict)

    def test_version_field(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        assert result["version"] == "1"

    def test_document_section_keys(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        doc = result["document"]
        assert "source_path" in doc
        assert "base_urn" in doc
        assert "language" in doc

    def test_document_base_urn(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        assert result["document"]["base_urn"] == "urn:cts:greekLit:tlg0001.tlg001.perseus-grc2"

    def test_document_language(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        assert result["document"]["language"] == "grc"

    def test_chunks_is_list(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        assert isinstance(result["chunks"], list)

    def test_chunk_entry_keys(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        chunk = result["chunks"][0]
        assert set(chunk.keys()) == {"xpath", "urn", "element", "text"}

    def test_chunk_text_not_chunk(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        chunk = result["chunks"][0]
        assert "text" in chunk
        assert "chunk" not in chunk

    def test_chunk_text_content(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        texts = [c["text"] for c in result["chunks"]]
        assert any("hello world" in t for t in texts)

    def test_chunk_element_field(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>text</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        p_chunk = next(c for c in result["chunks"] if "tei:p" in c["xpath"])
        assert p_chunk["element"] == "p"

    def test_chunk_urn_is_null(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>text</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        assert all(c["urn"] is None for c in result["chunks"])

    def test_multiple_chunks(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>first</p><p>second</p>"))
        index = ChunkIndexer(path).chunk_index
        result = ChunkIndexSerializer(index, make_meta(path)).generate()
        texts = [c["text"] for c in result["chunks"]]
        assert "first" in texts
        assert "second" in texts


class TestChunkIndexSerializerWrite:

    def test_writes_file(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = ChunkIndexer(path).chunk_index
        out = tmp_path / "out" / "chunks.json"
        ChunkIndexSerializer(index, make_meta(path)).write(out)
        assert out.exists()

    def test_creates_parent_dirs(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = ChunkIndexer(path).chunk_index
        out = tmp_path / "a" / "b" / "c" / "chunks.json"
        ChunkIndexSerializer(index, make_meta(path)).write(out)
        assert out.exists()

    def test_output_is_valid_json(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = ChunkIndexer(path).chunk_index
        out = tmp_path / "chunks.json"
        ChunkIndexSerializer(index, make_meta(path)).write(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "chunks" in data

    def test_output_preserves_unicode(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>ἄνδρα μοι ἔννεπε</p>"))
        index = ChunkIndexer(path).chunk_index
        out = tmp_path / "chunks.json"
        ChunkIndexSerializer(index, make_meta(path)).write(out)
        raw = out.read_text(encoding="utf-8")
        assert "ἄνδρα" in raw


# ---------------------------------------------------------------------------
# WordIndexSerializer
# ---------------------------------------------------------------------------

class TestWordIndexSerializerGenerate:

    def test_returns_list(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        index = WordIndexer(path).word_index
        result = WordIndexSerializer(index, make_meta(path)).generate()
        assert isinstance(result, list)

    def test_record_keys(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = WordIndexer(path).word_index
        result = WordIndexSerializer(index, make_meta(path)).generate()
        record = result[0]
        assert set(record.keys()) == {"word", "xpath", "urn", "start", "end"}

    def test_words_are_lowercase(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>Hello World</p>"))
        index = WordIndexer(path).word_index
        result = WordIndexSerializer(index, make_meta(path)).generate()
        for record in result:
            assert record["word"] == record["word"].lower()

    def test_urn_is_null(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = WordIndexer(path).word_index
        result = WordIndexSerializer(index, make_meta(path)).generate()
        assert all(r["urn"] is None for r in result)

    def test_start_end_are_integers(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = WordIndexer(path).word_index
        result = WordIndexSerializer(index, make_meta(path)).generate()
        for record in result:
            assert isinstance(record["start"], int)
            assert isinstance(record["end"], int)

    def test_sorted_by_xpath_then_start(self, tmp_path):
        body = "<p>first paragraph</p><p>second paragraph</p>"
        path = write_tei(tmp_path, make_tei(body))
        index = WordIndexer(path).word_index
        result = WordIndexSerializer(index, make_meta(path)).generate()
        keys = [(r["xpath"], r["start"]) for r in result]
        assert keys == sorted(keys)

    def test_all_words_present(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>alpha beta gamma</p>"))
        index = WordIndexer(path).word_index
        result = WordIndexSerializer(index, make_meta(path)).generate()
        words = {r["word"] for r in result}
        assert {"alpha", "beta", "gamma"} <= words


class TestWordIndexSerializerWrite:

    def test_writes_file(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = WordIndexer(path).word_index
        out = tmp_path / "out" / "words.jsonl"
        WordIndexSerializer(index, make_meta(path)).write(out)
        assert out.exists()

    def test_creates_parent_dirs(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello</p>"))
        index = WordIndexer(path).word_index
        out = tmp_path / "a" / "b" / "words.jsonl"
        WordIndexSerializer(index, make_meta(path)).write(out)
        assert out.exists()

    def test_each_line_is_valid_json(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>hello world</p>"))
        index = WordIndexer(path).word_index
        out = tmp_path / "words.jsonl"
        WordIndexSerializer(index, make_meta(path)).write(out)
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        for line in lines:
            record = json.loads(line)
            assert "word" in record

    def test_output_preserves_unicode(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>ἄνδρα μοι ἔννεπε</p>"))
        index = WordIndexer(path).word_index
        out = tmp_path / "words.jsonl"
        WordIndexSerializer(index, make_meta(path)).write(out)
        raw = out.read_text(encoding="utf-8")
        assert "ἄνδρα" in raw

    def test_line_count_equals_record_count(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>alpha beta gamma</p>"))
        index = WordIndexer(path).word_index
        serializer = WordIndexSerializer(index, make_meta(path))
        out = tmp_path / "words.jsonl"
        serializer.write(out)
        lines = [line for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == len(serializer.generate())
