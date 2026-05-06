# mvp/pipeline.py
#
# BuildPipeline: orchestrates the full Milestone 1 build.
#
# Iterates over the corpus, compiles chunk pages, collects metadata,
# and compiles the catalog.  Owns the error-handling policy.

from __future__ import annotations

import os
from pathlib import Path

from mvp.compilers import CatalogCompiler, CompilationError, PageCompiler
from mvp.corpus import Corpus
from mvp.models import TEIMetadata
from mvp.site_map import SiteMap
from mvp.strategy import StrategySelector


class BuildPipeline:
    """Orchestrates the Perseus6 Milestone 1 static site build.

    Stages:
        1. Iterate over corpus documents.
        2. Select a chunking strategy for each document.
        3. Compile each document into HTML chunk pages.
        4. Collect TEIMetadata from successfully compiled documents.
        5. Compile per-language catalog pages from the collected metadata.
        6. Compile the root index.html linking to each language catalog.

    Error policy: collect-all-errors.  All documents are attempted;
    failures are collected and reported at the end.  This is preferred
    over fail-fast for batch builds over large corpora.

    Args:
        corpus:    The TEI source corpus.
        site_map:  URL/path scheme for compiled artifacts.
        xslt_root: Directory containing XSLT stylesheets.
    """

    def __init__(self, corpora: list[Corpus], site_map: SiteMap,
                 xslt_root: Path,
                 morph_url: str = "") -> None:
        self._corpora = corpora
        self._site_map = site_map
        self._xslt_root = xslt_root
        self._morph_url = morph_url
        self._selector = StrategySelector()

    def run(self) -> None:
        """Run the full build.  Prints a summary on completion.

        Raises:
            SystemExit: If any documents failed to compile (after
                        all documents have been attempted).
        """
        metadata: list[TEIMetadata] = []
        errors: list[CompilationError] = []

        for corpus in self._corpora:
            for doc in corpus.documents():
                if not doc.metadata.urn:
                    print(f"  SKIPPED:  {doc.path}: empty URN")
                    continue
                try:
                    strategy = self._selector.select(doc)
                    compiler = PageCompiler(
                        strategy=strategy,
                        xslt_root=self._xslt_root,
                        morph_url=self._morph_url,
                    )
                    output_path = self._site_map.chunk_dir(doc.metadata.urn)
                    catalog_path = self._site_map.catalog_path(doc.metadata.language)
                    catalog_url = os.path.relpath(
                        catalog_path, output_path
                    ).replace("\\", "/")
                    compiler.compile(doc, output_path, catalog_url=catalog_url)
                    metadata.append(doc.metadata)
                    print(f"  compiled: {doc.metadata.urn}")
                except CompilationError as exc:
                    errors.append(exc)
                    print(f"  FAILED:   {exc}")
                except ValueError as exc:
                    # StrategySelector found no matching strategy
                    print(f"  SKIPPED:  {doc.path}: {exc}")

        print(f"\nCompiled {len(metadata)} documents, "
              f"{len(errors)} failures.")

        if metadata:
            catalog_compiler = CatalogCompiler(site_map=self._site_map)
            # Group metadata by language for per-language catalog pages
            languages: dict[str, list[TEIMetadata]] = {}
            for entry in metadata:
                languages.setdefault(entry.language, []).append(entry)

            for language, entries in languages.items():
                output_path = self._site_map.catalog_path(language)
                catalog_compiler.compile(entries, output_path)

            catalog_compiler.compile_index(
                languages,
                self._site_map.root / "index.html",
            )

        if errors:
            raise SystemExit(
                f"Build completed with {len(errors)} error(s). "
                "See output above for details."
            )
