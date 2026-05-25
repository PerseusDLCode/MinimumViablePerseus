# tests/test_compilers.py
#
# Tests for CompilationError, PageCompiler, and CatalogCompiler.
#
# Testing strategy:
#   - CompilationError: plain dataclass/exception behaviour, no mocking needed.
#   - PageCompiler: unit tests mock saxonche entirely.  We test that the
#     Python logic (directory creation, parameter passing, error wrapping)
#     is correct without invoking Saxon.  An integration test against real
#     Saxon + XSLT belongs here too but is deferred until the XSLT suite
#     is written; see the TODO at the bottom of this file.
#   - CatalogCompiler: stubbed; xfail documents the NotImplementedError.
#
# NOTE on PageCompiler design: PageCompiler constructs its PySaxonProcessor
# internally via a context manager.  We patch 'mvp.compilers.PySaxonProcessor'
# to intercept it.  If the import path changes, the patch target must change
# too.

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mvp.compilers import (
    CatalogCompiler, CompilationError, PageCompiler, XSLTCompiler,
    copy_static_assets,
)
from mvp.document import TEIDocument
from mvp.models import TEIMetadata
from mvp.site_map import SiteMap
from mvp.strategy import MilestoneStrategy

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
SENECA_PATH = DATA_DIR / "phi1017.phi007.perseus-lat2.xml"


@pytest.fixture
def seneca_doc():
    from mvp.document import TEIDocument
    return TEIDocument.from_path(SENECA_PATH)


@pytest.fixture
def card_strategy():
    return MilestoneStrategy(unit="card")


@pytest.fixture
def mock_saxon():
    """Patch PySaxonProcessor with a MagicMock and yield the mock class.

    The mock is configured so that the context-manager protocol works:
        with PySaxonProcessor(license=False) as proc: ...
    yields a mock proc object whose method calls are also mocks.

    error_message is set to None so the post-transform error check in
    XSLTCompiler.compile() does not raise on success paths.
    """
    with patch("mvp.compilers.PySaxonProcessor") as mock_cls:
        mock_proc = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_proc)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_proc.new_xslt30_processor.return_value.error_message = None
        yield mock_cls, mock_proc


# ---------------------------------------------------------------------------
# CompilationError
# ---------------------------------------------------------------------------

class TestCompilationError:

    def test_is_exception(self, seneca_doc):
        err = CompilationError(document=seneca_doc, message="something went wrong")
        assert isinstance(err, Exception)

    def test_str_without_cause(self, seneca_doc):
        err = CompilationError(document=seneca_doc, message="something went wrong")
        s = str(err)
        assert "something went wrong" in s
        assert str(seneca_doc.path) in s

    def test_str_with_cause(self, seneca_doc):
        cause = ValueError("underlying problem")
        err = CompilationError(
            document=seneca_doc,
            message="something went wrong",
            cause=cause,
        )
        s = str(err)
        assert "something went wrong" in s
        assert "underlying problem" in s

    def test_cause_defaults_to_none(self, seneca_doc):
        err = CompilationError(document=seneca_doc, message="oops")
        assert err.cause is None

    def test_can_be_raised_and_caught(self, seneca_doc):
        with pytest.raises(CompilationError) as exc_info:
            raise CompilationError(document=seneca_doc, message="test raise")
        assert exc_info.value.message == "test raise"


# ---------------------------------------------------------------------------
# XSLTCompiler
# ---------------------------------------------------------------------------

