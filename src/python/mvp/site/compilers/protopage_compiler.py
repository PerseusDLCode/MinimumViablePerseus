""" Proto-page compiler for TEI texts.




"""

"""Proto-page compiler and renderer for Family-1 (hierarchical-div) TEI texts.

Two compilers forming the two-step pipeline:

  ProtopageCompiler   (Compiler[TEIDocument])
      Step 1: TEI → proto-page XML.
      Runs generate_protopages.xsl via Saxon (delegating to XSLTCompiler)
      to produce one proto-page XML file per chapter plus an index.json.

  ProtopageRenderer   (Compiler[Path])
      Step 2: proto-page XML → HTML.
      Reads the proto-page directory produced by ProtopageCompiler and
      renders each XML file to an HTML reading page via Jinja2.

Proto-page XML vocabulary (no namespace):

    <chunk cts-urn="…" [prev-urn="…"] [next-urn="…"]>
      <meta>
        <title>…</title>
        <base-urn>…</base-urn>
        <language>…</language>
        <ctsurn>…</ctsurn>
        <sourceURL>…</sourceURL>
        <pubInfo>
          <title>…</title>
          <author>…</author>
          <editor>…</editor>   <!-- one per editor; empty element if none -->
          <pubPlace>…</pubPlace>
          <pubDate>…</pubDate>
        </pubInfo>
      </meta>
      <content>
        <section n="…" cts-urn="…">
          <p> … <place key="…"> … <person key="…"> … <q> … <del> … <add> … <gap/> … </p>
        </section>
      </content>
    </chunk>

Template context supplied by ProtopageRenderer:

    chunk    — Chunk dataclass (current chunk)
    pub_info — dict extracted from <meta>/<pubInfo>
    toc      — full toc.json dict, or None if toc.json absent
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from lxml import etree
from markupsafe import Markup, escape

from mvp.corpus.document import TEIDocument
from mvp.site.compilers.base import Compiler, CompilationError
from mvp.site.compilers.page_compiler import XSLTCompiler


_BUILTIN_TEMPLATES = Path(__file__).parent.parent / "templates"
_log = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Section:
    n: str
    cts_urn: str
    paragraphs: list[Markup]


@dataclass
class Chunk:
    cts_urn: str
    prev_urn: str | None
    next_urn: str | None
    title: str
    base_urn: str
    language: str
    sections: list[Section]

    @staticmethod
    def _file_for(urn: str) -> str:
        passage = urn.rsplit(":", 1)[-1]
        return f"chunk_{passage}.html"

    @property
    def html_file(self) -> str:
        return self._file_for(self.cts_urn)

    @property
    def prev_file(self) -> str | None:
        return self._file_for(self.prev_urn) if self.prev_urn else None

    @property
    def next_file(self) -> str | None:
        return self._file_for(self.next_urn) if self.next_urn else None


# ── XML parsing ───────────────────────────────────────────────────────────────

def _inline_to_html(el: etree._Element) -> str:
    """Recursively serialize proto-page inline elements to HTML strings.

    Text nodes are escaped; known elements are mapped to HTML equivalents;
    unknown elements fall through so no text content is silently lost.
    """
    parts: list[str] = []
    if el.text:
        parts.append(str(escape(el.text)))

    for child in el:
        tag = etree.QName(child.tag).localname
        inner = _inline_to_html(child)

        if tag == "place":
            key = str(escape(child.get("key", "")))
            parts.append(f'<span class="place" data-key="{key}">{inner}</span>')
        elif tag == "person":
            key = str(escape(child.get("key", "")))
            parts.append(f'<span class="person" data-key="{key}">{inner}</span>')
        elif tag == "q":
            parts.append(f"<q>{inner}</q>")
        elif tag == "del":
            parts.append(f'<span class="tei-del">{inner}</span>')
        elif tag == "add":
            parts.append(f'<span class="tei-add">{inner}</span>')
        elif tag == "gap":
            parts.append('<span class="gap">…</span>')
        else:
            parts.append(inner)

        if child.tail:
            parts.append(str(escape(child.tail)))

    return "".join(parts)


def _parse_pub_info(meta: etree._Element | None) -> dict[str, Any]:
    """Extract <pubInfo> from a proto-page <meta> element.

    Returns a dict with keys: title, author, editors (list), pub_place, pub_date.
    All values default to empty strings / empty list when the element is absent.
    """
    if meta is None:
        return {"title": "", "author": "", "editors": [], "pub_place": "", "pub_date": ""}
    pub = meta.find("pubInfo")
    if pub is None:
        return {"title": "", "author": "", "editors": [], "pub_place": "", "pub_date": ""}
    return {
        "title":     pub.findtext("title", ""),
        "author":    pub.findtext("author", ""),
        "editors":   [el.text or "" for el in pub.findall("editor")],
        "pub_place": pub.findtext("pubPlace", ""),
        "pub_date":  pub.findtext("pubDate", ""),
    }


def _parse_chunk(path: Path) -> tuple[Chunk, dict[str, Any]]:
    """Parse a proto-page XML file into a (Chunk, pub_info) tuple."""
    root = etree.parse(path).getroot()
    meta = root.find("meta")
    sections = [
        Section(
            n=sec.get("n", ""),
            cts_urn=sec.get("cts-urn", ""),
            paragraphs=[Markup(f"<p>{_inline_to_html(p)}</p>") for p in sec.findall("p")],
        )
        for sec in root.findall(".//section")
    ]
    chunk = Chunk(
        cts_urn=root.get("cts-urn", ""),
        prev_urn=root.get("prev-urn"),
        next_urn=root.get("next-urn"),
        title=meta.findtext("title", "") if meta is not None else "",
        base_urn=meta.findtext("base-urn", "") if meta is not None else "",
        language=meta.findtext("language", "") if meta is not None else "",
        sections=sections,
    )
    return chunk, _parse_pub_info(meta)


# ── ProtopageCompiler ─────────────────────────────────────────────────────────

class ProtopageCompiler(Compiler[TEIDocument]):
    """Step 1 of the two-step pipeline: TEI → proto-page XML.

    Delegates to XSLTCompiler with generate_protopages.xsl.  Produces one
    proto-page XML file per chapter plus an index.json manifest.

    Args:
        xsl_file: Path to generate_protopages.xsl
                  (typically src/xslt/html/generate_protopages.xsl).
    """

    def __init__(self, xsl_file: Path) -> None:
        self._xslt = XSLTCompiler(xsl_file)

    def compile(self, source: TEIDocument, output_path: Path, **kwargs) -> None:
        """Transform source TEI into proto-page XML files written to output_path.

        Args:
            source:      TEI source document (Family-1: book/chapter/section).
            output_path: Directory for proto-page XML files and index.json.

        Raises:
            CompilationError: if the XSLT transformation fails.
        """
        try:
            self._xslt.compile(
                source.path,
                output_path,
                params={"output-dir": str(output_path.resolve())},
            )
        except Exception as exc:
            raise CompilationError(
                document=source,
                message="Proto-page XSLT transformation failed",
                cause=exc,
            ) from exc


# ── ProtopageRenderer ─────────────────────────────────────────────────────────

class ProtopageRenderer(Compiler[Path]):
    """Step 2 of the two-step pipeline: proto-page XML → HTML.

    Reads the proto-page directory produced by ProtopageCompiler and renders
    each XML file to an HTML reading page via Jinja2.  index.json drives
    discovery and ordering; the directory is not scanned directly.

    Template context per chunk:
        chunk    — Chunk dataclass
        pub_info — dict from <meta>/<pubInfo> (title, author, editors, pub_place, pub_date)
        toc      — full toc.json dict, or None if toc.json is absent

    Args:
        template_dir:  Jinja2 template directory.  Defaults to the built-in
                       templates bundled with this package.
        template_name: Filename of the Jinja2 template within template_dir.
                       Defaults to ``chunk.html``.
    """

    def __init__(
        self,
        template_dir: Path = _BUILTIN_TEMPLATES,
        template_name: str = "chunk.html",
    ) -> None:
        self._template_dir = Path(template_dir)
        self._template_name = template_name

    def compile(self, source: Path, output_path: Path, **kwargs) -> None:
        """Render proto-page XML from source directory to HTML in output_path.

        Args:
            source:      Directory containing proto-page XML files + index.json.
            output_path: Directory to write HTML files to.

        Raises:
            RuntimeError: if rendering fails.
        """
        env = Environment(
            loader=FileSystemLoader(str(self._template_dir)),
            autoescape=True,
        )
        template = env.get_template(self._template_name)
        index = json.loads((source / "index.json").read_text(encoding="utf-8"))
        output_path.mkdir(parents=True, exist_ok=True)

        # Load toc.json if present; warn and continue if absent.
        toc_path = source / "toc.json"
        if toc_path.exists():
            toc_data: dict[str, Any] | None = json.loads(
                toc_path.read_text(encoding="utf-8")
            )
        else:
            toc_data = None
            _log.warning("toc.json not found in %s; toc context will be None", source)

        for entry in index["chunks"]:
            chunk, pub_info = _parse_chunk(source / entry["file"])
            out_path = output_path / chunk.html_file
            out_path.write_text(
                template.render(chunk=chunk, pub_info=pub_info, toc=toc_data),
                encoding="utf-8",
            )
