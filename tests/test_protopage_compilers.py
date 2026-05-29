# tests/test_protopage_compilers.py
#
# Tests for ProtopageCompiler and ProtopageRenderer.
#
# Testing strategy:
#   ProtopageCompiler — unit tests mock XSLTCompiler.compile so Saxon is never
#     invoked.  We verify that the correct params are forwarded and that
#     exceptions are wrapped as CompilationError.
#   ProtopageRenderer — unit tests write minimal proto-page XML fixtures into
#     tmp_path and verify that HTML files are produced with the expected
#     content.  No mocking: lxml and Jinja2 are fast enough to run directly.
#   Integration — @pytest.mark.slow tests run the real two-step pipeline
#     against the Thucydides fixture in tests/data/structure-data/.

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mvp.corpus.document import TEIDocument
from mvp.site.compilers import CompilationError, ProtopageCompiler, ProtopageRenderer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
STRUCTURE_DATA = DATA_DIR / "structure-data"
THUCYDIDES_GRC = STRUCTURE_DATA / "tlg0003.tlg001.perseus-grc2.xml"

_XSL_PATH = Path(__file__).parent.parent / "src" / "xslt" / "html" / "generate_protopages.xsl"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def thucydides_doc():
    return TEIDocument.from_path(THUCYDIDES_GRC)


def _write_protopage_fixture(directory: Path) -> None:
    """Write a minimal proto-page fixture (2 chunks) into directory.

    Includes <pubInfo> in <meta> and author/book_subtype/chapter_subtype in
    index.json so that ProtopageRenderer tests can exercise the enriched context
    without running the full XSLT (Part 2) pipeline.
    """
    directory.mkdir(parents=True, exist_ok=True)
    base_urn = "urn:cts:greekLit:tlg0003.tlg001.perseus-grc2"

    _pub_info = """
    <ctsurn>{base_urn}</ctsurn>
    <sourceURL></sourceURL>
    <pubInfo>
      <title>Ἱστορίαι</title>
      <author>Thucydides</author>
      <editor>Henry Stuart Jones</editor>
      <pubPlace>Medford, MA</pubPlace>
      <pubDate>1992</pubDate>
    </pubInfo>""".format(base_urn=base_urn)

    (directory / "chunk_1.1.xml").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<chunk cts-urn="{base_urn}:1.1"
       next-urn="{base_urn}:1.2">
  <meta>
    <title>Ἱστορίαι</title>
    <base-urn>{base_urn}</base-urn>
    <language>grc</language>{_pub_info}
  </meta>
  <content>
    <section n="1" cts-urn="{base_urn}:1.1.1">
      <p>Θουκυδίδης Ἀθηναῖος ξυνέγραψε.</p>
    </section>
  </content>