class TestXSLTCompiler:

    def test_construction_does_not_raise(self, tmp_path):
        compiler = XSLTCompiler(xsl_file=tmp_path / "driver.xsl")
        assert compiler is not None

    def test_accepts_string_path(self, tmp_path):
        compiler = XSLTCompiler(xsl_file=str(tmp_path / "driver.xsl"))
        assert compiler is not None

    def test_creates_output_directory(self, tmp_path, mock_saxon):
        output_path = tmp_path / "out" / "deep"
        assert not output_path.exists()
        compiler = XSLTCompiler(xsl_file=tmp_path / "driver.xsl")
        source = tmp_path / "source.xml"
        source.touch()
        compiler.compile(source, output_path)
        assert output_path.is_dir()

    def test_invokes_stylesheet(self, tmp_path, mock_saxon):
        mock_cls, mock_proc = mock_saxon
        driver = tmp_path / "driver.xsl"
        compiler = XSLTCompiler(xsl_file=driver)
        source = tmp_path / "source.xml"
        source.touch()
        compiler.compile(source, tmp_path / "out")
        mock_proc.new_xslt30_processor().compile_stylesheet.assert_called_once_with(
            stylesheet_file=str(driver.resolve())
        )

    def test_passes_params_to_transformer(self, tmp_path, mock_saxon):
        mock_cls, mock_proc = mock_saxon
        transformer = mock_proc.new_xslt30_processor().compile_stylesheet()
        compiler = XSLTCompiler(xsl_file=tmp_path / "driver.xsl")
        source = tmp_path / "source.xml"
        source.touch()
        compiler.compile(source, tmp_path / "out", params={"foo": "bar", "baz": "qux"})
        calls = [str(c) for c in transformer.set_parameter.call_args_list]
        assert any("foo" in c for c in calls)
        assert any("baz" in c for c in calls)

    def test_raises_runtime_error_on_saxon_error(self, tmp_path, mock_saxon):
        mock_cls, mock_proc = mock_saxon
        mock_proc.new_xslt30_processor().compile_stylesheet(
        ).transform_to_string.side_effect = RuntimeError("Saxon failed")
        compiler = XSLTCompiler(xsl_file=tmp_path / "driver.xsl")
        source = tmp_path / "source.xml"
        source.touch()
        with pytest.raises(RuntimeError):
            compiler.compile(source, tmp_path / "out")

    def test_raises_on_error_message(self, tmp_path, mock_saxon):
        mock_cls, mock_proc = mock_saxon
        mock_proc.new_xslt30_processor.return_value.error_message = "Saxon error"
        compiler = XSLTCompiler(xsl_file=tmp_path / "driver.xsl")
        source = tmp_path / "source.xml"
        source.touch()
        with pytest.raises(RuntimeError, match="Saxon error"):
            compiler.compile(source, tmp_path / "out")


# ---------------------------------------------------------------------------
# PageCompiler
# ---------------------------------------------------------------------------

class TestPageCompilerConstruction:

    def test_accepts_strategy_and_driver(self, tmp_path, card_strategy):
        compiler = PageCompiler(strategy=card_strategy, driver=tmp_path / "driver.xsl")
        assert compiler is not None

    def test_driver_coerced_to_path(self, tmp_path, card_strategy):
        compiler = PageCompiler(strategy=card_strategy, driver=str(tmp_path / "driver.xsl"))
        # No public accessor, but construction must not raise
        assert compiler is not None


class TestPageCompilerCompile:

    def test_creates_output_directory(self, tmp_path, seneca_doc,
                                      card_strategy, mock_saxon):
        output_path = tmp_path / "output" / "deep" / "path"
        assert not output_path.exists()

        compiler = PageCompiler(strategy=card_strategy, driver=tmp_path / "driver.xsl")
        compiler.compile(seneca_doc, output_path)

        assert output_path.is_dir()

    def test_invokes_saxon_with_correct_stylesheet(self, tmp_path, seneca_doc,
                                                   card_strategy, mock_saxon):
        mock_cls, mock_proc = mock_saxon
        driver = tmp_path / "html" / "driver.xsl"

        compiler = PageCompiler(strategy=card_strategy, driver=driver)
        compiler.compile(seneca_doc, tmp_path / "out")

        mock_proc.new_xslt30_processor().compile_stylesheet.assert_called_once_with(
            stylesheet_file=str(driver.resolve())
        )

    def test_sets_chunk_unit_parameter(self, tmp_path, seneca_doc,
                                       card_strategy, mock_saxon):
        mock_cls, mock_proc = mock_saxon
        transformer = mock_proc.new_xslt30_processor().compile_stylesheet()

        compiler = PageCompiler(strategy=card_strategy, driver=tmp_path / "driver.xsl")
        compiler.compile(seneca_doc, tmp_path / "out")

        calls = [str(c) for c in transformer.set_parameter.call_args_list]
        assert any("chunk-unit" in c for c in calls)

    def test_sets_chunk_strategy_parameter(self, tmp_path, seneca_doc,
                                           card_strategy, mock_saxon):
        mock_cls, mock_proc = mock_saxon
        transformer = mock_proc.new_xslt30_processor().compile_stylesheet()

        compiler = PageCompiler(strategy=card_strategy, driver=tmp_path / "driver.xsl")
        compiler.compile(seneca_doc, tmp_path / "out")

        calls = [str(c) for c in transformer.set_parameter.call_args_list]
        assert any("chunk-strategy" in c for c in calls)

    def test_sets_output_dir_parameter(self, tmp_path, seneca_doc,
                                       card_strategy, mock_saxon):
        mock_cls, mock_proc = mock_saxon
        transformer = mock_proc.new_xslt30_processor().compile_stylesheet()
        output_path = tmp_path / "out"

        compiler = PageCompiler(strategy=card_strategy, driver=tmp_path / "driver.xsl")
        compiler.compile(seneca_doc, output_path)

        calls = [str(c) for c in transformer.set_parameter.call_args_list]
        assert any("output-dir" in c for c in calls)

    def test_returns_none_on_success(self, tmp_path, seneca_doc,
                                     card_strategy, mock_saxon):
        compiler = PageCompiler(strategy=card_strategy, driver=tmp_path / "driver.xsl")
        result = compiler.compile(seneca_doc, tmp_path / "out")
        assert result is None

    def test_wraps_saxon_exception_as_compilation_error(self, tmp_path,
                                                         seneca_doc,
                                                         card_strategy,
                                                         mock_saxon):
        mock_cls, mock_proc = mock_saxon
        mock_proc.new_xslt30_processor().compile_stylesheet(
        ).transform_to_string.side_effect = RuntimeError("Saxon exploded")

        compiler = PageCompiler(strategy=card_strategy, driver=tmp_path / "driver.xsl")

        with pytest.raises(CompilationError) as exc_info:
            compiler.compile(seneca_doc, tmp_path / "out")

        assert exc_info.value.document is seneca_doc
        assert isinstance(exc_info.value.cause, RuntimeError)

    def test_compilation_error_message_mentions_xslt(self, tmp_path,
                                                      seneca_doc,
                                                      card_strategy,
                                                      mock_saxon):
        mock_cls, mock_proc = mock_saxon
        mock_proc.new_xslt30_processor().compile_stylesheet(
        ).transform_to_string.side_effect = RuntimeError("oops")

        compiler = PageCompiler(strategy=card_strategy, driver=tmp_path / "driver.xsl")

        with pytest.raises(CompilationError) as exc_info:
            compiler.compile(seneca_doc, tmp_path / "out")

        assert "XSLT" in exc_info.value.message


