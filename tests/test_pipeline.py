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
#     - mvp.pipeline.StrategySelector — controls strategy selection
#     - mvp.pipeline.CitationIndexGenerator — controls citation index generation
#     - mvp.pipeline.PageCompiler — controls compilation success/failure
#     - mvp.pipeline.CatalogCompiler — controls catalog compilation
#
#   NOTE on StrategySelector patching: BuildPipeline constructs
#   StrategySelector() eagerly in __init__, storing it as self._selector.
#   Patching mvp.pipeline.StrategySelector after construction has no effect
#   on the already-created instance.  Tests that need to control strategy
#   selection must therefore patch StrategySelector *before* constructing
#   the pipeline, i.e. the pipeline must be constructed inside the patch
#   context.  The make_pipeline() helper handles this.
#
#   NOTE on PageCompiler design: BuildPipeline constructs PageCompiler
#   instances internally in run() rather than accepting a compiler factory
#   via injection.  This makes patching the class in the mvp.pipeline
#   namespace sufficient for controlling compilation behaviour.
#
#   NOTE on CitationIndexGenerator: same pattern as PageCompiler — patched in
#   the mvp.pipeline namespace.  TEIDocument is also patched to avoid real
#   file I/O when constructing the generator.

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import ANY, MagicMock, call, patch

import pytest

from mvp.compilers import CompilationError
from mvp.corpus import Corpus
from mvp.models import TEIMetadata
from mvp.pipeline import BuildPipeline
from mvp.reference_parser import ConfigurationError
from mvp.site_map import SiteMap
from mvp.strategy import MilestoneStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"


def make_metadata(urn: str, language: str = "lat") -> TEIMetadata:
    return TEIMetadata(
        urn=urn, title="Test Title", author="Test Author",
        language=language, text_type="prose",
        source_path=Path(f"/fake/{urn}.xml"),
    )


def make_mock_doc(urn: str, language: str = "lat") -> MagicMock:
    doc = MagicMock()
    doc.metadata = make_metadata(urn, language)
    doc.path = Path(f"/fake/{urn}.xml")
    return doc


def make_pipeline(tmp_path, corpus, selector_side_effect=None,
                  selector_return_value=None):
    """Construct a BuildPipeline with StrategySelector patched at init time."""
    if selector_return_value is None and selector_side_effect is None:
        selector_return_value = MilestoneStrategy(unit="card")

    with patch("mvp.site.pipeline.StrategySelector") as mock_selector_cls:
        if selector_side_effect is not None:
            mock_selector_cls.return_value.select.side_effect = selector_side_effect
        else:
            mock_selector_cls.return_value.select.return_value = selector_return_value
        site_map = SiteMap(tmp_path / "output")
        pl = BuildPipeline(
            corpora=[corpus],
            site_map=site_map,
            driver=tmp_path / "driver.xsl",
        )
        mock_selector = mock_selector_cls.return_value

    return pl, site_map, mock_selector


