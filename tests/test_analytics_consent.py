# tests/test_analytics_consent.py
#
# Every page carries the GDPR consent toast and static/js/analyticsConsent.js,
# which loads Google Analytics only after the visitor accepts.

from __future__ import annotations

import pytest

from mvp.site import app as appmod
from mvp.site import config


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CORPORA_DIR", tmp_path / "empty-corpora")
    monkeypatch.setattr(config, "PROTO_DIR", tmp_path / "proto")
    monkeypatch.setattr(config, "SEARCH_INDEX_DIR", None)
    return appmod.create_app()


def test_consent_toast_on_every_page(app):
    client = app.test_client()
    for path in ("/about/", "/search/"):
        html = client.get(path).get_data(as_text=True)
        assert 'id="analytics-consent"' in html
        assert 'data-analytics-consent="granted"' in html
        assert 'data-analytics-consent="denied"' in html
        assert "data-analytics-consent-open" in html
        assert "js/analyticsConsent.js" in html


def test_gtag_not_loaded_before_consent(app):
    html = app.test_client().get("/about/").get_data(as_text=True)
    # gtag.js is only ever injected client-side after consent.
    assert "googletagmanager.com" not in html
