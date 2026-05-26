from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from mvp.site.compilers.base import Compiler
from mvp.corpus.document import LANGUAGE_NAMES
from mvp.corpus.models import TEIMetadata
from mvp.site.site_map import SiteMap

_CATALOG_CSS_URL = "/css/catalog.css"


def copy_static_assets(src_static_dir: Path, output_root: Path) -> None:
    """Copy src_static_dir/css/ to output_root/css/.

    Called at the start of a build so catalog pages can reference
    /css/catalog.css via a root-relative URL.  Safe to call multiple
    times; dirs_exist_ok=True means existing files are overwritten.
    Does nothing if src_static_dir/css/ does not exist.
    """
    src_css = Path(src_static_dir) / "css"
    if not src_css.exists():
        return
    shutil.copytree(src_css, Path(output_root) / "css", dirs_exist_ok=True)


def _render_page(
    title: str,
    css_url: str,
    header_html: str,
    main_html: str,
    body_class: str = "",
) -> str:
    """Render the shared HTML page shell used by all catalog pages."""
    body_tag = f'<body class="{body_class}">' if body_class else "<body>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <link rel="stylesheet" href="{css_url}"/>
</head>
{body_tag}
  <header class="site-header">
    {header_html}
  </header>
  <main>
{main_html}
  </main>
  <footer class="site-footer">Perseus Digital Library</footer>
</body>
</html>
"""


def _escape(text: str) -> str:
    """Minimal HTML escaping for text content."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


class CatalogCompiler(Compiler[list[TEIMetadata]]):
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

    def compile(self, source: list[TEIMetadata], output_path: Path,
                **kwargs) -> None:
        """Compile a per-language catalog page and write it to output_path.

        Args:
            source:      Metadata records for all documents in one language.
            output_path: Path of the catalog HTML file to write.

        The catalog page is always written, even if some entries have no
        compiled chunks (those entries appear as plain text without a link).
        """
        if not source:
            return

        language = source[0].language
        lang_name = LANGUAGE_NAMES.get(language, language.upper() if language else "Unknown")

        sorted_entries = sorted(source, key=lambda e: (e.author.lower(), e.title.lower()))

        authors: dict[str, list[TEIMetadata]] = {}
        for entry in sorted_entries:
            author = entry.author or "Anonymous"
            authors.setdefault(author, []).append(entry)

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
        count = len(source)
        noun = "work" if count == 1 else "works"

        index_url = os.path.relpath(
            self._site_map.root / "index.html", output_path.parent
        ).replace("\\", "/")

        header_html = (
            f'<a href="{index_url}">Perseus Digital Library</a>\n'
            f'    <span> · All Languages</span>'
        )
        main_html = (
            f'    <h1>{lang_name} Texts</h1>\n'
            f'    <p class="summary">{count} {noun}</p>\n'
            f'{body}'
        )
        html = _render_page(
            title=f"Perseus — {lang_name} Texts",
            css_url=_CATALOG_CSS_URL,
            header_html=header_html,
            main_html=main_html,
            body_class="catalog",
        )
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
            lang_name = LANGUAGE_NAMES.get(lang, lang.upper() if lang else "Unknown")
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
        main_html = (
            '    <h1>Perseus Digital Library</h1>\n'
            '    <p class="tagline">Texts from ancient Greece and Rome.</p>\n'
            f'    <ul>\n{items_html}\n    </ul>'
        )
        html = _render_page(
            title="Perseus Digital Library",
            css_url=_CATALOG_CSS_URL,
            header_html='<span class="site-name">Perseus Digital Library</span>',
            main_html=main_html,
            body_class="index",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")

    def _first_chunk_url(self, urn: str, from_dir: Path) -> str | None:
        """Return a relative URL to the first chunk of urn, relative to from_dir."""
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
