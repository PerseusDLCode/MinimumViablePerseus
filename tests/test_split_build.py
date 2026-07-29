# tests/test_split_build.py
#
# End-to-end coverage for the corpus-only/global-only split (see
# _build_corpus_manifest, _merge_manifests, and create_app's
# collections_override/urn_index_override in mvp.site.app): building each
# corpus's manifest independently and merging them must reproduce exactly
# what a single combined build would have produced for /collections/ and
# /urn-index.json.
#
# This drives the real _build_collections/_build_urn_index/_version_entry
# code paths against a hand-built proto-page tree (index.json/metadata.json
# only) rather than compiling real TEI fixtures through Chunker — that
# would also exercise TEILinker/the gazetteer/_parse_chunk, none of which
# this split touches. It does not invoke the `mvp-build` CLI itself.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mvp.site import app as appmod


# ---------------------------------------------------------------------------
# Fixture proto-page tree
# ---------------------------------------------------------------------------


def _write_version(
    proto_root: Path,
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    language: str,
) -> None:
    """Write a minimal version directory: just the index.json/metadata.json
    sidecars _version_entry and _build_urn_index actually read — no chunk
    XML, since nothing in this test freezes a reading-view page."""
    version_dir = proto_root / corpus / textgroup / work / version
    version_dir.mkdir(parents=True)

    urn = f"urn:cts:{corpus}:{textgroup}.{work}.{version}:1"
    (version_dir / "index.json").write_text(
        json.dumps({"chunks": [{"cts_urn": urn, "file": "chunk_1.html"}]})
    )
    (version_dir / "metadata.json").write_text(
        json.dumps(
            {
                "document": {
                    "language": language,
                    "editors": [{"name": "Ann Editor", "role": "editor"}],
                },
                "toc": [],
            }
        )
    )


@pytest.fixture
def combined_and_split_proto_dirs(tmp_path):
    """Build the same two-corpus catalog two ways: one proto dir with both
    corpora (simulating today's single combined build), and two separate
    proto dirs with one corpus each (simulating the split build)."""
    combined = tmp_path / "proto-combined"
    greek_only = tmp_path / "proto-greek"
    latin_only = tmp_path / "proto-latin"

    for root in (combined, greek_only, latin_only):
        root.mkdir()

    _write_version(combined, "greekLit", "tlg0001", "tlg001", "perseus-grc2", "grc")
    _write_version(combined, "latinLit", "phi1017", "phi007", "perseus-lat2", "lat")
    _write_version(greek_only, "greekLit", "tlg0001", "tlg001", "perseus-grc2", "grc")
    _write_version(latin_only, "latinLit", "phi1017", "phi007", "perseus-lat2", "lat")

    return combined, greek_only, latin_only


@pytest.fixture
def app_with_no_real_corpora(monkeypatch, tmp_path, combined_and_split_proto_dirs):
    """A create_app() instance with corpus auto-discovery disabled.

    CORPORA_DIR points at an empty directory so _discover_corpora/
    generate_proto_pages/CTSCatalog all see zero real corpora — this test
    only cares about the proto-page-tree-driven routes (/collections/,
    /urn-index.json), which read PROTO_DIR directly, not CORPORA_DIR. The
    resulting empty CTSCatalog is fine: _work_title/_group_name fall back
    to the directory name deterministically either way, so full vs. split
    builds still produce identical labels.
    """
    combined, _, _ = combined_and_split_proto_dirs
    monkeypatch.setattr(appmod, "CORPORA_DIR", tmp_path / "empty-corpora")
    monkeypatch.setattr(appmod, "PROTO_DIR", combined)
    return appmod.create_app()


# ---------------------------------------------------------------------------
# Split build reproduces the combined build
# ---------------------------------------------------------------------------


