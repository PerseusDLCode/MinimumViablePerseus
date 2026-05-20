# tests/test_pipeline.py
#
# Tests for BuildPipeline.
#
# Testing strategy:
#   BuildPipeline owns orchestration logic: error collection, skip handling,
#   SystemExit on failures, catalog grouping by language, and the guard that
#   CatalogCompiler is only invoked when there are successfully compiled docs.
#   None of this requires real Saxon or real TEI files.
#
#   We mock:
#     - Corpus.documents() — controls what documents the pipeline sees
#     - mvp.pipeline.PageCompiler — controls compilation success/failure
#       (PageCompiler is constructed inside run(), so we patch the class
#       in the mvp.pipeline namespace)
#     - mvp.pipeline.CatalogCompiler — controls catalog compilation
#     - mvp.pipeline.StrategySelector — controls strategy selection
#
#   NOTE on StrategySelector patching: BuildPipeline constructs
#   StrategySelector() eagerly in __init__, storing it as self._selector.
#   Patching mvp.pipeline.StrategySelector after construction has no effect
#   on the already-created instance.  Tests that need to control strategy
#   selection must therefore patch StrategySelector *before* constructing
#   the pipeline, i.e. the pipeline must be constructed inside the patch
#   context.  The make_pipeline() helper handles this.
#
#   NOTE on PageCompiler design: BuildPipeline also constructs PageCompiler
#   instances internally in run() rather than accepting a compiler factory
#   via injection.  This makes patching the class in the mvp.pipeline
#   namespace sufficient for controlling compilation behaviour.  If the
#   pipeline becomes harder to test as it grows, consider refactoring to
#   accept a compiler factory.

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

from mvp.compilers import CompilationError
from mvp.corpus import Corpus
from mvp.models import TEIMetadata
from mvp.pipeline import BuildPipeline
from mvp.site_map import SiteMap
from mvp.strategy import MilestoneStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"


def make_metadata(urn: str, language: str = "lat") -> TEIMetadata:
    """Return a minimal TEIMetadata instance for use in pipeline tests."""
    return TEIMetadata(
        urn=urn,
        title="Test Title",
        author="Test Author",
        language=language,
        text_type="prose",
        source_path=Path(f"/fake/{urn}.xml"),
    )


def make_mock_doc(urn: str, language: str = "lat") -> MagicMock:
    """Return a mock TEIDocument with realistic metadata."""
    doc = MagicMock()
    doc.metadata = make_metadata(urn, language)
    doc.path = Path(f"/fake/{urn}.xml")
    return doc