@contextmanager
def mock_runtime(*, page_effect=None, cig_effect=None):
    """Patch PageCompiler, CatalogCompiler, CitationIndexGenerator, and TEIDocument.

    Yields (mock_page_cls, mock_catalog_cls, mock_cig_cls).
    """
    with patch("mvp.site.pipeline.PageCompiler") as mock_page_cls, \
         patch("mvp.site.pipeline.CatalogCompiler") as mock_catalog_cls, \
         patch("mvp.site.pipeline.CitationIndexGenerator") as mock_cig_cls, \
         patch("mvp.site.pipeline.LenientTEIDocument"):
        if page_effect is not None:
            mock_page_cls.return_value.compile.side_effect = page_effect
        else:
            mock_page_cls.return_value.compile.return_value = None
        if cig_effect is not None:
            mock_cig_cls.return_value.write.side_effect = cig_effect
        yield mock_page_cls, mock_catalog_cls, mock_cig_cls


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
        with patch("mvp.site.pipeline.StrategySelector"):
            pl = BuildPipeline(
                corpora=[corpus_a, corpus_b],
                site_map=SiteMap(tmp_path / "output"),
                driver=tmp_path / "driver.xsl",
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

        with mock_runtime() as (mock_page_cls, _, _):
            pl.run()

        mock_page_cls.return_value.compile.assert_called_once_with(
            doc, site_map.chunk_dir(doc.metadata.urn), catalog_url=ANY,
        )

    def test_run_returns_none_on_success(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime():
            result = pl.run()

        assert result is None

    def test_run_invokes_catalog_compiler_after_page_compilation(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime() as (_, mock_catalog_cls, _):
            pl.run()

        mock_catalog_cls.return_value.compile.assert_called_once()

    def test_catalog_compiler_receives_collected_metadata(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2",
                            language="lat")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime() as (_, mock_catalog_cls, _):
            pl.run()

        call_args = mock_catalog_cls.return_value.compile.call_args
        entries = call_args[1].get("entries") if call_args[1] else call_args[0][0]
        assert doc.metadata in entries

    def test_catalog_grouped_by_language(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        lat_doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2",
                                language="lat")
        grc_doc = make_mock_doc("urn:cts:greekLit:tlg0011.tlg001.perseus-grc2",
                                language="grc")
        corpus.documents.return_value = [lat_doc, grc_doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime() as (_, mock_catalog_cls, _):
            pl.run()

        assert mock_catalog_cls.return_value.compile.call_count == 2

    def test_compile_index_called_after_catalogs(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2",
                            language="lat")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime() as (_, mock_catalog_cls, _):
            pl.run()

        mock_catalog_cls.return_value.compile_index.assert_called_once()

    def test_multiple_corpora_documents_all_compiled(self, tmp_path):
        corpus_a = MagicMock(spec=Corpus)
        corpus_b = MagicMock(spec=Corpus)
        doc_a = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2",
                              language="lat")
        doc_b = make_mock_doc("urn:cts:greekLit:tlg0011.tlg001.perseus-grc2",
                              language="grc")
        corpus_a.documents.return_value = [doc_a]
        corpus_b.documents.return_value = [doc_b]

        with patch("mvp.site.pipeline.StrategySelector") as mock_sel:
            mock_sel.return_value.select.return_value = MilestoneStrategy(unit="card")
            site_map = SiteMap(tmp_path / "output")
            pl = BuildPipeline(
                corpora=[corpus_a, corpus_b],
                site_map=site_map,
                driver=tmp_path / "driver.xsl",
            )

        with mock_runtime() as (mock_page_cls, mock_catalog_cls, _):
            pl.run()

        assert mock_page_cls.return_value.compile.call_count == 2
        assert mock_catalog_cls.return_value.compile.call_count == 2

    def test_empty_corpus_does_not_invoke_catalog_compiler(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        corpus.documents.return_value = []
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime() as (_, mock_catalog_cls, _):
            pl.run()

        mock_catalog_cls.return_value.compile.assert_not_called()


# ---------------------------------------------------------------------------
# Citation index generation
# ---------------------------------------------------------------------------

class TestBuildPipelineCitationIndex:

    def test_citation_index_generated_for_each_document(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, site_map, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime() as (_, _, mock_cig_cls):
            pl.run()

        mock_cig_cls.return_value.write.assert_called_once_with(
            site_map.citations_path(doc.metadata.urn)
        )

    def test_citation_index_generated_before_page_compilation(self, tmp_path):
        """write() must be called before compile() for the same document."""
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        call_order = []

        with mock_runtime() as (mock_page_cls, _, mock_cig_cls):
            mock_cig_cls.return_value.write.side_effect = (
                lambda *a, **kw: call_order.append("write")
            )
            mock_page_cls.return_value.compile.side_effect = (
                lambda *a, **kw: call_order.append("compile")
            )
            pl.run()

        assert call_order == ["write", "compile"]

    def test_citation_index_config_error_does_not_prevent_compilation(
            self, tmp_path):
        """A ConfigurationError from CIG logs a warning but still compiles the page."""
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime(
            cig_effect=ConfigurationError("no citeStructure")
        ) as (mock_page_cls, _, _):
            pl.run()

        mock_page_cls.return_value.compile.assert_called_once()

    def test_citation_index_config_error_does_not_count_as_build_failure(
            self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime(cig_effect=ConfigurationError("no citeStructure")):
            result = pl.run()  # must not raise SystemExit

        assert result is None

    def test_citation_index_generated_for_multiple_documents(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc_a = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        doc_b = make_mock_doc("urn:cts:greekLit:tlg0011.tlg001.perseus-grc2",
                              language="grc")
        corpus.documents.return_value = [doc_a, doc_b]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime() as (_, _, mock_cig_cls):
            pl.run()

        assert mock_cig_cls.return_value.write.call_count == 2


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestBuildPipelineErrorHandling:

    def test_raises_system_exit_when_compilation_fails(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime(
            page_effect=CompilationError(document=doc, message="Saxon exploded")
        ):
            with pytest.raises(SystemExit):
                pl.run()

    def test_collects_all_errors_before_raising(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc_a = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        doc_b = make_mock_doc("urn:cts:latinLit:phi1017.phi008.perseus-lat2")
        corpus.documents.return_value = [doc_a, doc_b]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        compile_calls = []

        def failing_compile(doc, output_path, **kwargs):
            compile_calls.append(doc)
            raise CompilationError(document=doc, message="fail")

        with mock_runtime(page_effect=failing_compile):
            with pytest.raises(SystemExit):
                pl.run()

        assert len(compile_calls) == 2

    def test_skips_documents_with_no_matching_strategy(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(
            tmp_path, corpus,
            selector_side_effect=ValueError("No chunking strategy found"),
        )

        with mock_runtime() as (mock_page_cls, _, mock_cig_cls):
            pl.run()

        mock_page_cls.return_value.compile.assert_not_called()
        mock_cig_cls.return_value.write.assert_not_called()

    def test_failed_documents_excluded_from_catalog(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime(
            page_effect=CompilationError(document=doc, message="fail")
        ) as (_, mock_catalog_cls, _):
            with pytest.raises(SystemExit):
                pl.run()

        mock_catalog_cls.return_value.compile.assert_not_called()

    def test_system_exit_message_mentions_error_count(self, tmp_path):
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(tmp_path, corpus)

        with mock_runtime(
            page_effect=CompilationError(document=doc, message="fail")
        ):
            with pytest.raises(SystemExit) as exc_info:
                pl.run()

        assert "1" in str(exc_info.value)

    def test_strategy_skip_does_not_generate_citation_index(self, tmp_path):
        """Skipped documents (no strategy) must not attempt CIG or PageCompiler."""
        corpus = MagicMock(spec=Corpus)
        doc = make_mock_doc("urn:cts:latinLit:phi1017.phi007.perseus-lat2")
        corpus.documents.return_value = [doc]
        pl, _, _ = make_pipeline(
            tmp_path, corpus,
            selector_side_effect=ValueError("no strategy"),
        )

        with mock_runtime() as (mock_page_cls, _, mock_cig_cls):
            pl.run()

        mock_cig_cls.return_value.write.assert_not_called()
        mock_page_cls.return_value.compile.assert_not_called()