</chunk>""",
        encoding="utf-8",
    )

    (directory / "chunk_1.2.xml").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<chunk cts-urn="{base_urn}:1.2"
       prev-urn="{base_urn}:1.1">
  <meta>
    <title>Ἱστορίαι</title>
    <base-urn>{base_urn}</base-urn>
    <language>grc</language>{_pub_info}
  </meta>
  <content>
    <section n="1" cts-urn="{base_urn}:1.2.1">
      <p>κίνησις γὰρ αὕτη μεγίστη.</p>
    </section>
  </content>
</chunk>""",
        encoding="utf-8",
    )

    (directory / "index.json").write_text(
        json.dumps({
            "base_urn": base_urn,
            "title": "Ἱστορίαι",
            "language": "grc",
            "author": "Thucydides",
            "book_subtype": "book",
            "chapter_subtype": "chapter",
            "chunks": [
                {"urn": f"{base_urn}:1.1", "file": "chunk_1.1.xml", "book": "1", "chapter": "1"},
                {"urn": f"{base_urn}:1.2", "file": "chunk_1.2.xml", "book": "1", "chapter": "2"},
            ],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# ProtopageCompiler — unit tests
# ---------------------------------------------------------------------------

class TestProtopageCompilerConstruction:

    def test_accepts_xsl_file(self, tmp_path):
        compiler = ProtopageCompiler(xsl_file=tmp_path / "generate_protopages.xsl")
        assert compiler is not None

    def test_accepts_string_path(self, tmp_path):
        compiler = ProtopageCompiler(xsl_file=str(tmp_path / "generate_protopages.xsl"))
        assert compiler is not None


class TestProtopageCompilerCompile:

    @pytest.fixture
    def mock_xslt_compile(self):
        with patch("mvp.site.compilers.protopage_compiler.XSLTCompiler.compile") as m:
            yield m

    def test_passes_output_dir_param(self, tmp_path, thucydides_doc, mock_xslt_compile):
        output_path = tmp_path / "out"
        compiler = ProtopageCompiler(xsl_file=tmp_path / "generate_protopages.xsl")
        compiler.compile(thucydides_doc, output_path)

        _, kwargs = mock_xslt_compile.call_args
        params = kwargs.get("params", mock_xslt_compile.call_args[0][2] if len(mock_xslt_compile.call_args[0]) > 2 else {})
        assert "output-dir" in params

    def test_passes_source_path_to_xslt(self, tmp_path, thucydides_doc, mock_xslt_compile):
        output_path = tmp_path / "out"
        compiler = ProtopageCompiler(xsl_file=tmp_path / "generate_protopages.xsl")
        compiler.compile(thucydides_doc, output_path)

        call_args = mock_xslt_compile.call_args
        source_arg = call_args[0][0] if call_args[0] else call_args[1].get("source")
        assert source_arg == thucydides_doc.path

    def test_wraps_xslt_exception_as_compilation_error(self, tmp_path, thucydides_doc,
                                                         mock_xslt_compile):
        mock_xslt_compile.side_effect = RuntimeError("Saxon exploded")
        compiler = ProtopageCompiler(xsl_file=tmp_path / "generate_protopages.xsl")

        with pytest.raises(CompilationError) as exc_info:
            compiler.compile(thucydides_doc, tmp_path / "out")

        assert exc_info.value.document is thucydides_doc
        assert isinstance(exc_info.value.cause, RuntimeError)

    def test_compilation_error_message_mentions_proto_page(self, tmp_path, thucydides_doc,
                                                             mock_xslt_compile):
        mock_xslt_compile.side_effect = RuntimeError("oops")
        compiler = ProtopageCompiler(xsl_file=tmp_path / "generate_protopages.xsl")

        with pytest.raises(CompilationError) as exc_info:
            compiler.compile(thucydides_doc, tmp_path / "out")

        assert "proto-page" in exc_info.value.message.lower()

    def test_returns_none_on_success(self, tmp_path, thucydides_doc, mock_xslt_compile):
        compiler = ProtopageCompiler(xsl_file=tmp_path / "generate_protopages.xsl")
        result = compiler.compile(thucydides_doc, tmp_path / "out")
        assert result is None


# ---------------------------------------------------------------------------
# ProtopageRenderer — unit tests
# ---------------------------------------------------------------------------

class TestProtopageRendererConstruction:

    def test_uses_builtin_templates_by_default(self, tmp_path):
        renderer = ProtopageRenderer()
        assert renderer is not None

    def test_accepts_custom_template_dir(self, tmp_path):
        renderer = ProtopageRenderer(template_dir=tmp_path)
        assert renderer is not None

    def test_accepts_custom_template_name(self, tmp_path):
        renderer = ProtopageRenderer(template_name="my_chunk.html")
        assert renderer is not None

    def test_uses_named_template(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        (tpl_dir / "minimal.html").write_text(
            "<html><body>SENTINEL {{ chunk.cts_urn }}</body></html>",
            encoding="utf-8",
        )

        output_dir = tmp_path / "html"
        ProtopageRenderer(template_dir=tpl_dir, template_name="minimal.html").compile(
            proto_dir, output_dir
        )

        html = (output_dir / "chunk_1.1.html").read_text(encoding="utf-8")
        assert "SENTINEL" in html
        assert "1.1" in html


class TestProtopageRendererCompile:

    def test_creates_output_directory(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        output_dir = tmp_path / "html" / "deep"

        renderer = ProtopageRenderer()
        renderer.compile(proto_dir, output_dir)

        assert output_dir.is_dir()

    def test_produces_one_html_per_chunk(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        output_dir = tmp_path / "html"

        renderer = ProtopageRenderer()
        renderer.compile(proto_dir, output_dir)

        html_files = list(output_dir.glob("*.html"))
        assert len(html_files) == 2

    def test_html_filenames_derived_from_cts_urns(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        output_dir = tmp_path / "html"

        renderer = ProtopageRenderer()
        renderer.compile(proto_dir, output_dir)

        assert (output_dir / "chunk_1.1.html").exists()
        assert (output_dir / "chunk_1.2.html").exists()

    def test_html_contains_text_content(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        output_dir = tmp_path / "html"

        renderer = ProtopageRenderer()
        renderer.compile(proto_dir, output_dir)

        html = (output_dir / "chunk_1.1.html").read_text(encoding="utf-8")
        assert "Θουκυδίδης" in html

    def test_html_contains_nav_link_to_next(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        output_dir = tmp_path / "html"

        renderer = ProtopageRenderer()
        renderer.compile(proto_dir, output_dir)

        html = (output_dir / "chunk_1.1.html").read_text(encoding="utf-8")
        assert "chunk_1.2.html" in html

    def test_first_chunk_has_no_prev_link(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        output_dir = tmp_path / "html"

        renderer = ProtopageRenderer()
        renderer.compile(proto_dir, output_dir)

        html = (output_dir / "chunk_1.1.html").read_text(encoding="utf-8")
        assert "chunk_1.0.html" not in html

    def test_html_has_page_chrome(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        output_dir = tmp_path / "html"

        renderer = ProtopageRenderer()
        renderer.compile(proto_dir, output_dir)

        html = (output_dir / "chunk_1.1.html").read_text(encoding="utf-8")
        assert 'name="viewport"' in html
        assert 'class="site-header"' in html
        assert 'class="site-footer"' in html
        assert "Perseus Digital Library" in html

    def test_html_references_external_stylesheet(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        output_dir = tmp_path / "html"

        renderer = ProtopageRenderer()
        renderer.compile(proto_dir, output_dir)

        html = (output_dir / "chunk_1.1.html").read_text(encoding="utf-8")
        assert '<link rel="stylesheet"' in html
        assert "<style>" not in html

    def test_inline_place_rendered_with_class(self, tmp_path):
        proto_dir = tmp_path / "proto"
        proto_dir.mkdir()
        base_urn = "urn:cts:greekLit:tlg0003.tlg001.perseus-grc2"
        (proto_dir / "chunk_1.1.xml").write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<chunk cts-urn="{base_urn}:1.1">
  <meta><title>T</title><base-urn>{base_urn}</base-urn><language>grc</language></meta>
  <content>
    <section n="1" cts-urn="{base_urn}:1.1.1">
      <p>Near <place key="pleiades:123">Athens</place>.</p>
    </section>
  </content>
</chunk>""",
            encoding="utf-8",
        )
        (proto_dir / "index.json").write_text(
            json.dumps({"base_urn": base_urn, "title": "T", "language": "grc",
                        "chunks": [{"urn": f"{base_urn}:1.1", "file": "chunk_1.1.xml",
                                    "book": "1", "chapter": "1"}]}),
            encoding="utf-8",
        )
        output_dir = tmp_path / "html"
        renderer = ProtopageRenderer()
        renderer.compile(proto_dir, output_dir)

        html = (output_dir / "chunk_1.1.html").read_text(encoding="utf-8")
        assert 'class="place"' in html
        assert "Athens" in html


# ---------------------------------------------------------------------------
# Integration tests (require real Saxon + XSLT)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestProtopagePipelineIntegration:
    """Full two-step pipeline: TEI → proto-page XML → HTML.

    Requires Saxon via saxonche and the generate_protopages.xsl stylesheet.
    Run with:
        pdm run test -m slow
    """

    def test_thucydides_grc_produces_proto_pages(self, tmp_path):
        doc = TEIDocument.from_path(THUCYDIDES_GRC)
        proto_dir = tmp_path / "proto"
        compiler = ProtopageCompiler(xsl_file=_XSL_PATH)
        compiler.compile(doc, proto_dir)

        assert (proto_dir / "index.json").exists()
        index = json.loads((proto_dir / "index.json").read_text(encoding="utf-8"))
        assert len(index["chunks"]) == 917

    def test_thucydides_grc_proto_pages_render_to_html(self, tmp_path):
        doc = TEIDocument.from_path(THUCYDIDES_GRC)
        proto_dir = tmp_path / "proto"
        html_dir = tmp_path / "html"

        ProtopageCompiler(xsl_file=_XSL_PATH).compile(doc, proto_dir)
        ProtopageRenderer().compile(proto_dir, html_dir)

        html_files = list(html_dir.glob("chunk_*.html"))
        assert len(html_files) == 917

    def test_rendered_html_has_greek_text(self, tmp_path):
        doc = TEIDocument.from_path(THUCYDIDES_GRC)
        proto_dir = tmp_path / "proto"
        html_dir = tmp_path / "html"

        ProtopageCompiler(xsl_file=_XSL_PATH).compile(doc, proto_dir)
        ProtopageRenderer().compile(proto_dir, html_dir)

        html = (html_dir / "chunk_1.1.html").read_text(encoding="utf-8")
        assert "Θουκυδίδης" in html

    def test_rendered_html_has_navigation(self, tmp_path):
        doc = TEIDocument.from_path(THUCYDIDES_GRC)
        proto_dir = tmp_path / "proto"
        html_dir = tmp_path / "html"

        ProtopageCompiler(xsl_file=_XSL_PATH).compile(doc, proto_dir)
        ProtopageRenderer().compile(proto_dir, html_dir)

        html = (html_dir / "chunk_1.1.html").read_text(encoding="utf-8")
        assert "chunk_1.2.html" in html

    # -- Part 2: pubInfo and extended index.json --

    def test_proto_page_xml_has_pub_info(self, tmp_path):
        """XSLT emits <pubInfo> with non-empty <author> and <title>."""
        from lxml import etree

        doc = TEIDocument.from_path(THUCYDIDES_GRC)
        proto_dir = tmp_path / "proto"
        ProtopageCompiler(xsl_file=_XSL_PATH).compile(doc, proto_dir)

        root = etree.parse(proto_dir / "chunk_1.1.xml").getroot()
        pub_info = root.find("meta/pubInfo")
        assert pub_info is not None, "<pubInfo> missing from <meta>"
        assert pub_info.findtext("author", "").strip() != "", "<author> is empty"
        assert pub_info.findtext("title", "").strip() != "", "<title> is empty"

    def test_proto_page_xml_has_editor(self, tmp_path):
        """XSLT emits <editor> elements when source TEI has <editor> in <titleStmt>."""
        from lxml import etree

        doc = TEIDocument.from_path(THUCYDIDES_GRC)
        proto_dir = tmp_path / "proto"
        ProtopageCompiler(xsl_file=_XSL_PATH).compile(doc, proto_dir)

        root = etree.parse(proto_dir / "chunk_1.1.xml").getroot()
        pub_info = root.find("meta/pubInfo")
        assert pub_info is not None
        editors = pub_info.findall("editor")
        assert len(editors) >= 1, "No <editor> elements found"
        assert any(e.text and e.text.strip() for e in editors), "All <editor> elements are empty"

    def test_proto_page_xml_emits_empty_elements_for_absent_fields(self, tmp_path):
        """XSLT emits empty elements (not absent) for fields not in the source TEI."""
        from lxml import etree

        doc = TEIDocument.from_path(THUCYDIDES_GRC)
        proto_dir = tmp_path / "proto"
        ProtopageCompiler(xsl_file=_XSL_PATH).compile(doc, proto_dir)

        root = etree.parse(proto_dir / "chunk_1.1.xml").getroot()
        pub_info = root.find("meta/pubInfo")
        assert pub_info is not None
        # All scalar fields must be present as elements, even if empty.
        for tag in ("title", "author", "pubPlace", "pubDate"):
            el = pub_info.find(tag)
            assert el is not None, f"<{tag}> missing from <pubInfo>"

    def test_index_json_has_author_and_subtypes(self, tmp_path):
        """index.json contains author, book_subtype, and chapter_subtype."""
        doc = TEIDocument.from_path(THUCYDIDES_GRC)
        proto_dir = tmp_path / "proto"
        ProtopageCompiler(xsl_file=_XSL_PATH).compile(doc, proto_dir)

        index = json.loads((proto_dir / "index.json").read_text(encoding="utf-8"))
        assert "author" in index, "author missing from index.json"
        assert "book_subtype" in index, "book_subtype missing from index.json"
        assert "chapter_subtype" in index, "chapter_subtype missing from index.json"
        assert index["author"].strip() != "", "author is empty"
        assert index["book_subtype"] == "book"
        assert index["chapter_subtype"] == "chapter"


# ---------------------------------------------------------------------------
# ProtopageRenderer — pub_info and toc context (unit tests, no Saxon)
# ---------------------------------------------------------------------------

class TestProtopageRendererContext:
    """Unit tests for the enriched template context (pub_info, toc)."""

    def test_pub_info_populated_from_meta(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        html_dir = tmp_path / "html"

        captured: list[dict] = []
        original_render = None

        def capturing_render(**ctx):
            captured.append(ctx)
            return original_render(**ctx)

        renderer = ProtopageRenderer()
        env_orig = renderer.compile.__func__  # just verify via rendered output
        renderer.compile(proto_dir, html_dir)

        # Verify via _parse_chunk directly
        from mvp.site.compilers.protopage_compiler import _parse_chunk
        _, pub_info = _parse_chunk(proto_dir / "chunk_1.1.xml")
        assert pub_info["author"] == "Thucydides"
        assert pub_info["title"] == "Ἱστορίαι"
        assert "Henry Stuart Jones" in pub_info["editors"]
        assert pub_info["pub_place"] == "Medford, MA"
        assert pub_info["pub_date"] == "1992"

    def test_toc_passed_when_toc_json_present(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)

        # Write a minimal toc.json
        toc_data = {"version": "1", "document": {}, "toc": [{"depth": 0, "label": "Book 1"}]}
        (proto_dir / "toc.json").write_text(
            json.dumps(toc_data), encoding="utf-8"
        )

        html_dir = tmp_path / "html"
        renderer = ProtopageRenderer()

        # Patch template.render to capture context
        with patch("mvp.site.compilers.protopage_compiler.Environment") as mock_env_cls:
            mock_template = MagicMock()
            mock_template.render.return_value = "<html/>"
            mock_env = MagicMock()
            mock_env.get_template.return_value = mock_template
            mock_env_cls.return_value = mock_env

            renderer.compile(proto_dir, html_dir)

        calls = mock_template.render.call_args_list
        assert len(calls) == 2
        for call in calls:
            assert "toc" in call.kwargs
            assert call.kwargs["toc"] == toc_data

    def test_toc_none_when_toc_json_absent(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        # No toc.json written

        html_dir = tmp_path / "html"
        renderer = ProtopageRenderer()

        with patch("mvp.site.compilers.protopage_compiler.Environment") as mock_env_cls:
            mock_template = MagicMock()
            mock_template.render.return_value = "<html/>"
            mock_env = MagicMock()
            mock_env.get_template.return_value = mock_template
            mock_env_cls.return_value = mock_env

            renderer.compile(proto_dir, html_dir)

        calls = mock_template.render.call_args_list
        assert len(calls) == 2
        for call in calls:
            assert call.kwargs.get("toc") is None

    def test_toc_none_logs_warning(self, tmp_path):
        import logging

        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        html_dir = tmp_path / "html"

        with patch("mvp.site.compilers.protopage_compiler.Environment") as mock_env_cls:
            mock_template = MagicMock()
            mock_template.render.return_value = "<html/>"
            mock_env = MagicMock()
            mock_env.get_template.return_value = mock_template
            mock_env_cls.return_value = mock_env

            with patch("mvp.site.compilers.protopage_compiler._log") as mock_log:
                renderer = ProtopageRenderer()
                renderer.compile(proto_dir, html_dir)
                mock_log.warning.assert_called_once()

    def test_pub_info_passed_to_template(self, tmp_path):
        proto_dir = tmp_path / "proto"
        _write_protopage_fixture(proto_dir)
        html_dir = tmp_path / "html"

        with patch("mvp.site.compilers.protopage_compiler.Environment") as mock_env_cls:
            mock_template = MagicMock()
            mock_template.render.return_value = "<html/>"
            mock_env = MagicMock()
            mock_env.get_template.return_value = mock_template
            mock_env_cls.return_value = mock_env

            renderer = ProtopageRenderer()
            renderer.compile(proto_dir, html_dir)

        for call in mock_template.render.call_args_list:
            assert "pub_info" in call.kwargs
            assert call.kwargs["pub_info"]["author"] == "Thucydides"
