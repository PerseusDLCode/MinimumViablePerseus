# tests/test_catalog_tree_kinds.py
#
# Coverage for grouping /collections versions into editions (original
# language), translations (any other language), and commentaries, including
# cross-listing a commentary under the work it comments on. See
# catalog_tree._version_kind and catalog_tree._attach_commentaries.

from __future__ import annotations

import json
from pathlib import Path

import pytest
from perseus_cts.models import CTSCatalog

from mvp.site import config
from mvp.site.catalog_tree import (
    _build_collections,
    _collections_display_tree,
    _curated_source,
    _experimental_version_ids,
    _flatten_search_index,
    _merge_collections,
)


def _write_version(
    proto_root: Path,
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    language: str,
    about: str | None = None,
) -> None:
    version_dir = proto_root / corpus / textgroup / work / version
    version_dir.mkdir(parents=True)
    urn = f"urn:cts:{corpus}:{textgroup}.{work}.{version}:1"
    (version_dir / "index.json").write_text(
        json.dumps({"chunks": [{"cts_urn": urn, "file": "chunk_1.html"}]})
    )
    (version_dir / "metadata.json").write_text(
        json.dumps(
            {
                "document": {"language": language, "editors": [], "about": about},
                "toc": [],
            }
        )
    )


@pytest.fixture
def empty_catalog(tmp_path):
    root = tmp_path / "empty-corpora"
    root.mkdir()
    return CTSCatalog(root)


def _works_by_id(collections: list[dict]) -> dict[str, dict]:
    return {
        f"{tg['id']}.{work['id']}": work
        for corpus in collections
        for tg in corpus["textgroups"]
        for work in tg["works"]
    }


def _kinds(work: dict) -> dict[str, str]:
    return {v["id"]: v["kind"] for v in work["versions"]}


class TestVersionKind:
    def test_original_language_is_edition_other_is_translation(
        self, tmp_path, empty_catalog
    ):
        proto = tmp_path / "proto"
        _write_version(proto, "latinLit", "phi0474", "phi002", "perseus-lat2", "lat")
        _write_version(proto, "latinLit", "phi0474", "phi002", "perseus-eng1", "eng")

        work = _works_by_id(_build_collections(proto, empty_catalog))["phi0474.phi002"]
        assert _kinds(work) == {
            "perseus-lat2": "edition",
            "perseus-eng1": "translation",
        }

    def test_version_id_language_beats_mistagged_tei_language(
        self, tmp_path, empty_catalog
    ):
        """First1KGreek editions are often tagged "lat" (for their Latin
        front matter) or "greek" in the TEI header."""
        proto = tmp_path / "proto"
        _write_version(proto, "greekLit", "tlg0057", "tlg036", "1st1K-grc1", "lat")
        _write_version(proto, "greekLit", "tlg0086", "tlg014", "1st1K-grc1", "greek")

        works = _works_by_id(_build_collections(proto, empty_catalog))
        assert _kinds(works["tlg0057.tlg036"]) == {"1st1K-grc1": "edition"}
        assert _kinds(works["tlg0086.tlg014"]) == {"1st1K-grc1": "edition"}

    def test_about_marks_a_commentary(self, tmp_path, empty_catalog):
        proto = tmp_path / "proto"
        _write_version(
            proto,
            "latinLit",
            "sec00009",
            "sec002",
            "perseus-eng1",
            "eng",
            about="urn:cts:latinLit:phi0474.phi002",
        )

        work = _works_by_id(_build_collections(proto, empty_catalog))["sec00009.sec002"]
        assert _kinds(work) == {"perseus-eng1": "commentary"}


class TestAttachCommentaries:
    def test_commentary_is_cross_listed_under_its_target_work(
        self, tmp_path, empty_catalog
    ):
        proto = tmp_path / "proto"
        _write_version(proto, "latinLit", "phi0474", "phi013", "perseus-lat2", "lat")
        _write_version(
            proto,
            "latinLit",
            "sec00009",
            "sec005b",
            "perseus-eng1",
            "eng",
            # A commentary on part of a work is still listed with that work.
            about="urn:cts:latinLit:phi0474.phi013:2",
        )

        works = _works_by_id(_build_collections(proto, empty_catalog))
        target = works["phi0474.phi013"]
        commentary = works["sec00009.sec005b"]["versions"][0]
        assert target["commentaries"] == [commentary]
        # Still listed under its own work, but not under itself twice.
        assert works["sec00009.sec005b"]["commentaries"] == []

    def test_merge_cross_lists_commentaries_across_sources(
        self, tmp_path, empty_catalog
    ):
        proto_a = tmp_path / "proto-a"
        proto_b = tmp_path / "proto-b"
        _write_version(proto_a, "greekLit", "tlg0001", "tlg001", "perseus-grc2", "grc")
        _write_version(
            proto_b,
            "greekLit",
            "tlg5012",
            "tlg001",
            "wendelnotes-1",
            "grc",
            about="urn:cts:greekLit:tlg0001.tlg001",
        )

        # Round-trip through JSON, as manifests do, so the merge can't lean
        # on dict identity from the per-source builds.
        sources = [
            json.loads(json.dumps(_build_collections(p, empty_catalog)))
            for p in (proto_a, proto_b)
        ]
        works = _works_by_id(_merge_collections(sources))
        assert [v["id"] for v in works["tlg0001.tlg001"]["commentaries"]] == [
            "wendelnotes-1"
        ]