# ---------------------------------------------------------------------------
# CatalogCompiler
# ---------------------------------------------------------------------------

def make_entry(urn: str, title: str = "Test Title", author: str = "Test Author",
               language: str = "lat") -> TEIMetadata:
    return TEIMetadata(
        urn=urn,
        title=title,
        author=author,
        language=language,
        text_type="prose",
        source_path=Path(f"/fake/{urn}.xml"),
    )


class TestCatalogCompilerConstruction:

    def test_construction_does_not_raise(self, tmp_path):
        site_map = SiteMap(tmp_path)
        compiler = CatalogCompiler(site_map=site_map)
        assert compiler is not None


class TestCatalogCompilerCompile:

    def test_creates_html_file(self, tmp_path):
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        entry = make_entry("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        output_path = tmp_path / "catalog" / "lat.html"
        compiler.compile([entry], output_path)
        assert output_path.exists()

    def test_html_contains_title_and_author(self, tmp_path):
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        entry = make_entry(
            "urn:cts:latinLit:phi1017.phi007.perseus-lat2",
            title="Agamemnon",
            author="Seneca",
        )
        output_path = tmp_path / "catalog" / "lat.html"
        compiler.compile([entry], output_path)
        html = output_path.read_text(encoding="utf-8")
        assert "Agamemnon" in html
        assert "Seneca" in html

    def test_links_to_first_chunk_when_manifest_exists(self, tmp_path):
        site_map = SiteMap(tmp_path / "output")
        urn = "urn:cts:latinLit:phi1017.phi007.perseus-lat2"

        # Write a real index.json so CatalogCompiler can find the first chunk.
        chunk_dir = site_map.chunk_dir(urn)
        manifest = {
            "base_urn": urn,
            "title": "Agamemnon",
            "chunks": [{"n": "1", "file": "card_1.html", "urn": ""}],
        }
        (chunk_dir / "index.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        compiler = CatalogCompiler(site_map=site_map)
        entry = make_entry(urn, title="Agamemnon", author="Seneca")
        output_path = tmp_path / "catalog" / "lat.html"
        compiler.compile([entry], output_path)

        html = output_path.read_text(encoding="utf-8")
        assert "card_1.html" in html
        assert 'href="' in html

    def test_graceful_when_manifest_missing(self, tmp_path):
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        entry = make_entry("urn:cts:latinLit:phi1017.phi007.perseus-lat2",
                           title="Agamemnon")
        output_path = tmp_path / "catalog" / "lat.html"
        # No index.json exists — must not raise.
        compiler.compile([entry], output_path)
        html = output_path.read_text(encoding="utf-8")
        assert "Agamemnon" in html

    def test_empty_entries_writes_nothing(self, tmp_path):
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        output_path = tmp_path / "catalog" / "lat.html"
        compiler.compile([], output_path)
        assert not output_path.exists()

    def test_entries_sorted_by_author_then_title(self, tmp_path):
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        entries = [
            make_entry("urn:cts:latinLit:phi0003.phi001.test", title="Odes",
                       author="Horace"),
            make_entry("urn:cts:latinLit:phi0003.phi002.test", title="Aeneid",
                       author="Virgil"),
            make_entry("urn:cts:latinLit:phi0003.phi003.test", title="Amores",
                       author="Ovid"),
        ]
        output_path = tmp_path / "catalog" / "lat.html"
        compiler.compile(entries, output_path)
        html = output_path.read_text(encoding="utf-8")
        # Horace comes before Ovid, Ovid before Virgil
        assert html.index("Horace") < html.index("Ovid") < html.index("Virgil")

    def test_catalog_has_page_chrome(self, tmp_path):
        """Catalog page must have viewport meta, site header, main, and footer."""
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        entry = make_entry("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        output_path = tmp_path / "catalog" / "lat.html"
        compiler.compile([entry], output_path)
        html = output_path.read_text(encoding="utf-8")
        assert 'name="viewport"' in html
        assert 'class="site-header"' in html
        assert '<main' in html
        assert 'class="site-footer"' in html


class TestCatalogCompilerIndex:

    def test_compile_index_creates_root_file(self, tmp_path):
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        languages = {
            "lat": [make_entry("urn:cts:latinLit:phi1017.phi007.test")],
        }
        output_path = tmp_path / "index.html"
        compiler.compile_index(languages, output_path)
        assert output_path.exists()

    def test_compile_index_links_to_language_catalogs(self, tmp_path):
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        languages = {
            "lat": [make_entry("urn:cts:latinLit:phi1017.phi007.test")],
            "grc": [make_entry("urn:cts:greekLit:tlg0011.tlg001.test",
                               language="grc")],
        }
        output_path = tmp_path / "index.html"
        compiler.compile_index(languages, output_path)
        html = output_path.read_text(encoding="utf-8")
        assert "/catalog/lat.html" in html
        assert "/catalog/grc.html" in html
        assert "Latin" in html
        assert "Greek" in html

    def test_index_has_page_chrome(self, tmp_path):
        """Index page must have viewport meta, site header, tagline, main, and footer."""
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        languages = {"lat": [make_entry("urn:cts:latinLit:phi1017.phi007.test")]}
        output_path = tmp_path / "index.html"
        compiler.compile_index(languages, output_path)
        html = output_path.read_text(encoding="utf-8")
        assert 'name="viewport"' in html
        assert 'class="site-header"' in html
        assert 'class="tagline"' in html
        assert '<main' in html
        assert 'class="site-footer"' in html


# ---------------------------------------------------------------------------
# copy_static_assets
# ---------------------------------------------------------------------------

class TestCopyStaticAssets:

    def test_copies_css_to_output(self, tmp_path):
        src = tmp_path / "static" / "css"
        src.mkdir(parents=True)
        (src / "catalog.css").write_text("body {}", encoding="utf-8")
        out = tmp_path / "output"
        copy_static_assets(tmp_path / "static", out)
        assert (out / "css" / "catalog.css").exists()

    def test_noop_when_src_css_missing(self, tmp_path):
        out = tmp_path / "output"
        copy_static_assets(tmp_path / "nonexistent", out)
        assert not out.exists()

    def test_catalog_page_references_external_stylesheet(self, tmp_path):
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        entry = make_entry("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        output_path = tmp_path / "catalog" / "lat.html"
        compiler.compile([entry], output_path)
        html = output_path.read_text(encoding="utf-8")
        assert '<link rel="stylesheet"' in html
        assert "<style>" not in html

    def test_index_page_references_external_stylesheet(self, tmp_path):
        site_map = SiteMap(tmp_path / "output")
        compiler = CatalogCompiler(site_map=site_map)
        languages = {"lat": [make_entry("urn:cts:latinLit:phi1017.phi007.test")]}
        output_path = tmp_path / "index.html"
        compiler.compile_index(languages, output_path)
        html = output_path.read_text(encoding="utf-8")
        assert '<link rel="stylesheet"' in html
        assert "<style>" not in html


# ---------------------------------------------------------------------------
# PageCompiler integration tests (require real Saxon + XSLT)
# ---------------------------------------------------------------------------

DRIVER = Path(__file__).parent.parent / "src" / "xslt" / "html" / "driver.xsl"
DTD_FIXTURE_PATH = DATA_DIR / "dtd_entity_test.xml"


@pytest.mark.slow
class TestPageCompilerIntegration:
    """Run real Saxon transformations against fixture files.

    These tests are slow (Saxon JVM startup + full XSLT transform) and
    are excluded from the default test run.  Run with:
        pdm run test -m slow
    """

    def test_seneca_produces_chunks(self, tmp_path):
        doc = TEIDocument.from_path(SENECA_PATH)
        strategy = MilestoneStrategy(unit="card")
        compiler = PageCompiler(strategy=strategy, driver=DRIVER)
        compiler.compile(doc, tmp_path)

        assert (tmp_path / "card_1.html").exists(), \
            "Expected card_1.html to be produced by the XSLT"
        assert (tmp_path / "index.json").exists(), \
            "Expected index.json manifest to be produced"
        manifest = json.loads((tmp_path / "index.json").read_text())
        assert "chunks" in manifest
        assert len(manifest["chunks"]) > 0

    def test_seneca_chunk_contains_html_structure(self, tmp_path):
        doc = TEIDocument.from_path(SENECA_PATH)
        strategy = MilestoneStrategy(unit="card")
        compiler = PageCompiler(strategy=strategy, driver=DRIVER)
        compiler.compile(doc, tmp_path)

        html = (tmp_path / "card_1.html").read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html or "<html" in html
        assert "<nav" in html
        assert 'name="viewport"' in html
        assert 'class="site-header"' in html
        assert 'class="site-footer"' in html
        assert "<main" in html
        assert "toc.html" in html

    def test_seneca_toc_is_generated(self, tmp_path):
        """generate_chunks.xsl must write a toc.html alongside index.json."""
        doc = TEIDocument.from_path(SENECA_PATH)
        strategy = MilestoneStrategy(unit="card")
        compiler = PageCompiler(strategy=strategy, driver=DRIVER)
        compiler.compile(doc, tmp_path)

        assert (tmp_path / "toc.html").exists(), "Expected toc.html to be produced"
        toc = (tmp_path / "toc.html").read_text(encoding="utf-8")
        assert "card_1.html" in toc
        assert 'class="toc-list"' in toc

    def test_dtd_document_produces_chunks(self, tmp_path):
        """Documents with DOCTYPE references compile after the DTD parser fix."""
        doc = TEIDocument.from_path(DTD_FIXTURE_PATH)
        strategy = MilestoneStrategy(unit="section")
        compiler = PageCompiler(strategy=strategy, driver=DRIVER)
        compiler.compile(doc, tmp_path)

        assert (tmp_path / "section_1.html").exists()
        assert (tmp_path / "index.json").exists()
        manifest = json.loads((tmp_path / "index.json").read_text())
        assert len(manifest["chunks"]) == 2

    def test_caracallus_produces_chapter_chunks(self, tmp_path):
        """phi2331.phi013 -- SHA Antoninus Caracallus.

        The refState hint selects DivisionStrategy(chapter), which uses
        generate_div_chunks.xsl.  Expect one file per chapter (~11 chapters)
        rather than one file per section (~100 sections).
        """
        from mvp.strategy import DivisionStrategy
        doc = TEIDocument.from_path(DATA_DIR / "phi2331.phi013.perseus-lat2.xml")
        strategy = DivisionStrategy(div_type="textpart", subtype="chapter")
        compiler = PageCompiler(strategy=strategy, driver=DRIVER)
        compiler.compile(doc, tmp_path)

        assert (tmp_path / "chapter_1.html").exists()
        assert (tmp_path / "index.json").exists()
        manifest = json.loads((tmp_path / "index.json").read_text())
        assert len(manifest["chunks"]) == 11, \
            "Expected 11 chapters in Antoninus Caracallus"
        html = (tmp_path / "chapter_1.html").read_text(encoding="utf-8")
        assert "<p>" in html, "Chapter 1 should contain paragraph content"

    def test_compile_enriches_index_json_with_author_and_language(
            self, tmp_path):
        """PageCompiler.compile() must inject author and language into index.json."""
        doc = TEIDocument.from_path(DATA_DIR / "phi1017.phi007.perseus-lat2.xml")
        strategy = MilestoneStrategy(unit="card")
        compiler = PageCompiler(strategy=strategy, driver=DRIVER)
        compiler.compile(doc, tmp_path)

        manifest = json.loads((tmp_path / "index.json").read_text())
        assert "author" in manifest, "index.json must contain 'author'"
        assert "language" in manifest, "index.json must contain 'language'"
        assert manifest["language"] == "lat"
