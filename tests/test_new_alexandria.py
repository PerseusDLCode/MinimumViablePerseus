# tests/test_new_alexandria.py
#
# New Alexandria Commentaries (see mvp.site.new_alexandria) are Markdown
# commentaries fetched from three opencommentaries.org GitHub repos
# (src/tools/fetch_new_alexandria.py) that share differing frontmatter
# conventions but a common `@urn:cts:<workurn>:<citation>` entry-anchor
# line. These tests use trimmed fixtures modeled on the real Pausanias
# (list `authors:` + `base_urn:` + `## Scroll` headings + `subject
# heading(s):` lines + inline images) and Homer/Pindar (single `author:` +
# `:key: value` metadata lines, multiple work URNs per file) formats.

from __future__ import annotations

from pathlib import Path

from mvp.site.new_alexandria import (
    SOURCES,
    _authors_from_frontmatter,
    _parse_entries,
    _split_frontmatter,
    build_new_alexandria_index,
)

_PAUSANIAS_SOURCE = SOURCES[0]
_HOMER_SOURCE = SOURCES[1]

_PAUSANIAS_FIXTURE = """---
authors:
- Test Author
- "Editors: A and B"
base_urn: "urn:cts:greekLit:tlg0525.tlg001.apcip-nagy"
title: Test title
---

## Scroll I. Attica

---

@urn:cts:greekLit:tlg0525.tlg001.apcip-nagy:1.1.1

subject heading(s): test subject

§1.1. First entry text with an image.

<img src="/commentaries/img/media/image1.jpeg" style="width:1in" />

---

@urn:cts:greekLit:tlg0525.tlg001.apcip-nagy:1.2.1

§1.2. Second entry, still under Scroll I heading.
"""

_HOMER_FIXTURE = """---
author: Test Commentator
shortname: test
---

@urn:cts:greekLit:tlg0012.tlg001:10.1
:contributors: Someone Else
:citation_urn: urn:cts:CHS:Commentaries.TEST:Iliad.10.1.abc
:created_at: 2020-01-01T00:00:00.000Z
:updated_at: 2020-01-01T00:00:00.000Z

First comment body, book 10.

---

@urn:cts:greekLit:tlg0012.tlg002:1.1-1.5
:citation_urn: urn:cts:CHS:Commentaries.TEST:Iliad.2.1.xyz
:created_at: 2020-01-01T00:00:00.000Z
:updated_at: 2020-01-01T00:00:00.000Z

Second comment body, book 2 -- a different work than the entry above.
"""


def test_split_frontmatter_authors_list():
    frontmatter, body = _split_frontmatter(_PAUSANIAS_FIXTURE)
    assert _authors_from_frontmatter(frontmatter) == [
        "Test Author",
        "Editors: A and B",
    ]
    # The frontmatter block itself must not leak into the body.
    assert "base_urn" not in body
    assert body.startswith("\n## Scroll I. Attica")


def test_split_frontmatter_single_author():
    frontmatter, body = _split_frontmatter(_HOMER_FIXTURE)
    assert _authors_from_frontmatter(frontmatter) == ["Test Commentator"]
    assert frontmatter["shortname"] == "test"


def test_split_frontmatter_missing_returns_unchanged_body():
    text = "@urn:cts:greekLit:tlg0012.tlg001:1.1\n\nNo frontmatter here.\n"
    frontmatter, body = _split_frontmatter(text)
    assert frontmatter == {}
    assert body == text


def test_frontmatter_entry_separator_collision_not_mistaken_for_frontmatter():
    """The '---' right after '## Scroll I. Attica' is an entry separator,
    not a second frontmatter block -- only the file's very first '---'...
    '---' pair is frontmatter."""
    frontmatter, body = _split_frontmatter(_PAUSANIAS_FIXTURE)
    entries = _parse_entries(body, ["Test Author"], _PAUSANIAS_SOURCE, "test")
    assert len(entries) == 2
    assert entries[0].work_urn == "urn:cts:greekLit:tlg0525.tlg001.apcip-nagy"
    assert entries[0].citation == "1.1.1"


def test_parse_entries_section_tracking():
    frontmatter, body = _split_frontmatter(_PAUSANIAS_FIXTURE)
    entries = _parse_entries(body, ["Test Author"], _PAUSANIAS_SOURCE, "test")
    assert entries[0].section == "Scroll I. Attica"
    assert entries[1].section == "Scroll I. Attica"


def test_parse_entries_pausanias_subject_heading_not_treated_as_metadata():
    """'subject heading(s):' has no leading colon, so it isn't captured
    into `metadata` the way Homer/Pindar's ':key: value' lines are -- it
    stays as part of the rendered comment body."""
    frontmatter, body = _split_frontmatter(_PAUSANIAS_FIXTURE)
    entries = _parse_entries(body, ["Test Author"], _PAUSANIAS_SOURCE, "test")
    assert entries[0].metadata == {}
    assert "subject heading(s)" in entries[0].body_html


