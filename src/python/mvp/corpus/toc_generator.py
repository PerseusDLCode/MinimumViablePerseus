from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TOCGenerator:
    """Generates a per-document TOC index from a proto-page output directory.

    Reads ``index.json`` (produced by ProtopageCompiler / generate_protopages.xsl)
    and writes ``toc.json`` alongside it.  ``toc.json`` is a dataset artifact —
    it belongs to the corpus layer and is consumed by the View layer at render
    time rather than embedded in every chunk file.

    ``index.json`` format assumed:
        {
          "base_urn": "...",
          "title": "...",
          "language": "...",
          "author": "...",          # added by generate_protopages.xsl Part 2
          "book_subtype": "book",   # added by generate_protopages.xsl Part 2
          "chapter_subtype": "chapter",
          "chunks": [
            {"urn": "...", "file": "...", "book": "1", "chapter": "1"},
            ...
          ]
        }

    When ``book_subtype`` is absent from ``index.json`` and all chunks share a
    single book value, a flat (single-level) TOC is produced instead of the
    default nested book/chapter structure.
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = Path(output_dir)

    def generate(self) -> dict[str, Any]:
        """Return the TOC as a dict ready for JSON serialisation."""
        index = json.loads(
            (self._output_dir / "index.json").read_text(encoding="utf-8")
        )
        base_urn = index["base_urn"]
        title = index.get("title", "")
        author = index.get("author", "")
        book_subtype = index.get("book_subtype", "book")
        chapter_subtype = index.get("chapter_subtype", "chapter")
        chunks = index.get("chunks", [])

        # Detect single-level mode: no book_subtype declared AND only one
        # distinct book value across all chunks.
        has_book_subtype = "book_subtype" in index
        book_values = {ch.get("book", "") for ch in chunks}
        single_level = not has_book_subtype and len(book_values) <= 1

        if single_level:
            toc = self._build_flat_toc(chunks, chapter_subtype, base_urn)
        else:
            toc = self._build_nested_toc(chunks, book_subtype, chapter_subtype, base_urn)

        return {
            "version": "1",
            "document": {
                "base_urn": base_urn,
                "title": title,
                "author": author,
            },
            "toc": toc,
        }

    def write(self, output_path: Path | None = None) -> None:
        """Write ``toc.json`` to output_path (defaults to the output directory)."""
        if output_path is None:
            output_path = self._output_dir / "toc.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(self.generate(), f, ensure_ascii=False, indent=2)

    # ── private helpers ──────────────────────────────────────────────────────

    def _build_flat_toc(
        self,
        chunks: list[dict],
        chapter_subtype: str,
        base_urn: str,
    ) -> list[dict[str, Any]]:
        """Flat depth-0 chapter entries for single-level documents."""
        entries = []
        for idx, ch in enumerate(chunks, 1):
            n = ch.get("chapter", str(idx))
            entries.append({
                "depth": 0,
                "index": idx,
                "label": f"{chapter_subtype.capitalize()} {n}",
                "subtype": chapter_subtype,
                "urn": ch["urn"],
                "subpassages": [],
            })
        return entries

    def _build_nested_toc(
        self,
        chunks: list[dict],
        book_subtype: str,
        chapter_subtype: str,
        base_urn: str,
    ) -> list[dict[str, Any]]:
        """Nested depth-0 book / depth-1 chapter entries."""
        # Group chapters by book, preserving insertion order.
        books: dict[str, list[dict]] = {}
        for ch in chunks:
            book_n = ch.get("book", "")
            books.setdefault(book_n, []).append(ch)

        toc = []
        for book_idx, (book_n, chapters) in enumerate(books.items(), 1):
            subpassages = []
            for chap_idx, ch in enumerate(chapters, 1):
                n = ch.get("chapter", str(chap_idx))
                subpassages.append({
                    "depth": 1,
                    "index": chap_idx,
                    "label": f"{chapter_subtype.capitalize()} {n}",
                    "subtype": chapter_subtype,
                    "urn": ch["urn"],
                    "subpassages": [],
                })
            toc.append({
                "depth": 0,
                "index": book_idx,
                "label": f"{book_subtype.capitalize()} {book_n}",
                "subtype": book_subtype,
                "urn": f"{base_urn}:{book_n}",
                "subpassages": subpassages,
            })
        return toc