class TestSplitBuildMatchesCombinedBuild:
    def test_collections_page_is_identical(
        self, app_with_no_real_corpora, combined_and_split_proto_dirs
    ):
        _, greek_only, latin_only = combined_and_split_proto_dirs
        app = app_with_no_real_corpora
        client = app.test_client()

        baseline_html = client.get("/collections/").get_data(as_text=True)

        greek_manifest = appmod._build_corpus_manifest(
            app, greek_only, app.catalog, "digest-greek"
        )
        latin_manifest = appmod._build_corpus_manifest(
            app, latin_only, app.catalog, "digest-latin"
        )
        manifest_paths = []
        for name, manifest in [
            ("greek", greek_manifest),
            ("latin", latin_manifest),
        ]:
            path = greek_only.parent / f"manifest-{name}.json"
            path.write_text(json.dumps(manifest))
            manifest_paths.append(path)

        collections, urn_index = appmod._merge_manifests(manifest_paths)

        split_app = appmod.create_app(
            collections_override=collections, urn_index_override=urn_index
        )
        split_html = split_app.test_client().get("/collections/").get_data(
            as_text=True
        )

        assert split_html == baseline_html

    def test_urn_index_is_identical(
        self, app_with_no_real_corpora, combined_and_split_proto_dirs
    ):
        _, greek_only, latin_only = combined_and_split_proto_dirs
        app = app_with_no_real_corpora
        client = app.test_client()

        baseline_index = client.get("/urn-index.json").get_json()

        greek_manifest = appmod._build_corpus_manifest(
            app, greek_only, app.catalog, "digest-greek"
        )
        latin_manifest = appmod._build_corpus_manifest(
            app, latin_only, app.catalog, "digest-latin"
        )
        manifest_paths = []
        for name, manifest in [
            ("greek", greek_manifest),
            ("latin", latin_manifest),
        ]:
            path = greek_only.parent / f"manifest-{name}.json"
            path.write_text(json.dumps(manifest))
            manifest_paths.append(path)

        _, urn_index = appmod._merge_manifests(manifest_paths)

        assert urn_index == baseline_index
        # Sanity check it's non-trivial, not two empty dicts matching by accident.
        assert urn_index == {
            "urn:cts:greekLit:tlg0001.tlg001": {"grc": "/greekLit:tlg0001.tlg001.perseus-grc2"},
            "urn:cts:latinLit:phi1017.phi007": {"lat": "/latinLit:phi1017.phi007.perseus-lat2"},
        }

    def test_manifest_href_resolves_to_the_real_reading_view_route(
        self, app_with_no_real_corpora, combined_and_split_proto_dirs
    ):
        """The manifest must carry a real, resolvable href (see
        _build_corpus_manifest), not the raw first_chunk_kwargs a
        global-only build has no Flask app to resolve on its own."""
        _, greek_only, _ = combined_and_split_proto_dirs
        app = app_with_no_real_corpora

        manifest = appmod._build_corpus_manifest(
            app, greek_only, app.catalog, "digest-greek"
        )
        version = manifest["textgroups"][0]["works"][0]["versions"][0]

        assert "first_chunk_kwargs" not in version
        assert (
            version["href"]
            == "/urn:cts:greekLit:tlg0001.tlg001.perseus-grc2:1/"
        )


class TestMergeManifestsSchemaVersion:
    def test_rejects_mismatched_schema_version(self, tmp_path):
        bad_manifest = {
            "schema_version": appmod._MANIFEST_SCHEMA_VERSION + 1,
            "corpus_id": "greekLit",
            "corpus_label": "Greek",
            "textgroups": [],
            "urn_index": {},
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(bad_manifest))

        with pytest.raises(ValueError, match="schema_version"):
            appmod._merge_manifests([path])


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


class TestParseBuildArgs:
    def test_defaults_to_full_mode(self):
        args = appmod._parse_build_args([])
        assert args.mode == "full"
        assert args.manifest == []
        assert args.source_digest == ""

    def test_corpus_only_accepts_source_digest(self):
        args = appmod._parse_build_args(
            ["--mode", "corpus-only", "--source-digest", "abc123"]
        )
        assert args.mode == "corpus-only"
        assert args.source_digest == "abc123"

    def test_global_only_accepts_repeated_manifest_flag(self):
        args = appmod._parse_build_args(
            ["--mode", "global-only", "--manifest", "a.json", "--manifest", "b.json"]
        )
        assert args.manifest == ["a.json", "b.json"]

    def test_global_only_without_manifest_is_rejected(self):
        with pytest.raises(SystemExit):
            appmod._parse_build_args(["--mode", "global-only"])
