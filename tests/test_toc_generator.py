"""Tests for TOCGenerator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mvp.corpus.toc_generator import TOCGenerator


BASE_URN = "urn:cts:greekLit:tlg0003.tlg001.perseus-grc2"


def _write_index(directory: Path, data: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _two_book_index(directory: Path) -> None:
    """2 books, 3 chapters each."""
    chunks = []
    for book in ("1", "2"):
        for ch in ("1", "2", "3"):
            chunks.append({
                "urn": f"{BASE_URN}:{book}.{ch}",
                "file": f"chunk_{book}.{ch}.xml",
                "book": book,
                "chapter": ch,
            })
    _write_index(directory, {
        "base_urn": BASE_URN,
        "title": "Ἱστορίαι",
        "language": "grc",
        "author": "Thucydides",
        "book_subtype": "book",
        "chapter_subtype": "chapter",
        "chunks": chunks,
    })


def _single_level_index(directory: Path) -> None:
    """Single-level: chapters only, no book_subtype in index."""
    chunks = [
        {"urn": f"{BASE_URN}:1", "file": "chunk_1.xml", "book": "1", "chapter": "1"},
        {"urn": f"{BASE_URN}:2", "file": "chunk_2.xml", "book": "1", "chapter": "2"},
    ]
    _write_index(directory, {
        "base_urn": BASE_URN,
        "title": "Demo",
        "language": "grc",
        "chapter_subtype": "section",
        "chunks": chunks,
    })


# ---------------------------------------------------------------------------
# Nested (two-level) TOC
# ---------------------------------------------------------------------------

class TestNestedTOC:

    def test_version_field(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()
        assert toc["version"] == "1"

    def test_document_block(self, tmp_path):
        _two_book_index(tmp_path)
        doc = TOCGenerator(tmp_path).generate()["document"]
        assert doc["base_urn"] == BASE_URN
        assert doc["title"] == "Ἱστορίαι"
        assert doc["author"] == "Thucydides"

    def test_top_level_has_two_books(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        assert len(toc) == 2

    def test_book_depth_is_zero(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        assert all(b["depth"] == 0 for b in toc)

    def test_book_index_is_one_based(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        assert [b["index"] for b in toc] == [1, 2]

    def test_book_label(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        assert toc[0]["label"] == "Book 1"
        assert toc[1]["label"] == "Book 2"

    def test_book_subtype(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        assert all(b["subtype"] == "book" for b in toc)

    def test_book_urn_constructed_from_base_urn(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        assert toc[0]["urn"] == f"{BASE_URN}:1"
        assert toc[1]["urn"] == f"{BASE_URN}:2"

    def test_each_book_has_three_chapters(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        for book in toc:
            assert len(book["subpassages"]) == 3

    def test_chapter_depth_is_one(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        for book in toc:
            assert all(ch["depth"] == 1 for ch in book["subpassages"])

    def test_chapter_index_restarts_per_book(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        for book in toc:
            assert [ch["index"] for ch in book["subpassages"]] == [1, 2, 3]

    def test_chapter_urn_from_index_json(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        assert toc[0]["subpassages"][0]["urn"] == f"{BASE_URN}:1.1"
        assert toc[1]["subpassages"][2]["urn"] == f"{BASE_URN}:2.3"

    def test_chapter_subpassages_always_present_and_empty(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        for book in toc:
            for ch in book["subpassages"]:
                assert "subpassages" in ch
                assert ch["subpassages"] == []

    def test_book_subpassages_always_present(self, tmp_path):
        _two_book_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        for book in toc:
            assert "subpassages" in book


# ---------------------------------------------------------------------------
# Single-level TOC
# ---------------------------------------------------------------------------

class TestSingleLevelTOC:

    def test_flat_toc_entries(self, tmp_path):
        _single_level_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        assert len(toc) == 2

    def test_flat_entries_depth_zero(self, tmp_path):
        _single_level_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        assert all(e["depth"] == 0 for e in toc)

    def test_flat_entries_use_chapter_subtype(self, tmp_path):
        _single_level_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        assert all(e["subtype"] == "section" for e in toc)

    def test_flat_entry_subpassages_present_and_empty(self, tmp_path):
        _single_level_index(tmp_path)
        toc = TOCGenerator(tmp_path).generate()["toc"]
        for entry in toc:
            assert "subpassages" in entry
            assert entry["subpassages"] == []


# ---------------------------------------------------------------------------
# Defaults when book_subtype / chapter_subtype absent
# ---------------------------------------------------------------------------

class TestDefaults:

    def test_defaults_to_book_chapter_labels(self, tmp_path):
        chunks = [
            {"urn": f"{BASE_URN}:1.1", "file": "chunk_1.1.xml", "book": "1", "chapter": "1"},
            {"urn": f"{BASE_URN}:2.1", "file": "chunk_2.1.xml", "book": "2", "chapter": "1"},
        ]
        _write_index(tmp_path, {
            "base_urn": BASE_URN,
            "title": "Test",
            "language": "grc",
            "chunks": chunks,
        })
        toc = TOCGenerator(tmp_path).generate()["toc"]
        # Two different books → nested mode
        assert toc[0]["subtype"] == "book"
        assert toc[0]["subpassages"][0]["subtype"] == "chapter"

    def test_author_defaults_to_empty_string(self, tmp_path):
        chunks = [
            {"urn": f"{BASE_URN}:1.1", "file": "chunk_1.1.xml", "book": "1", "chapter": "1"},
        ]
        _write_index(tmp_path, {
            "base_urn": BASE_URN,
            "title": "No Author",
            "language": "grc",
            "book_subtype": "book",
            "chapter_subtype": "chapter",
            "chunks": chunks,
        })
        doc = TOCGenerator(tmp_path).generate()["document"]
        assert doc["author"] == ""


# ---------------------------------------------------------------------------
# write() method
# ---------------------------------------------------------------------------

class TestWrite:

    def test_write_creates_toc_json(self, tmp_path):
        _two_book_index(tmp_path)
        TOCGenerator(tmp_path).write()
        assert (tmp_path / "toc.json").exists()

    def test_written_content_is_valid_json(self, tmp_path):
        _two_book_index(tmp_path)
        TOCGenerator(tmp_path).write()
        data = json.loads((tmp_path / "toc.json").read_text(encoding="utf-8"))
        assert "toc" in data

    def test_write_respects_custom_output_path(self, tmp_path):
        _two_book_index(tmp_path)
        out = tmp_path / "custom" / "my_toc.json"
        TOCGenerator(tmp_path).write(out)
        assert out.exists()

    def test_written_file_is_utf8(self, tmp_path):
        _two_book_index(tmp_path)
        TOCGenerator(tmp_path).write()
        raw = (tmp_path / "toc.json").read_bytes()
        text = raw.decode("utf-8")
        assert "Ἱστορίαι" in text
