# tests/test_sibling_focus_url.py
#
# Regression test for the sibling "focus" link in reading.html.jinja
# (see _build_sibling_data / _focus_url in mvp.site.siblings).
#
# _build_sibling_data may resolve a sibling version's chunk from a
# citeStructure *scheme* subdirectory, to match the granularity the base
# text is currently being read at (e.g. base viewed "by card"). That
# scheme-specific index.json can chunk the sibling differently than its
# own default index.json. The focus link used to be built as a bare
# `/{{ sib_chunk.cts_urn }}` href, which always routes through the
# scheme-less `reading_view` endpoint and resolves against the sibling's
# *default* index — landing on a 404 or the wrong-bounded chunk whenever
# the scheme-specific chunking differs. The fix threads the scheme the
# chunk was actually read under into the link (via url_for), matching how
# NavigationItem.html.jinja and _redirect_to_first_chunk build reading-view
# links elsewhere.

from __future__ import annotations

import json
from pathlib import Path

import pytest
from perseus_cts.models import CTSVersion

from mvp.site import app as appmod
from mvp.site import chunks as chunksmod
from mvp.site import config
from mvp.site import siblings as siblingsmod
from mvp.site.chunks import _Chunk, _chunk_end_line, _chunk_start_line


CORPUS, TEXTGROUP, WORK = "greekLit", "tlg0011", "tlg001"
BASE_VERSION = "perseus-grc2"
SIB_VERSION = "perseus-eng3"
SCHEME = "card"


class _FakeCatalog:
    """Minimal stand-in exposing only what _build_sibling_data reads.

    Avoids needing real __cts__.xml files on disk just to exercise the
    focus-link/scheme-routing logic under test.
    """

    def __init__(self, editions=(), translations=()):
        self._editions = list(editions)
        self._translations = list(translations)

    def version_for(self, urn):
        return None

    def editions_of(self, work_urn):
        return self._editions

    def translations_of(self, work_urn):
        return self._translations


def _write_index(dir_: Path, urn_by_file: dict[str, str]) -> dict[Path, str]:
    """Write an index.json plus empty placeholder chunk files.

    Chunk *content* doesn't matter here — _parse_chunk is monkeypatched in
    these tests — only that the files exist (_build_sibling_data/
    _render_reading_view check chunk_file.exists() before parsing). Returns
    a {full_path: cts_urn} map for _install_fake_parse_chunk, since two
    versions can otherwise share a basename (e.g. both chunked "94.xml"
    under their own directory) and a filename-only key would collide.
    """
    dir_.mkdir(parents=True, exist_ok=True)
    chunks = [
        {"cts_urn": urn, "file": filename} for filename, urn in urn_by_file.items()
    ]
    (dir_ / "index.json").write_text(json.dumps({"chunks": chunks}))
    urn_by_path = {}
    for filename, urn in urn_by_file.items():
        path = dir_ / filename
        path.touch()
        urn_by_path[path] = urn
    return urn_by_path


def _install_fake_parse_chunk(monkeypatch, urn_by_path: dict[Path, str]) -> None:
    """Make _parse_chunk return a canned _Chunk keyed by full chunk-file
    path, instead of actually parsing TEI/XML — irrelevant to the routing
    bug this test targets."""

    def fake_parse_chunk(path: Path):
        urn = urn_by_path[path]
        chunk = _Chunk(
            cts_urn=urn,
            prev_urn=None,
            next_urn=None,
            title="",
            base_urn=urn.rsplit(":", 1)[0],
            language="grc",
            elements=[],
        )
        pub_info = {
            "title": "",
            "author": "",
            "editors": "",
            "pub_place": "",
            "pub_date": "",
        }
        return chunk, pub_info

    monkeypatch.setattr(chunksmod, "_parse_chunk", fake_parse_chunk)


