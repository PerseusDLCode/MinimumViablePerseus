# tests/test_site_map.py
#
# Tests for SiteMap: output path and URL scheme for compiled artifacts.
#
# SiteMap._urn_to_path() is private but is the core logic of the class;
# it is tested indirectly through chunk_dir(), which exposes the resulting
# path and also creates the directory (a separately testable side-effect).
#
# Passage-citation stripping is covered implicitly by the path-structure
# tests: if test_latin_urn_maps_to_correct_path passes with a URN that
# has no passage, and the implementation strips the passage before
# constructing the path, then passage stripping is correct by construction.

from __future__ import annotations

from pathlib import Path


from mvp.compilers.site_map import SiteMap

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Representative CTS URNs from the corpus fixtures
SENECA_URN    = "urn:cts:latinLit:phi1017.phi007.perseus-lat2"
SOPHOCLES_URN = "urn:cts:greekLit:tlg0011.tlg001.perseus-grc2"
GALEN_URN     = "urn:cts:greekLit:tlg0057.tlg069.1st1K-grc1"

# URN with a passage citation appended
SENECA_URN_WITH_PASSAGE = "urn:cts:latinLit:phi1017.phi007.perseus-lat2:57"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestSiteMapConstruction:

    def test_accepts_path(self, tmp_path):
        sm = SiteMap(tmp_path)
        assert sm.root == tmp_path

    def test_accepts_string(self, tmp_path):
        sm = SiteMap(str(tmp_path))
        assert sm.root == tmp_path

    def test_root_is_path_instance(self, tmp_path):
        sm = SiteMap(tmp_path)
        assert isinstance(sm.root, Path)


# ---------------------------------------------------------------------------
# URN → path mapping (tested via chunk_dir)
# ---------------------------------------------------------------------------

class TestURNToPath:
    """Path structure for well-formed CTS URNs."""

    def test_latin_urn_maps_to_correct_path(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.chunk_dir(SENECA_URN)
        expected = tmp_path / "latinLit" / "phi1017" / "phi007" / "perseus-lat2"
        assert result == expected

    def test_greek_urn_maps_to_correct_path(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.chunk_dir(SOPHOCLES_URN)
        expected = tmp_path / "greekLit" / "tlg0011" / "tlg001" / "perseus-grc2"
        assert result == expected

    def test_passage_citation_is_stripped(self, tmp_path):
        """A URN with a passage component maps to the same path as without."""
        sm = SiteMap(tmp_path)
        result_bare    = sm.chunk_dir(SENECA_URN)
        result_passage = sm.chunk_dir(SENECA_URN_WITH_PASSAGE)
        assert result_bare == result_passage

    def test_version_with_hyphens_is_preserved(self, tmp_path):
        """Version identifiers containing hyphens (e.g. '1st1K-grc1') are
        preserved as-is; hyphens are valid in directory names."""
        sm = SiteMap(tmp_path)
        result = sm.chunk_dir(GALEN_URN)
        expected = tmp_path / "greekLit" / "tlg0057" / "tlg069" / "1st1K-grc1"
        assert result == expected


class TestURNToPathFallback:
    """Fallback behaviour for URNs that don't conform to expected structure."""

    def test_empty_urn_does_not_raise(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.chunk_dir("")
        assert isinstance(result, Path)

    def test_bare_string_does_not_raise(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.chunk_dir("not-a-urn-at-all")
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# chunk_dir
# ---------------------------------------------------------------------------

class TestChunkDir:

    def test_returns_path(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.chunk_dir(SENECA_URN)
        assert isinstance(result, Path)

    def test_creates_directory(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.chunk_dir(SENECA_URN)
        assert result.is_dir()

    def test_is_idempotent(self, tmp_path):
        """Calling chunk_dir twice does not raise."""
        sm = SiteMap(tmp_path)
        first  = sm.chunk_dir(SENECA_URN)
        second = sm.chunk_dir(SENECA_URN)
        assert first == second

    def test_is_under_root(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.chunk_dir(SENECA_URN)
        assert result.is_relative_to(tmp_path)

    def test_different_urns_produce_different_paths(self, tmp_path):
        sm = SiteMap(tmp_path)
        assert sm.chunk_dir(SENECA_URN) != sm.chunk_dir(SOPHOCLES_URN)


# ---------------------------------------------------------------------------
# chunk_path
# ---------------------------------------------------------------------------

class TestChunkPath:

    def test_returns_path_under_chunk_dir(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.chunk_path(SENECA_URN, "57")
        assert result.parent == sm.chunk_dir(SENECA_URN)

    def test_filename_contains_chunk_id(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.chunk_path(SENECA_URN, "57")
        assert "57" in result.name

    def test_filename_is_html(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.chunk_path(SENECA_URN, "57")
        assert result.suffix == ".html"

    def test_different_chunk_ids_produce_different_paths(self, tmp_path):
        sm = SiteMap(tmp_path)
        assert sm.chunk_path(SENECA_URN, "1") != sm.chunk_path(SENECA_URN, "57")

    def test_does_not_create_file(self, tmp_path):
        """chunk_path is pure path computation; it must not create files."""
        sm = SiteMap(tmp_path)
        result = sm.chunk_path(SENECA_URN, "57")
        assert not result.exists()


# ---------------------------------------------------------------------------
# manifest_path
# ---------------------------------------------------------------------------

class TestManifestPath:

    def test_returns_path_under_chunk_dir(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.manifest_path(SENECA_URN)
        assert result.parent == sm.chunk_dir(SENECA_URN)

    def test_filename_is_index_json(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.manifest_path(SENECA_URN)
        assert result.name == "index.json"

    def test_does_not_create_file(self, tmp_path):
        """manifest_path is pure path computation; it must not create files."""
        sm = SiteMap(tmp_path)
        result = sm.manifest_path(SENECA_URN)
        assert not result.exists()


# ---------------------------------------------------------------------------
# catalog_path
# ---------------------------------------------------------------------------

class TestCatalogPath:

    def test_returns_path_under_catalog_dir(self, tmp_path):
        sm = SiteMap(tmp_path)
        result = sm.catalog_path("grc")
        assert result.parent == tmp_path / "catalog"

    def test_filename_is_language_html(self, tmp_path):
        sm = SiteMap(tmp_path)
        assert sm.catalog_path("grc").name == "grc.html"
        assert sm.catalog_path("lat").name == "lat.html"

    def test_creates_catalog_directory(self, tmp_path):
        sm = SiteMap(tmp_path)
        sm.catalog_path("grc")
        assert (tmp_path / "catalog").is_dir()

    def test_different_languages_produce_different_paths(self, tmp_path):
        sm = SiteMap(tmp_path)
        assert sm.catalog_path("grc") != sm.catalog_path("lat")

    def test_is_idempotent(self, tmp_path):
        """Calling catalog_path twice does not raise."""
        sm = SiteMap(tmp_path)
        first  = sm.catalog_path("grc")
        second = sm.catalog_path("grc")
        assert first == second