class TestPreferredWithinKind:
    def test_commentary_does_not_outrank_same_family_edition(
        self, tmp_path, empty_catalog
    ):
        proto = tmp_path / "proto"
        _write_version(proto, "greekLit", "tlg0627", "tlg001", "1st1K-grc1", "grc")
        _write_version(
            proto,
            "greekLit",
            "tlg0627",
            "tlg001",
            "1st1K-grc2",
            "grc",
            about="urn:cts:greekLit:tlg0627.tlg001",
        )

        work = _works_by_id(_build_collections(proto, empty_catalog))["tlg0627.tlg001"]
        assert {v["id"]: v["preferred"] for v in work["versions"]} == {
            "1st1K-grc1": True,
            "1st1K-grc2": True,
        }


class TestCommentator:
    def test_standalone_commentary_is_credited_to_its_textgroup(
        self, tmp_path, empty_catalog
    ):
        """Jebb's commentaries live under their own textgroup and list no
        editors, so the textgroup (falling back to the TEI author) is the
        only place his name appears."""
        proto = tmp_path / "proto"
        _write_version(proto, "greekLit", "tlg0011", "tlg004", "perseus-grc2", "grc")
        _write_version(
            proto,
            "greekLit",
            "viaf2603144",
            "viaf001",
            "perseus-eng1",
            "eng",
            about="urn:cts:greekLit:tlg0011.tlg004",
        )
        metadata = proto / "greekLit/viaf2603144/viaf001/perseus-eng1/metadata.json"
        data = json.loads(metadata.read_text())
        data["document"]["author"] = "Sir Richard C. Jebb"
        metadata.write_text(json.dumps(data))

        works = _works_by_id(_build_collections(proto, empty_catalog))
        (commentary,) = works["tlg0011.tlg004"]["commentaries"]
        assert commentary["commentator"] == "Sir Richard C. Jebb"
        assert works["tlg0011.tlg004"]["versions"][0]["commentator"] == ""

    def test_commentary_filed_with_its_work_gets_no_commentator(
        self, tmp_path, empty_catalog
    ):
        """Its textgroup is the ancient author's, not the commentator's."""
        proto = tmp_path / "proto"
        _write_version(
            proto,
            "greekLit",
            "tlg0627",
            "tlg001",
            "1st1K-grc2",
            "grc",
            about="urn:cts:greekLit:tlg0627.tlg001",
        )

        work = _works_by_id(_build_collections(proto, empty_catalog))["tlg0627.tlg001"]
        assert work["versions"][0]["commentator"] == ""


class TestCollectionsDisplayTree:
    def test_kinds_in_order_with_every_version_and_perseus_first(
        self, tmp_path, empty_catalog
    ):
        proto = tmp_path / "proto"
        _write_version(proto, "greekLit", "tlg0011", "tlg004", "1st1K-grc1", "grc")
        _write_version(proto, "greekLit", "tlg0011", "tlg004", "perseus-grc1", "grc")
        _write_version(proto, "greekLit", "tlg0011", "tlg004", "perseus-grc2", "grc")
        _write_version(proto, "greekLit", "tlg0011", "tlg004", "perseus-eng2", "eng")
        _write_version(
            proto,
            "greekLit",
            "viaf2603144",
            "viaf001",
            "perseus-eng1",
            "eng",
            about="urn:cts:greekLit:tlg0011.tlg004",
        )

        (corpus,) = _collections_display_tree(_build_collections(proto, empty_catalog))
        work = _works_by_id([corpus])["tlg0011.tlg004"]
        assert [
            (k["kind"], [v["id"] for v in k["versions"]]) for k in work["kinds"]
        ] == [
            # Superseded perseus-grc1 is shown too, not hidden.
            ("edition", ["perseus-grc1", "perseus-grc2", "1st1K-grc1"]),
            ("translation", ["perseus-eng2"]),
            ("commentary", ["perseus-eng1"]),
        ]

    def test_sorts_corpora_authors_and_works_without_mutating_input(
        self, tmp_path, empty_catalog
    ):
        proto = tmp_path / "proto"
        _write_version(proto, "latinLit", "phi0474", "phi002", "perseus-lat2", "lat")
        _write_version(proto, "greekLit", "tlg0011", "tlg004", "perseus-grc2", "grc")
        collections = _build_collections(proto, empty_catalog)
        before = json.dumps(collections)

        display = _collections_display_tree(collections)
        # Sorted by label: "Greek" before "Latin".
        assert [c["id"] for c in display] == ["greekLit", "latinLit"]
        assert json.dumps(collections) == before


