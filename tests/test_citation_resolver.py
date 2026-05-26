# tests/test_citation_resolver.py
#
# Tests for CitationResolver.
#
# Uses small synthetic fixture data written to tmp_path rather than the
# real data files in data/abbreviations/ (which are gitignored and not
# guaranteed to be present in all environments).

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mvp.annotations.citation_resolver import CitationResolver


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ABBREVIATIONS = [
    {"abbrev": "Hom.", "full": "Homer"},
    {"abbrev": "Od.",  "full": "Odyssey"},
    {"abbrev": "Il.",  "full": "Iliad"},
    {"abbrev": "Pl.",  "full": "Plato"},
    {"abbrev": "Rep.", "full": "Republic"},
    # Duplicate abbreviation — first entry wins
    {"abbrev": "Cat.", "full": "In Catilinam"},
    {"abbrev": "Cat.", "full": "Catalogus mulierum"},
]

INVERTED_URNS = {
    "homer": {
        "odyssey": "urn:cts:greekLit:tlg0012.tlg002",
        "iliad":   "urn:cts:greekLit:tlg0012.tlg001",
    },
    "plato": {
        "republic": "urn:cts:greekLit:tlg0059.tlg030",
    },
}


@pytest.fixture
def abbreviations_dir(tmp_path: Path) -> Path:
    (tmp_path / "ocd_abbreviations.json").write_text(
        json.dumps(ABBREVIATIONS), encoding="utf-8"
    )
    (tmp_path / "inverted_urn.json").write_text(
        json.dumps(INVERTED_URNS), encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def resolver(abbreviations_dir: Path) -> CitationResolver:
    return CitationResolver(abbreviations_dir)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestCitationResolverConstruction:

    def test_accepts_path(self, abbreviations_dir):
        r = CitationResolver(abbreviations_dir)
        assert r is not None

    def test_accepts_string_path(self, abbreviations_dir):
        r = CitationResolver(str(abbreviations_dir))
        assert r is not None

    def test_raises_on_missing_dir(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            CitationResolver(tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------

class TestResolve:

    def test_known_author_and_work(self, resolver):
        assert resolver.resolve("Hom. Od. 1.1") == \
            "urn:cts:greekLit:tlg0012.tlg002:1.1"

    def test_multi_digit_location(self, resolver):
        assert resolver.resolve("Hom. Il. 24.804") == \
            "urn:cts:greekLit:tlg0012.tlg001:24.804"

    def test_three_token_citation(self, resolver):
        assert resolver.resolve("Pl. Rep. 514a") == \
            "urn:cts:greekLit:tlg0059.tlg030:514a"

    def test_unknown_author_returns_none(self, resolver):
        assert resolver.resolve("Xen. An. 1.1") is None

    def test_unknown_work_returns_none(self, resolver):
        assert resolver.resolve("Hom. Batr. 1") is None

    def test_unknown_abbreviation_returns_none(self, resolver):
        assert resolver.resolve("Zzz. Yyy. 1.1") is None

    def test_single_token_returns_none(self, resolver):
        assert resolver.resolve("Hom.") is None

    def test_two_tokens_no_work_returns_none(self, resolver):
        # "Hom. 1.1" — no work abbreviation between author and location
        assert resolver.resolve("Hom. 1.1") is None

    def test_empty_string_returns_none(self, resolver):
        assert resolver.resolve("") is None

    def test_first_expansion_wins_for_duplicate_abbreviation(self, resolver):
        # "Cat." expands to "In Catilinam" (first entry); not in inverted_urns -> None
        assert resolver.resolve("Cat. 1.1") is None
