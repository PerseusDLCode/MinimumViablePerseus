from __future__ import annotations

import json
from pathlib import Path

from saxonche import PySaxonProcessor

from mvp.site.compilers.base import Compiler, CompilationError
from mvp.corpus.document import TEIDocument
from mvp.site.strategy import ChunkingStrategy


class XSLTCompiler:
    """Generic XSLT 3.0 compiler via SaxonC.

    Wraps the PySaxonProcessor lifecycle. Callers supply source,
    stylesheet, output directory, and an arbitrary parameter dict.
    """

    def __init__(self, xsl_file: Path) -> None:
        self._xsl_file = Path(xsl_file)

    def compile(
        self,
        source: Path,
        output_dir: Path,
        params: dict[str, str] | None = None,
    ) -> None:
        """Transform source via the stylesheet, writing results to output_dir.

        Raises:
            RuntimeError: if Saxon reports an error.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        with PySaxonProcessor(license=False) as proc:
            xslt = proc.new_xslt30_processor()
            transformer = xslt.compile_stylesheet(
                stylesheet_file=str(self._xsl_file.resolve())
            )
            for name, value in (params or {}).items():
                transformer.set_parameter(name, proc.make_string_value(value))
            transformer.set_base_output_uri(output_dir.resolve().as_uri() + "/")
            transformer.transform_to_string(source_file=str(source.resolve()))
            if xslt.error_message:
                raise RuntimeError(xslt.error_message)


class PageCompiler(Compiler[TEIDocument]):
    """Compiles a TEIDocument into a sequence of HTML chunk pages.

    Delegates document segmentation to a ChunkingStrategy and HTML
    generation to an XSLT 3.0 stylesheet via Saxon.

    Args:
        strategy:  ChunkingStrategy determining how the document is
                   divided into chunks.
        driver:    Full path to the XSLT driver stylesheet (e.g.
                   Path("src/xslt/html/driver.xsl")).

    Usage::

        compiler = PageCompiler(strategy, driver=Path("src/xslt/html/driver.xsl"))
        compiler.compile(doc, output_path=site_map.chunk_dir(doc.metadata.urn))
    """

    def __init__(self, strategy: ChunkingStrategy,
                 driver: Path,
                 morph_url: str = "") -> None:
        self._strategy = strategy
        self._xslt = XSLTCompiler(driver)
        self._morph_url = morph_url

    def compile(self, source: TEIDocument, output_path: Path,
                catalog_url: str | None = None, **kwargs) -> None:
        """Compile source into HTML chunk pages written to output_path.

        Args:
            source:       The TEI source document to compile.
            output_path:  Directory into which chunk HTML files and
                          index.json are written.  Created if absent.
            catalog_url:  URL for the "← Catalog" nav link rendered on
                          every chunk page.  If omitted, a root-relative
                          fallback is constructed from the document's
                          language code.

        Raises:
            CompilationError: If the XSLT transformation fails for
                              any reason.
        """
        if catalog_url is None:
            lang = source.metadata.language
            catalog_url = f"/catalog/{lang}.html" if lang else "/index.html"

        params: dict[str, str] = {
            "chunk-unit":     self._strategy.chunk_unit,
            "chunk-strategy": self._strategy.chunk_strategy,
            "output-dir":     str(output_path),
            "catalog-url":    catalog_url,
        }
        if self._morph_url:
            params["morph-url"] = self._morph_url

        try:
            self._xslt.compile(source.path, output_path, params)
        except Exception as exc:
            raise CompilationError(
                document=source,
                message="XSLT transformation failed",
                cause=exc,
            ) from exc

        # Enrich the XSLT-written index.json with author and language so
        # the catalog can be rebuilt from manifests alone (no source TEI).
        manifest = output_path / "index.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["author"]   = source.metadata.author
            data["language"] = source.metadata.language
            manifest.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
