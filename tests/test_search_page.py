# tests/test_search_page.py
#
# /search/ is a static page: the search itself runs in the browser against
# the search index, read over HTTP range requests from /search-index/. In
# production nginx serves that directory (deploy/nginx.conf); with
# SEARCH_INDEX_DIR set, `mvp-dev` serves it instead, and must answer Range
# requests the way nginx does.

from __future__ import annotations

import json

import pytest

from mvp.site import app as appmod
from mvp.site import config


@pytest.fixture
def make_app(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CORPORA_DIR", tmp_path / "empty-corpora")
    monkeypatch.setattr(config, "PROTO_DIR", tmp_path / "proto")

    def make(search_index_dir=None):
        monkeypatch.setattr(config, "SEARCH_INDEX_DIR", search_index_dir)
        return appmod.create_app()

    return make


def test_search_page_is_configured_for_index_and_morph(make_app, monkeypatch):
    monkeypatch.setattr(config, "MORPH_URL", "https://example.org/morph")
    response = make_app().test_client().get("/search/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '"indexUrl": "/search-index/"' in html
    assert '"morphUrl": "https://example.org/morph"' in html
    assert "sql-httpvfs/index.js" in html


def test_index_route_absent_unless_configured(make_app):
    client = make_app().test_client()
    assert client.get("/search-index/manifest.json").status_code == 404


def test_dev_index_route_serves_byte_ranges(make_app, tmp_path):
    index_dir = tmp_path / "search-index"
    index_dir.mkdir()
    (index_dir / "manifest.json").write_text(json.dumps({"db": "search-abc.db"}))
    (index_dir / "search-abc.db").write_bytes(bytes(range(256)) * 32)

    client = make_app(index_dir).test_client()
    assert client.get("/search-index/manifest.json").get_json() == {"db": "search-abc.db"}

    response = client.get("/search-index/search-abc.db", headers={"Range": "bytes=4096-4097"})
    assert response.status_code == 206
    assert response.data == bytes([0, 1])
    assert response.headers["Content-Range"] == "bytes 4096-4097/8192"


def test_nav_links_to_search(make_app):
    html = make_app().test_client().get("/search/").get_data(as_text=True)
    assert 'href="/search/"' in html