def test_parse_entries_rewrites_root_relative_image_src():
    frontmatter, body = _split_frontmatter(_PAUSANIAS_FIXTURE)
    entries = _parse_entries(body, ["Test Author"], _PAUSANIAS_SOURCE, "test")
    assert (
        'src="https://pausanias.opencommentaries.org/commentaries/img/media/image1.jpeg"'
        in entries[0].body_html
    )


def test_parse_entries_metadata_lines_captured_and_excluded_from_body():
    frontmatter, body = _split_frontmatter(_HOMER_FIXTURE)
    authors = _authors_from_frontmatter(frontmatter)
    entries = _parse_entries(body, authors, _HOMER_SOURCE, "test")
    assert entries[0].metadata == {
        "contributors": "Someone Else",
        "citation_urn": "urn:cts:CHS:Commentaries.TEST:Iliad.10.1.abc",
        "created_at": "2020-01-01T00:00:00.000Z",
        "updated_at": "2020-01-01T00:00:00.000Z",
    }
    assert "contributors" not in entries[0].body_html
    assert "First comment body, book 10." in entries[0].body_html


def test_parse_entries_multiple_work_urns_in_one_file():
    """A single Homer-style file's entries can span more than one work
    URN -- matching must be per-entry, not per-file."""
    frontmatter, body = _split_frontmatter(_HOMER_FIXTURE)
    authors = _authors_from_frontmatter(frontmatter)
    entries = _parse_entries(body, authors, _HOMER_SOURCE, "test")
    assert [e.work_urn for e in entries] == [
        "urn:cts:greekLit:tlg0012.tlg001",
        "urn:cts:greekLit:tlg0012.tlg002",
    ]
    assert [e.citation for e in entries] == ["10.1", "1.1-1.5"]


def _write_fixture(root: Path, repo_name: str, filename: str, text: str) -> None:
    repo_dir = root / repo_name
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / filename).write_text(text, encoding="utf-8")


def test_build_new_alexandria_index_none_returns_empty():
    index = build_new_alexandria_index(None)
    assert index.entries == []
    assert index.entries_for_passage("urn:cts:greekLit:tlg0012.tlg001", "10.1") == []


def test_build_new_alexandria_index_missing_dir_returns_empty(tmp_path):
    index = build_new_alexandria_index(tmp_path / "does-not-exist")
    assert index.entries == []


def test_build_new_alexandria_index_reads_fixture_directories(tmp_path):
    _write_fixture(
        tmp_path,
        "pausanias.opencommentaries.org",
        "test.md",
        _PAUSANIAS_FIXTURE,
    )
    _write_fixture(
        tmp_path,
        "homer.opencommentaries.org",
        "test.md",
        _HOMER_FIXTURE,
    )

    index = build_new_alexandria_index(tmp_path)
    assert len(index.entries) == 4


def test_entries_for_passage_matches_overlapping_work_and_citation(tmp_path):
    _write_fixture(
        tmp_path,
        "homer.opencommentaries.org",
        "test.md",
        _HOMER_FIXTURE,
    )
    index = build_new_alexandria_index(tmp_path)

    groups = index.entries_for_passage(
        "urn:cts:greekLit:tlg0012.tlg001", "10.1-10.5"
    )
    assert len(groups) == 1
    assert groups[0].label == "Test Commentator"
    assert len(groups[0].entries) == 1
    assert groups[0].entries[0].citation == "10.1"


def test_entries_for_passage_does_not_cross_match_different_work(tmp_path):
    _write_fixture(
        tmp_path,
        "homer.opencommentaries.org",
        "test.md",
        _HOMER_FIXTURE,
    )
    index = build_new_alexandria_index(tmp_path)

    # Book 10 entry must not appear when viewing book 2's passage, and
    # vice versa, even though both come from the same file/commentator.
    groups = index.entries_for_passage("urn:cts:greekLit:tlg0012.tlg002", "1.2")
    assert len(groups) == 1
    assert groups[0].entries[0].work_urn == "urn:cts:greekLit:tlg0012.tlg002"


def test_entries_for_passage_no_match_returns_empty(tmp_path):
    _write_fixture(
        tmp_path,
        "homer.opencommentaries.org",
        "test.md",
        _HOMER_FIXTURE,
    )
    index = build_new_alexandria_index(tmp_path)

    groups = index.entries_for_passage("urn:cts:greekLit:tlg0011.tlg001", "1.1")
    assert groups == []