_CTS_XML = f"""<ti:work xmlns:ti="http://chs.harvard.edu/xmlns/cts"
    urn="urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}" groupUrn="urn:cts:{CORPUS}:{TEXTGROUP}">
  <ti:title xml:lang="eng">Fixture Play</ti:title>
  <ti:edition urn="urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{BASE_VERSION}"
      workUrn="urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}" xml:lang="grc">
    <ti:label>Greek Edition</ti:label>
    <ti:description>ed. Fixture</ti:description>
  </ti:edition>
  <ti:translation urn="urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}"
      workUrn="urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}" xml:lang="eng">
    <ti:label>A Translation</ti:label>
    <ti:description>trans. Fixture</ti:description>
  </ti:translation>
</ti:work>
"""


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A create_app() instance with corpus auto-discovery disabled, like
    app_with_no_real_corpora in test_split_build.py — these tests only
    care about proto-page-tree-driven reading-view routes, not the
    __cts__.xml-derived catalog (a _FakeCatalog is passed in directly
    where a catalog is needed)."""
    monkeypatch.setattr(config, "CORPORA_DIR", tmp_path / "empty-corpora")
    proto_dir = tmp_path / "proto"
    proto_dir.mkdir()
    monkeypatch.setattr(config, "PROTO_DIR", proto_dir)
    return appmod.create_app()


@pytest.fixture
def app_with_real_catalog(tmp_path, monkeypatch):
    """Like `app`, but backed by a real __cts__.xml declaring the fixture
    work's edition/translation, so app.catalog (captured by closure inside
    create_app, and hence unpatchable from outside it) actually finds the
    sibling translation when _render_reading_view calls
    _build_sibling_data."""
    corpora_dir = tmp_path / "corpora"
    (corpora_dir / "fixture-corpus").mkdir(parents=True)
    (corpora_dir / "fixture-corpus" / "__cts__.xml").write_text(_CTS_XML)
    monkeypatch.setattr(config, "CORPORA_DIR", corpora_dir)
    proto_dir = tmp_path / "proto"
    proto_dir.mkdir()
    monkeypatch.setattr(config, "PROTO_DIR", proto_dir)
    return appmod.create_app()


@pytest.fixture
def mismatched_sibling_tree(tmp_path):
    """Base text read "by card"; sibling translation chunked coarsely by
    default but with a matching "card" scheme subdirectory — the scenario
    that used to break the bare-URN focus link.

    Both the base's and the sibling's "card" chunk happen to share the
    basename "94.xml" (each is the file for citation "94" under its own
    directory) — deliberately, to make sure _install_fake_parse_chunk's
    full-path keying is actually exercised, not just filename lookup.
    """
    proto_dir = tmp_path / "proto"
    urn_by_path: dict[Path, str] = {}

    base_urn = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{BASE_VERSION}:94"
    urn_by_path.update(
        _write_index(
            proto_dir / CORPUS / TEXTGROUP / WORK / BASE_VERSION / SCHEME,
            {"94.xml": base_urn},
        )
    )

    sib_default_urn = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:1-530"
    urn_by_path.update(
        _write_index(
            proto_dir / CORPUS / TEXTGROUP / WORK / SIB_VERSION,
            {"1-530.xml": sib_default_urn},
        )
    )

    sib_scheme_urn = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:94"
    urn_by_path.update(
        _write_index(
            proto_dir / CORPUS / TEXTGROUP / WORK / SIB_VERSION / SCHEME,
            {"94.xml": sib_scheme_urn},
        )
    )

    return {
        "base_urn": base_urn,
        "sib_default_urn": sib_default_urn,
        "sib_scheme_urn": sib_scheme_urn,
        "urn_by_path": urn_by_path,
    }


class TestBuildSiblingDataFocusUrl:
    def test_focus_url_routes_through_the_scheme_the_chunk_was_read_from(
        self, app, mismatched_sibling_tree, monkeypatch
    ):
        urns = mismatched_sibling_tree
        _install_fake_parse_chunk(monkeypatch, urns["urn_by_path"])

        sib_version_obj = CTSVersion(
            urn=f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}",
            work_urn=f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}",
            lang="eng",
            label="A Translation",
            description="trans.",
            version_type="translation",
        )
        catalog = _FakeCatalog(translations=[sib_version_obj])

        current_line = _chunk_start_line(urns["base_urn"])
        current_end = _chunk_end_line(urns["base_urn"])

        with app.test_request_context():
            sibling_data = siblingsmod._build_sibling_data(
                CORPUS,
                TEXTGROUP,
                WORK,
                BASE_VERSION,
                "94",
                current_line,
                current_end,
                catalog,
                base_urn=f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{BASE_VERSION}",
                scheme=SCHEME,
            )

        [(sib, sib_chunk, focus_url)] = sibling_data["translation_chunks"]
        assert sib_chunk.cts_urn == urns["sib_scheme_urn"]
        assert (
            focus_url
            == f"/urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}/{SCHEME}:94/"
        )

    def test_focus_url_omits_scheme_when_sibling_has_no_matching_scheme_dir(
        self, app, tmp_path, monkeypatch
    ):
        """When the sibling has no scheme subdir matching the base's scheme,
        _lookup falls back to the sibling's own default index — the focus
        url should stay scheme-less (reading_view), matching that fallback."""
        proto_dir = tmp_path / "proto"
        urn_by_path: dict[Path, str] = {}
        base_urn = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{BASE_VERSION}:94"
        urn_by_path.update(
            _write_index(
                proto_dir / CORPUS / TEXTGROUP / WORK / BASE_VERSION / SCHEME,
                {"94.xml": base_urn},
            )
        )
        # Two default chunks bracketing citation 94, so the range check in
        # _lookup (current_line must fall within [min(starts), max(starts)])
        # passes and Strategy 1 picks the "94-140" chunk by start line.
        sib_urn_before = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:1-93"
        sib_urn = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:94-140"
        urn_by_path.update(
            _write_index(
                proto_dir / CORPUS / TEXTGROUP / WORK / SIB_VERSION,
                {"1-93.xml": sib_urn_before, "94-140.xml": sib_urn},
            )
        )
        _install_fake_parse_chunk(monkeypatch, urn_by_path)

        sib_version_obj = CTSVersion(
            urn=f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}",
            work_urn=f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}",
            lang="eng",
            label="A Translation",
            description="trans.",
            version_type="translation",
        )
        catalog = _FakeCatalog(translations=[sib_version_obj])

        current_line = _chunk_start_line(base_urn)
        current_end = _chunk_end_line(base_urn)

        with app.test_request_context():
            sibling_data = siblingsmod._build_sibling_data(
                CORPUS,
                TEXTGROUP,
                WORK,
                BASE_VERSION,
                "94",
                current_line,
                current_end,
                catalog,
                base_urn=f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{BASE_VERSION}",
                scheme=SCHEME,
            )

        [(sib, sib_chunk, focus_url)] = sibling_data["translation_chunks"]
        assert sib_chunk.cts_urn == sib_urn
        assert (
            focus_url == f"/urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:94-140/"
        )


class TestBuildSiblingDataAboutUrn:
    """A commentary's own <ti:about> urn (surfaced as _Chunk.about_urn from
    metadata.json's document.about) should be used to find the work whose
    editions/translations are shown as siblings, since a commentary has no
    work family of its own to align against."""

    def test_about_urn_overrides_base_urn_for_sibling_work_lookup(self):
        seen_work_urns = []

        class _RecordingCatalog:
            def version_for(self, urn):
                return None

            def editions_of(self, work_urn):
                seen_work_urns.append(work_urn)
                return []

            def translations_of(self, work_urn):
                seen_work_urns.append(work_urn)
                return []

        commentary_urn = f"urn:cts:{CORPUS}:{TEXTGROUP}.commentary-version"
        about_urn = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}"

        siblingsmod._build_sibling_data(
            CORPUS,
            TEXTGROUP,
            "commentary-work",
            "commentary-version",
            "1",
            (1,),
            (1,),
            _RecordingCatalog(),
            base_urn=commentary_urn,
            about_urn=about_urn,
        )

        assert seen_work_urns == [about_urn, about_urn]

    def test_about_urn_with_citation_suffix_is_stripped_to_work_level(self):
        seen_work_urns = []

        class _RecordingCatalog:
            def version_for(self, urn):
                return None

            def editions_of(self, work_urn):
                seen_work_urns.append(work_urn)
                return []

            def translations_of(self, work_urn):
                seen_work_urns.append(work_urn)
                return []

        work_urn = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}"
        about_urn = f"{work_urn}.{BASE_VERSION}:1.1-1.10"

        siblingsmod._build_sibling_data(
            CORPUS,
            TEXTGROUP,
            "commentary-work",
            "commentary-version",
            "1",
            (1,),
            (1,),
            _RecordingCatalog(),
            base_urn=f"urn:cts:{CORPUS}:{TEXTGROUP}.commentary-version",
            about_urn=about_urn,
        )

        assert seen_work_urns == [work_urn, work_urn]

    def test_no_about_urn_falls_back_to_base_urn(self):
        seen_work_urns = []

        class _RecordingCatalog:
            def version_for(self, urn):
                return None

            def editions_of(self, work_urn):
                seen_work_urns.append(work_urn)
                return []

            def translations_of(self, work_urn):
                seen_work_urns.append(work_urn)
                return []

        base_urn = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{BASE_VERSION}"

        siblingsmod._build_sibling_data(
            CORPUS,
            TEXTGROUP,
            WORK,
            BASE_VERSION,
            "1",
            (1,),
            (1,),
            _RecordingCatalog(),
            base_urn=base_urn,
        )

        expected = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}"
        assert seen_work_urns == [expected, expected]


class TestBuildSiblingDataLeafBaseAlignment:
    """A base chunk that's itself a leaf at a coarser unit than its own
    citeStructure normally reaches -- e.g. one of Livy's periochae, a
    book-level summary with no chapter/section subdivisions (see
    perseus_cts.cts_resolver's leaf fallback in _collect_cs_elements) --
    should align to a finer-grained sibling's *whole* corresponding span,
    not just the sibling's single nearest chunk (see _starts_within_range)."""

    def test_leaf_base_merges_every_finer_sibling_chunk_in_its_range(
        self, app, tmp_path, monkeypatch
    ):
        proto_dir = tmp_path / "proto"
        urn_by_path: dict[Path, str] = {}

        # Base: a leaf book-level chunk, "5" -- no chapter subdivision.
        base_urn = f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{BASE_VERSION}:5"
        urn_by_path.update(
            _write_index(
                proto_dir / CORPUS / TEXTGROUP / WORK / BASE_VERSION,
                {"5.xml": base_urn},
            )
        )

        # Sibling: fully chaptered -- book 4 (before), three chapters of
        # book 5, and book 6 (after). Only the book-5 chapters should be
        # picked up and merged.
        sib_urns = {
            "4.xml": f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:4",
            "5.1.xml": f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:5.1",
            "5.2.xml": f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:5.2",
            "5.3.xml": f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:5.3",
            "6.xml": f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:6",
        }
        urn_by_path.update(
            _write_index(
                proto_dir / CORPUS / TEXTGROUP / WORK / SIB_VERSION,
                sib_urns,
            )
        )

        def fake_parse_chunk(path: Path):
            urn = urn_by_path[path]
            chunk = _Chunk(
                cts_urn=urn,
                prev_urn=None,
                next_urn=None,
                title="",
                base_urn=urn.rsplit(":", 1)[0],
                language="grc",
                # A marker per chunk, so a merge across every book-5
                # chapter (not just the nearest one) is actually verified
                # below, rather than just the merged chunk's leading urn.
                elements=[urn.rsplit(":", 1)[-1]],
            )
            return chunk, {}

        monkeypatch.setattr(chunksmod, "_parse_chunk", fake_parse_chunk)

        sib_version_obj = CTSVersion(
            urn=f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}",
            work_urn=f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}",
            lang="eng",
            label="A Translation",
            description="trans.",
            version_type="translation",
        )
        catalog = _FakeCatalog(translations=[sib_version_obj])

        current_line = _chunk_start_line(base_urn)
        current_end = _chunk_end_line(base_urn)
        assert current_line == current_end == (5,)

        with app.test_request_context():
            sibling_data = siblingsmod._build_sibling_data(
                CORPUS,
                TEXTGROUP,
                WORK,
                BASE_VERSION,
                "5",
                current_line,
                current_end,
                catalog,
                base_urn=f"urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{BASE_VERSION}",
            )

        [(sib, sib_chunk, focus_url)] = sibling_data["translation_chunks"]
        # Merged chunk should span exactly the three book-5 chapters, in
        # order -- not just the nearest single chapter (5.1).
        assert sib_chunk.elements == ["5.1", "5.2", "5.3"]
        assert sib_chunk.cts_urn == sib_urns["5.1.xml"]
        assert (
            focus_url
            == f"/urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:5.1/"
        )


class TestReadingViewFocusLinkResolves:
    """End-to-end: the rendered focus link must actually resolve, and must
    land on the scheme-aligned chunk rather than 404ing or resolving to the
    sibling's differently-bounded default chunk."""

    def test_focus_link_in_rendered_page_resolves_to_the_aligned_chunk(
        self, app_with_real_catalog, mismatched_sibling_tree, monkeypatch
    ):
        app = app_with_real_catalog
        urns = mismatched_sibling_tree
        _install_fake_parse_chunk(monkeypatch, urns["urn_by_path"])

        client = app.test_client()
        resp = client.get(
            f"/urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{BASE_VERSION}/{SCHEME}:94/"
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        expected_focus_href = (
            f"/urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}/{SCHEME}:94/"
        )
        assert f'href="{expected_focus_href}"' in html

        # The pre-fix bare-URN link would have pointed here instead, which
        # 404s because the sibling's *default* index only has "1-530".
        stale_href = f"/urn:cts:{CORPUS}:{TEXTGROUP}.{WORK}.{SIB_VERSION}:94/"
        assert client.get(stale_href).status_code == 404

        follow = client.get(expected_focus_href)
        assert follow.status_code == 200