class TestSearchIndex:
    def test_entries_carry_the_facet_values_collections_filters_on(
        self, tmp_path, empty_catalog
    ):
        proto = tmp_path / "proto"
        _write_version(proto, "latinLit", "phi0474", "phi002", "perseus-lat2", "lat")
        _write_version(proto, "latinLit", "phi0474", "phi002", "perseus-eng1", "eng")
        collections = _build_collections(proto, empty_catalog)
        for version in _works_by_id(collections)["phi0474.phi002"]["versions"]:
            version["href"] = f"/{version['id']}/"

        facets = {
            entry["url"]: (entry["kind"], entry["lang"], entry["corpus_id"])
            for entry in _flatten_search_index(collections)
        }
        assert facets == {
            "/perseus-lat2/": ("edition", "lat", "latinLit"),
            "/perseus-eng1/": ("translation", "eng", "latinLit"),
        }


class TestExperimentalVersions:
    def test_ids_come_from_filenames_and_catalog(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "_EXPERIMENTAL_SOURCES", {"grcnewxml"})
        corpora = tmp_path / "corpora"
        work_dir = corpora / "grcnewxml" / "data" / "tlg0001" / "tlg001"
        work_dir.mkdir(parents=True)
        # No __cts__.xml entry: found by filename alone.
        (work_dir / "tlg0001.tlg001.ocr-grc1.xml").write_text("<TEI/>")
        # Declared in __cts__.xml under a file named differently.
        (work_dir / "__cts__.xml").write_text(
            '<ti:work xmlns:ti="http://chs.harvard.edu/xmlns/cts" '
            'groupUrn="urn:cts:greekLit:tlg0001" urn="urn:cts:greekLit:tlg0001.tlg001">'
            '<ti:title xml:lang="eng">W</ti:title>'
            '<ti:edition workUrn="urn:cts:greekLit:tlg0001.tlg001" '
            'urn="urn:cts:greekLit:tlg0001.tlg001.ocr-grc2">'
            "<ti:label>L</ti:label></ti:edition></ti:work>"
        )
        curated = corpora / "canonical-greekLit" / "data" / "tlg0001" / "tlg001"
        curated.mkdir(parents=True)
        (curated / "tlg0001.tlg001.perseus-grc1.xml").write_text("<TEI/>")
        catalog = CTSCatalog([corpora / "grcnewxml" / "data", corpora / "canonical-greekLit" / "data"])

        assert _experimental_version_ids(corpora, catalog) == {
            "tlg0001.tlg001.ocr-grc1",
            "tlg0001.tlg001.ocr-grc2",
        }

    def test_flagged_sorted_last_and_faceted(self, tmp_path, empty_catalog):
        proto = tmp_path / "proto"
        _write_version(proto, "greekLit", "tlg0011", "tlg004", "a-ocr-grc1", "grc")
        _write_version(proto, "greekLit", "tlg0011", "tlg004", "perseus-grc2", "grc")
        _write_version(proto, "greekLit", "tlg0011", "tlg004", "1st1K-grc1", "grc")
        collections = _build_collections(
            proto, empty_catalog, frozenset({"tlg0011.tlg004.a-ocr-grc1"})
        )

        (corpus,) = _collections_display_tree(collections)
        (edition,) = _works_by_id([corpus])["tlg0011.tlg004"]["kinds"]
        assert [(v["id"], v["experimental"]) for v in edition["versions"]] == [
            ("perseus-grc2", False),
            ("1st1K-grc1", False),
            ("a-ocr-grc1", True),
        ]

        for version in _works_by_id(collections)["tlg0011.tlg004"]["versions"]:
            version["href"] = f"/{version['id']}/"
        statuses = {e["url"]: e["status"] for e in _flatten_search_index(collections)}
        assert statuses == {
            "/a-ocr-grc1/": "experimental",
            "/perseus-grc2/": "curated",
            "/1st1K-grc1/": "curated",
        }


class TestCuratedSource:
    @pytest.mark.parametrize(
        ("urn", "label"),
        [
            ("urn:cts:greekLit:tlg0012.tlg001.perseus-grc2", "Perseus"),
            ("urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1", "Perseus"),
            ("tlg2042.tlg001.1st1K-grc1", "First1KGreek"),
            ("perseus-eng1", "Perseus"),
            ("urn:cts:greekLit:tlg0012.tlg001.opp-grc3", None),
            ("urn:cts:latinLit:phi0474.phi013.nd-dlc-lat1", None),
        ],
    )
    def test_label(self, urn, label):
        assert _curated_source(urn) == label

