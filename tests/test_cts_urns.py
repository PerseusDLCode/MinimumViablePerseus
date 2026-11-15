# tests/test_cts_urns.py
#
# /cts-urns.json is a public contract for the legacy-Perseus redirect server
# (see _build_cts_urns): every deployed version URN -> its first page, plus
# a best-first version list per work. It must come out the same from a full
# build and from a split (corpus-only manifests -> global-only) build.

from __future__ import annotations

import json
import re

import pytest
from test_split_build import _write_version

from mvp.site import app as appmod
from mvp.site import config
from mvp.site import manifest as manifestmod
from mvp.site.catalog_tree import _CTS_URNS_SCHEMA_VERSION, _build_cts_urns


@pytest.fixture
def proto_dir(tmp_path):
    root = tmp_path / "proto"
    root.mkdir()
    # Translation, superseded edition, current edition — written in an order
    # that doesn't already match the expected best-first order.
    _write_version(root, "greekLit", "tlg0012", "tlg001", "perseus-eng3", "eng")
    _write_version(root, "greekLit", "tlg0012", "tlg001", "perseus-grc1", "grc")
    _write_version(root, "greekLit", "tlg0012", "tlg001", "perseus-grc2", "grc")
    _write_version(root, "latinLit", "phi1017", "phi007", "perseus-lat2", "lat")
    return root


@pytest.fixture
def app(monkeypatch, tmp_path, proto_dir):
    monkeypatch.setattr(config, "CORPORA_DIR", tmp_path / "empty-corpora")
    monkeypatch.setattr(config, "PROTO_DIR", proto_dir)
    return appmod.create_app()


def test_full_build_route(app):
    data = app.test_client().get("/cts-urns.json").get_json()

    assert data["schema_version"] == _CTS_URNS_SCHEMA_VERSION
    assert data["versions"]["urn:cts:greekLit:tlg0012.tlg001.perseus-grc2"] == {
        "href": "/urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1/",
        "kind": "edition",
        "language": "grc",
        "experimental": False,
    }
    assert (
        data["versions"]["urn:cts:greekLit:tlg0012.tlg001.perseus-eng3"]["kind"]
        == "translation"
    )
    # Editions first, current before superseded, translations after.
    assert data["works"]["urn:cts:greekLit:tlg0012.tlg001"] == [
        "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2",
        "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1",
        "urn:cts:greekLit:tlg0012.tlg001.perseus-eng3",
    ]
    assert set(data["versions"]) == {
        urn for urns in data["works"].values() for urn in urns
    }


def test_families_resolve_renumbered_versions_within_language(app):
    data = app.test_client().get("/cts-urns.json").get_json()
    families = data["families"]

    def resolve(version_urn: str) -> str | None:
        if version_urn in data["versions"]:
            return version_urn
        return families.get(re.sub(r"\d+$", "", version_urn))

    # Superseded edition and a not-yet-deployed newer translation number
    # both stay in their own language.
    assert families["urn:cts:greekLit:tlg0012.tlg001.perseus-grc"] == (
        "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2"
    )
    assert resolve("urn:cts:greekLit:tlg0012.tlg001.perseus-eng4") == (
        "urn:cts:greekLit:tlg0012.tlg001.perseus-eng3"
    )
    assert resolve("urn:cts:greekLit:tlg0012.tlg001.perseus-eng1") == (
        "urn:cts:greekLit:tlg0012.tlg001.perseus-eng3"
    )
    # Exact matches win, even for a superseded version that's still deployed.
    assert resolve("urn:cts:greekLit:tlg0012.tlg001.perseus-grc1") == (
        "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1"
    )
    # No same-family version -> no match, rather than a different language.
    assert resolve("urn:cts:greekLit:tlg0012.tlg001.perseus-ger1") is None
    assert all(target in data["versions"] for target in families.values())


def test_split_build_matches_full_build(app, proto_dir, tmp_path):
    baseline = app.test_client().get("/cts-urns.json").get_json()

    manifest = manifestmod._build_corpus_manifest(app, proto_dir, app.catalog, "d")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    collections, urn_index = manifestmod._merge_manifests([path, path])

    split_app = appmod.create_app(
        collections_override=collections, urn_index_override=urn_index
    )
    assert split_app.test_client().get("/cts-urns.json").get_json() == baseline


def test_experimental_versions_sort_last():
    collections = [
        {
            "id": "greekLit",
            "textgroups": [
                {
                    "id": "tlg0001",
                    "works": [
                        {
                            "id": "tlg001",
                            "versions": [
                                {
                                    "id": "1st1K-grc9",
                                    "label": "x",
                                    "kind": "edition",
                                    "language": "grc",
                                    "experimental": True,
                                    "preferred": True,
                                    "href": "/a/",
                                },
                                {
                                    "id": "perseus-eng1",
                                    "label": "y",
                                    "kind": "translation",
                                    "language": "eng",
                                    "experimental": False,
                                    "preferred": True,
                                    "href": "/b/",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    assert _build_cts_urns(collections)["works"]["urn:cts:greekLit:tlg0001.tlg001"] == [
        "urn:cts:greekLit:tlg0001.tlg001.perseus-eng1",
        "urn:cts:greekLit:tlg0001.tlg001.1st1K-grc9",
    ]