def make_pipeline(tmp_path, corpus, selector_side_effect=None,
                  selector_return_value=None):
    """Construct a BuildPipeline with StrategySelector patched at init time.

    Because BuildPipeline constructs StrategySelector() eagerly in __init__,
    the patch must be active when the pipeline is constructed.  This helper
    wraps that construction so callers don't have to manage the patch context
    manually for every test.

    Returns (pipeline, mock_selector_instance) so tests can make assertions
    about selector calls if needed.
    """
    if selector_return_value is None and selector_side_effect is None:
        selector_return_value = MilestoneStrategy(unit="card")

    with patch("mvp.pipeline.StrategySelector") as mock_selector_cls:
        if selector_side_effect is not None:
            mock_selector_cls.return_value.select.side_effect = (
                selector_side_effect
            )
        else:
            mock_selector_cls.return_value.select.return_value = (
                selector_return_value
            )
        site_map = SiteMap(tmp_path / "output")
        pl = BuildPipeline(
            corpora=[corpus],
            site_map=site_map,
            xslt_root=tmp_path / "xslt",
        )
        mock_selector = mock_selector_cls.return_value

    # The pipeline is constructed; the patch is no longer active, but
    # mock_selector is the instance stored in pl._selector, so its
    # configured side_effect / return_value remain in effect.
    return pl, site_map, mock_selector


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestBuildPipelineConstruction:

    def test_construction_does_not_raise(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        pl, _, _ = make_pipeline(tmp_path, corpus)
        assert pl is not None

    def test_accepts_multiple_corpora(self, tmp_path):
        corpus_a = MagicMock(spec=Corpus)
        corpus_b = MagicMock(spec=Corpus)
        corpus_a.documents.return_value = []
        corpus_b.documents.return_value = []
        with patch("mvp.pipeline.StrategySelector"):
            pl = BuildPipeline(
                corpora=[corpus_a, corpus_b],
                site_map=SiteMap(tmp_path / "output"),
                xslt_root=tmp_path / "xslt",
            )
        assert pl is not None


# ---------------------------------------------------------------------------
# Successful compilation
# ---------------------------------------------------------------------------

class TestBuildPipelineSuccess:

    def test_run_compiles_each_document(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, site_map, _ = make_pipeline(tmp_path, corpus)

        with patch("mvp.pipeline.PageCompiler") as mock_compiler_cls, \
             patch("mvp.pipeline.CatalogCompiler"):
            mock_compiler_cls.return_value.compile.return_value = None
            pl.run()

        mock_compiler_cls.return_value.compile.assert_called_once_with(
            doc, site_map.chunk_dir(doc.metadata.urn),
            catalog_url=ANY,
        )

    def test_run_returns_none_on_success(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with patch("mvp.pipeline.PageCompiler") as mock_compiler_cls, \
             patch("mvp.pipeline.CatalogCompiler"):
            mock_compiler_cls.return_value.compile.return_value = None
            result = pl.run()

        assert result is None

    def test_run_invokes_catalog_compiler_after_page_compilation(
            self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with patch("mvp.pipeline.PageCompiler") as mock_page_cls, \
             patch("mvp.pipeline.CatalogCompiler") as mock_catalog_cls:
            mock_page_cls.return_value.compile.return_value = None
            pl.run()

        mock_catalog_cls.return_value.compile.assert_called_once()

    def test_catalog_compiler_receives_collected_metadata(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2",
                            language="lat")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with patch("mvp.pipeline.PageCompiler") as mock_page_cls, \
             patch("mvp.pipeline.CatalogCompiler") as mock_catalog_cls:
            mock_page_cls.return_value.compile.return_value = None
            pl.run()

        # compile() is called as compile(entries=..., output_path=...)
        # or compile([...], path) depending on call site; handle both.
        call_args = mock_catalog_cls.return_value.compile.call_args
        entries = call_args[1].get("entries") if call_args[1] else call_args[0][0]
        assert doc.metadata in entries

    def test_catalog_grouped_by_language(self, tmp_path):
        """Documents in different languages produce separate catalog calls."""
        corpus = MagicMock(spec=Corpus)
        lat_doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2",
                                language="lat")
        grc_doc = make_mock_doc("urn:cts:greekLit:tlg0011.tlg001.perseus-grc2",
                                language="grc")
        corpus.documents.return_value = [lat_doc, grc_doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with patch("mvp.pipeline.PageCompiler") as mock_page_cls, \
             patch("mvp.pipeline.CatalogCompiler") as mock_catalog_cls:
            mock_page_cls.return_value.compile.return_value = None
            pl.run()

        assert mock_catalog_cls.return_value.compile.call_count == 2

    def test_compile_index_called_after_catalogs(self, tmp_path):
        """compile_index() is called once after all per-language catalogs."""
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2",
                            language="lat")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with patch("mvp.pipeline.PageCompiler") as mock_page_cls, \
             patch("mvp.pipeline.CatalogCompiler") as mock_catalog_cls:
            mock_page_cls.return_value.compile.return_value = None
            pl.run()

        mock_catalog_cls.return_value.compile_index.assert_called_once()

    def test_multiple_corpora_documents_all_compiled(self, tmp_path):
        """Documents from all corpora are compiled before catalog is written."""
        corpus_a = MagicMock(spec=Corpus)
        corpus_b = MagicMock(spec=Corpus)
        doc_a = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2",
                              language="lat")
        doc_b = make_mock_doc("urn:cts:greekLit:tlg0011.tlg001.perseus-grc2",
                              language="grc")
        corpus_a.documents.return_value = [doc_a]
        corpus_b.documents.return_value = [doc_b]

        with patch("mvp.pipeline.StrategySelector") as mock_sel:
            mock_sel.return_value.select.return_value = MilestoneStrategy(unit="card")
            site_map = SiteMap(tmp_path / "output")
            pl = BuildPipeline(
                corpora=[corpus_a, corpus_b],
                site_map=site_map,
                xslt_root=tmp_path / "xslt",
            )

        with patch("mvp.pipeline.PageCompiler") as mock_page_cls, \
             patch("mvp.pipeline.CatalogCompiler") as mock_catalog_cls:
            mock_page_cls.return_value.compile.return_value = None
            pl.run()

        assert mock_page_cls.return_value.compile.call_count == 2
        assert mock_catalog_cls.return_value.compile.call_count == 2

    def test_empty_corpus_does_not_invoke_catalog_compiler(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        corpus.documents.return_value = []
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with patch("mvp.pipeline.PageCompiler"), \
             patch("mvp.pipeline.CatalogCompiler") as mock_catalog_cls:
            pl.run()

        mock_catalog_cls.return_value.compile.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestBuildPipelineErrorHandling:

    def test_raises_system_exit_when_compilation_fails(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with patch("mvp.pipeline.PageCompiler") as mock_compiler_cls, \
             patch("mvp.pipeline.CatalogCompiler"):
            mock_compiler_cls.return_value.compile.side_effect = (
                CompilationError(document=doc, message="Saxon exploded")
            )
            with pytest.raises(SystemExit):
                pl.run()

    def test_collects_all_errors_before_raising(self, tmp_path):
        """All documents are attempted even if some fail (collect-all policy)."""
        corpus = MagicMock(spec=Corpus)
        doc_a = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        doc_b = make_mock_doc("urn:cts:latinLit:phi1017.phi008.perseus-lat2")
        corpus.documents.return_value = [doc_a, doc_b]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        compile_calls = []

        def failing_compile(doc, output_path, **kwargs):
            compile_calls.append(doc)
            raise CompilationError(document=doc, message="fail")

        with patch("mvp.pipeline.PageCompiler") as mock_compiler_cls, \
             patch("mvp.pipeline.CatalogCompiler"):
            mock_compiler_cls.return_value.compile.side_effect = failing_compile
            with pytest.raises(SystemExit):
                pl.run()

        # Both documents must have been attempted despite the first failure
        assert len(compile_calls) == 2

    def test_skips_documents_with_no_matching_strategy(self, tmp_path):
        """StrategySelector.ValueError causes a skip, not a failure."""
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(
            tmp_path, corpus,
            selector_side_effect=ValueError("No chunking strategy found"),
        )

        with patch("mvp.pipeline.PageCompiler") as mock_compiler_cls, \
             patch("mvp.pipeline.CatalogCompiler"):
            # Should not raise SystemExit — skips are not failures
            pl.run()

        mock_compiler_cls.return_value.compile.assert_not_called()

    def test_failed_documents_excluded_from_catalog(self, tmp_path):
        """Metadata from failed compilations must not reach CatalogCompiler."""
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with patch("mvp.pipeline.PageCompiler") as mock_compiler_cls, \
             patch("mvp.pipeline.CatalogCompiler") as mock_catalog_cls:
            mock_compiler_cls.return_value.compile.side_effect = (
                CompilationError(document=doc, message="fail")
            )
            with pytest.raises(SystemExit):
                pl.run()

        mock_catalog_cls.return_value.compile.assert_not_called()

    def test_system_exit_message_mentions_error_count(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with patch("mvp.pipeline.PageCompiler") as mock_compiler_cls, \
             patch("mvp.pipeline.CatalogCompiler"):
            mock_compiler_cls.return_value.compile.side_effect = (
                CompilationError(document=doc, message="fail")
            )
            with pytest.raises(SystemExit) as exc_info:
                pl.run()

        assert "1" in str(exc_info.value)
