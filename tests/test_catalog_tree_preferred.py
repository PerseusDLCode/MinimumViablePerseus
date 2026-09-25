# tests/test_catalog_tree_preferred.py
#
# Coverage for the /collections "preferred edition" logic: within a work,
# the highest-numbered id in each version-id family (e.g. perseus-grc2 over
# perseus-grc1) is preferred by default, and config._VERSION_OVERRIDES can
# force a different one. See catalog_tree._mark_preferred_versions.

from __future__ import annotations

import json
from pathlib import Path

import pytest
from perseus_cts.models import CTSCatalog

from mvp.site import config
from mvp.site.catalog_tree import (
    _build_collections,
    _mark_preferred_versions,
    _merge_collections,
    _version_family,
)


def _write_version(
    proto_root: Path,
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    language: str = "grc",
) -> None:
    version_dir = proto_root / corpus / textgroup / work / version
    version_dir.mkdir(parents=True)
    urn = f"urn:cts:{corpus}:{textgroup}.{work}.{version}:1"
    (version_dir / "index.json").write_text(
        json.dumps({"chunks": [{"cts_urn": urn, "file": "chunk_1.html"}]})
    )
    (version_dir / "metadata.json").write_text(
        json.dumps({"document": {"language": language, "editors": []}, "toc": []})
    )


@pytest.fixture
def empty_catalog(tmp_path):
    root = tmp_path / "empty-corpora"
    root.mkdir()
    return CTSCatalog(root)


class TestVersionFamily:
    def test_splits_trailing_digits(self):
        assert _version_family("perseus-grc2") == ("perseus-grc", 2)
        assert _version_family("perseus-grc10") == ("perseus-grc", 10)

    def test_no_trailing_digits_is_its_own_family(self):
        assert _version_family("some-edition") == ("some-edition", 0)


class TestMarkPreferredVersions:
    def test_highest_number_in_family_wins(self, monkeypatch):
        monkeypatch.setattr(config, "_VERSION_OVERRIDES", {})
        versions = [{"id": "perseus-grc1"}, {"id": "perseus-grc2"}]
        _mark_preferred_versions("urn:cts:greekLit:tlg0001.tlg001", versions)
        assert [v["preferred"] for v in versions] == [False, True]

    def test_separate_families_each_get_a_preferred_version(self, monkeypatch):
        monkeypatch.setattr(config, "_VERSION_OVERRIDES", {})
        versions = [
            {"id": "perseus-grc1"},
            {"id": "perseus-grc2"},
            {"id": "perseus-eng1"},
        ]
        _mark_preferred_versions("urn:cts:greekLit:tlg0001.tlg001", versions)
        preferred = {v["id"] for v in versions if v["preferred"]}
        assert preferred == {"perseus-grc2", "perseus-eng1"}

    def test_override_forces_a_specific_version_preferred(self, monkeypatch):
        work_urn = "urn:cts:greekLit:tlg0001.tlg001"
        monkeypatch.setattr(
            config,
            "_VERSION_OVERRIDES",
            {f"{work_urn}.perseus-grc1": {"preferred": True}},
        )
        versions = [{"id": "perseus-grc1"}, {"id": "perseus-grc2"}]
        _mark_preferred_versions(work_urn, versions)
        assert [v["preferred"] for v in versions] == [True, False]


class TestBuildCollectionsMarksPreferred(object):
    def test_build_collections_flags_highest_numbered_version(
        self, tmp_path, empty_catalog, monkeypatch
    ):
        monkeypatch.setattr(config, "_VERSION_OVERRIDES", {})
        proto = tmp_path / "proto"
        proto.mkdir()
        _write_version(proto, "greekLit", "tlg0001", "tlg001", "perseus-grc1")
        _write_version(proto, "greekLit", "tlg0001", "tlg001", "perseus-grc2")

        collections = _build_collections(proto, empty_catalog)
        versions = collections[0]["textgroups"][0]["works"][0]["versions"]
        preferred = {v["id"]: v["preferred"] for v in versions}
        assert preferred == {"perseus-grc1": False, "perseus-grc2": True}

    def test_merge_recomputes_preferred_across_sources(self, tmp_path, empty_catalog, monkeypatch):
        """A work's two editions can come from two different manifests
        (see _merge_collections docstring); preferred must be computed on
        the merged version set, not decided independently per source."""
        monkeypatch.setattr(config, "_VERSION_OVERRIDES", {})
        proto_a = tmp_path / "proto-a"
        proto_b = tmp_path / "proto-b"
        proto_a.mkdir()
        proto_b.mkdir()
        _write_version(proto_a, "greekLit", "tlg0001", "tlg001", "perseus-grc1")
        _write_version(proto_b, "greekLit", "tlg0001", "tlg001", "perseus-grc2")

        collections_a = _build_collections(proto_a, empty_catalog)
        collections_b = _build_collections(proto_b, empty_catalog)

        # Each build in isolation trivially marks its lone version preferred.
        assert collections_a[0]["textgroups"][0]["works"][0]["versions"][0]["preferred"]
        assert collections_b[0]["textgroups"][0]["works"][0]["versions"][0]["preferred"]

        merged = _merge_collections([collections_a, collections_b])
        versions = merged[0]["textgroups"][0]["works"][0]["versions"]
        preferred = {v["id"]: v["preferred"] for v in versions}
        assert preferred == {"perseus-grc1": False, "perseus-grc2": True}


class TestExperimentalNeverPreferredOverCurated:
    def test_curated_version_of_same_kind_wins(self, monkeypatch):
        monkeypatch.setattr(config, "_VERSION_OVERRIDES", {})
        versions = [
            {"id": "perseus-grc1", "kind": "edition"},
            {"id": "ocr-grc9", "kind": "edition", "experimental": True},
        ]
        _mark_preferred_versions("urn:cts:greekLit:tlg0001.tlg001", versions)
        assert [v["preferred"] for v in versions] == [True, False]

    def test_experimental_preferred_when_its_kind_has_no_curated_version(
        self, monkeypatch
    ):
        monkeypatch.setattr(config, "_VERSION_OVERRIDES", {})
        versions = [
            {"id": "perseus-grc1", "kind": "edition"},
            {"id": "ocr-eng1", "kind": "translation", "experimental": True},
            {"id": "ocr-eng2", "kind": "translation", "experimental": True},
        ]
        _mark_preferred_versions("urn:cts:greekLit:tlg0001.tlg001", versions)
        preferred = {v["id"] for v in versions if v["preferred"]}
        assert preferred == {"perseus-grc1", "ocr-eng2"}
