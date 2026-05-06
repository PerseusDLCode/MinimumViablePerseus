# mvp/compilers.py
#
# PageCompiler and CatalogCompiler.
#
# Compilers follow the command pattern: compile() returns None on
# success and raises CompilationError on failure.  All output is
# written to paths obtained from SiteMap.  Compilers are agents that
# produce artifacts; they are not functions that return values.

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from saxonche import PySaxonProcessor

from mvp.document import TEIDocument
from mvp.models import TEIMetadata
from mvp.site_map import SiteMap
from mvp.strategy import ChunkingStrategy

# Human-readable names for BCP 47 / ISO 639-3 language codes.
_LANGUAGE_NAMES: dict[str, str] = {
    "lat": "Latin",
    "grc": "Greek",
    "eng": "English",
    "ara": "Arabic",
    "per": "Persian",
    "deu": "German",
    "fra": "French",
    "ita": "Italian",
    "spa": "Spanish",
    "rus": "Russian",
}

_SHARED_CSS = """
.site-header { border-bottom: 1px solid #ccc; margin-bottom: 1.5em;
               padding-bottom: .5em; font-size: .9em; color: #555 }
.site-header a { text-decoration: none; font-weight: bold; color: inherit }
.site-footer { border-top: 1px solid #eee; margin-top: 2em; padding-top: .5em;
               font-size: .8em; color: #888; text-align: center }
"""

_CATALOG_CSS = _SHARED_CSS + """
body         { font-family: serif; max-width: 60em; margin: 0 auto; padding: 1em 2em }
h1           { margin-bottom: 0.25em }
.summary     { color: #555; margin-bottom: 1.5em }
.author-group { margin: 1.5em 0 }
.author-name { font-size: 1.05em; font-weight: bold;
               border-bottom: 1px solid #ccc; padding-bottom: .2em }
.work-entry  { margin: .35em 0 .35em 1.5em }
.work-entry a { text-decoration: none }
.work-entry a:hover { text-decoration: underline }
"""

_INDEX_CSS = _SHARED_CSS + """
body  { font-family: serif; max-width: 40em; margin: 0 auto; padding: 2em }
h1    { margin-bottom: 0.25em }
.tagline { color: #555; margin-bottom: 1.5em }
ul    { list-style: none; padding: 0 }
li    { margin: .5em 0; font-size: 1.1em }
"""


@dataclass
class CompilationError(Exception):
    """Raised when a compiler fails to produce its artifact.

    Carries enough context for the BuildPipeline to log clearly
    and decide whether to continue or abort.
    """
    document: TEIDocument
    message: str
    cause: Exception | None = None

    def __str__(self) -> str:
        base = f"Compilation failed for {self.document.path}: {self.message}"
        if self.cause:
            base += f" (caused by: {self.cause})"
        return base


class PageCompiler:
    """Compiles a TEIDocument into a sequence of HTML chunk pages.

    Delegates document segmentation to a ChunkingStrategy and HTML
    generation to an XSLT 3.0 stylesheet via Saxon.

    Args:
        strategy:   ChunkingStrategy determining how the document is
                    divided into chunks.
        xslt_root:  Directory containing XSLT stylesheets.

    Usage::

        compiler = PageCompiler(strategy, xslt_root=Path("src/xslt"))
        compiler.compile(doc, output_path=site_map.chunk_dir(doc.metadata.urn))
    """

    def __init__(self, strategy: ChunkingStrategy,
                 xslt_root: Path,
                 morph_url: str = "") -> None:
        self._strategy = strategy
        self._xslt_root = Path(xslt_root)
        self._morph_url = morph_url

    def compile(self, doc: TEIDocument, output_path: Path,
                catalog_url: str | None = None) -> None:
        """Compile doc into HTML chunk pages written to output_path.

        Args:
            doc:          The TEI source document to compile.
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
        output_path.mkdir(parents=True, exist_ok=True)
        stylesheet = self._xslt_root / self._strategy.xslt_stylesheet

        if catalog_url is None:
            lang = doc.metadata.language
            catalog_url = f"/catalog/{lang}.html" if lang else "/index.html"

        try:
            with PySaxonProcessor(license=False) as proc:
                xslt = proc.new_xslt30_processor()
                transformer = xslt.compile_stylesheet(
                    stylesheet_file=str(stylesheet)
                )
                transformer.set_parameter(
                    "chunk-unit",
                    proc.make_string_value(self._strategy.chunk_unit)
                )
                transformer.set_parameter(
                    "output-dir",
                    proc.make_string_value(str(output_path))
                )
                transformer.set_parameter(
                    "catalog-url",
                    proc.make_string_value(catalog_url)
                )
                if self._morph_url:
                    transformer.set_parameter(
                        "morph-url",
                        proc.make_string_value(self._morph_url)
                    )
                transformer.set_base_output_uri(output_path.as_uri() + "/")
                transformer.transform_to_string(source_file=str(doc.path))

            # Enrich the XSLT-written index.json with author and language so
            # the catalog can be rebuilt from manifests alone (no source TEI).
            manifest = output_path / "index.json"
            if manifest.exists():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                data["author"]   = doc.metadata.author
                data["language"] = doc.metadata.language
                manifest.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
        except Exception as exc:
            raise CompilationError(
                document=doc,
                message="XSLT transformation failed",
                cause=exc,
            ) from exc


class CatalogCompiler:
    """Compiles TEIMetadata records into catalog HTML pages.

    Produces one catalog page per language grouping, listing all
    documents in that language with links to their first chunk pages.
    Also produces a root index.html linking to each language catalog.

    No external template engine: HTML is rendered with Python f-strings.

    Args:
        site_map: The SiteMap used during compilation; needed to locate
                  index.json manifests and construct chunk URLs.
    """

    def __init__(self, site_map: SiteMap) -> None:
        self._site_map = site_map

    def compile(self, entries: list[TEIMetadata],
                output_path: Path) -> None:
        """Compile a per-language catalog page and write it to output_path.

        Args:
            entries:     Metadata records for all documents in one language.
            output_path: Path of the catalog HTML file to write.

        The catalog page is always written, even if some entries have no
        compiled chunks (those entries appear as plain text without a link).
        """
        if not entries:
            return

        language = entries[0].language
        lang_name = _LANGUAGE_NAMES.get(language, language.upper() if language else "Unknown")

        # Sort by author then title.
        sorted_entries = sorted(entries, key=lambda e: (e.author.lower(), e.title.lower()))

        # Group by author.
        authors: dict[str, list[TEIMetadata]] = {}
        for entry in sorted_entries:
            author = entry.author or "Anonymous"
            authors.setdefault(author, []).append(entry)

        # Build the author/work HTML rows.
        rows: list[str] = []
        for author, works in authors.items():
            rows.append(f'    <div class="author-group">')
            rows.append(f'      <div class="author-name">{_escape(author)}</div>')
            for work in works:
                url = self._first_chunk_url(work.urn, output_path.parent)
                if url:
                    rows.append(
                        f'      <div class="work-entry">'
                        f'<a href="{url}">{_escape(work.title)}</a>'
                        f'</div>'
                    )
                else:
                    rows.append(
                        f'      <div class="work-entry">{_escape(work.title)}</div>'
                    )
            rows.append(f'    </div>')

        body = "\n".join(rows)
        count = len(entries)
        noun = "work" if count == 1 else "works"

        index_url = os.path.relpath(
            self._site_map.root / "index.html", output_path.parent
        ).replace("\\", "/")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Perseus — {lang_name} Texts</title>
  <style>{_CATALOG_CSS}</style>
</head>
<body>
  <header class="site-header">
    <a href="{index_url}">Perseus Digital Library</a>
    <span> · All Languages</span>
  </header>
  <main>
    <h1>{lang_name} Texts</h1>
    <p class="summary">{count} {noun}</p>
{body}
  </main>
  <footer class="site-footer">Perseus Digital Library</footer>
</body>
</html>
"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")

    def compile_index(self, languages: dict[str, list[TEIMetadata]],
                      output_path: Path) -> None:
        """Compile the root index.html linking to each language catalog.

        Args:
            languages:   Mapping of language code to list of TEIMetadata.
            output_path: Path of the index HTML file to write.
        """
        items: list[str] = []
        for lang, entries in sorted(languages.items()):
            lang_name = _LANGUAGE_NAMES.get(lang, lang.upper() if lang else "Unknown")
            count = len(entries)
            noun = "work" if count == 1 else "works"
            catalog_url = os.path.relpath(
                self._site_map.catalog_path(lang), output_path.parent
            ).replace("\\", "/")
            items.append(
                f'  <li>'
                f'<a href="{catalog_url}">{_escape(lang_name)}</a>'
                f' <span class="count">({count} {noun})</span>'
                f'</li>'
            )

        items_html = "\n".join(items)
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Perseus Digital Library</title>
  <style>{_INDEX_CSS}
.count {{ color: #888; font-size: .9em }}
</style>
</head>
<body>
  <header class="site-header">
    <span class="site-name">Perseus Digital Library</span>
  </header>
  <main>
    <h1>Perseus Digital Library</h1>
    <p class="tagline">Texts from ancient Greece and Rome.</p>
    <ul>
{items_html}
    </ul>
  </main>
  <footer class="site-footer">Perseus Digital Library</footer>
</body>
</html>
"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")

    # ------------------------------------------------------------------
    # Private

    def _first_chunk_url(self, urn: str, from_dir: Path) -> str | None:
        """Return a relative URL to the first chunk of urn, relative to from_dir.

        Args:
            urn:      CTS URN of the work to link to.
            from_dir: Directory of the page that will contain the link
                      (e.g. the catalog file's parent directory).
        Returns:
            A relative URL string suitable for an href attribute, or None
            if no compiled manifest exists for the given URN.
        """
        manifest_path = self._site_map.manifest_path(urn)
        if not manifest_path.exists():
            return None
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            chunks = data.get("chunks", [])
            if not chunks:
                return None
            first_file = chunks[0].get("file", "")
            if not first_file:
                return None
            chunk_abs = manifest_path.parent / first_file
            return os.path.relpath(chunk_abs, from_dir).replace("\\", "/")
        except (json.JSONDecodeError, KeyError, ValueError):
            return None


def _escape(text: str) -> str:
    """Minimal HTML escaping for text content."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))
