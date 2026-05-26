# mvp/corpus/corpus.py
#
# Corpus: discovers and enumerates TEI source documents.
#
# Documents are loaded lazily: documents() is an iterator, so the
# full corpus is not held in memory simultaneously.

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mvp.corpus.document import TEIDocument


class Corpus:
    """A collection of TEI source documents under a root directory.

    Discovers all .xml files recursively under root, excluding CTS
    catalog files (__cts__.xml).  Documents are loaded lazily by the
    documents() iterator.

    Args:
        root: Root directory of the corpus (e.g. data/canonical-greekLit).

    Raises:
        FileNotFoundError: If root does not exist.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        if not self._root.exists():
            raise FileNotFoundError(f"Corpus root not found: {self._root}")

    @property
    def root(self) -> Path:
        return self._root

    def documents(self) -> Iterator[TEIDocument]:
        """Yield TEIDocuments for all XML files under the corpus root.

        Skips __cts__.xml catalog files, which describe collection
        structure rather than containing text to compile.

        Files that cannot be parsed are skipped; a summary of all
        failures is printed after the last file is processed.
        """
        from mvp.corpus.document import TEIDocument  # noqa: PLC0415

        failures: list[tuple[Path, Exception]] = []
        for xml_path in sorted(self._root.rglob("*.xml")):
            if xml_path.name == "__cts__.xml":
                continue
            try:
                yield TEIDocument.from_path(xml_path)
            except Exception as exc:
                failures.append((xml_path, exc))

        if failures:
            print(f"Warning: skipped {len(failures)} file(s) due to parse errors:")
            for path, exc in failures:
                print(f"  {path}: {exc}")

    def document(self, urn: str) -> TEIDocument:
        """Return the TEIDocument whose metadata.urn matches urn.

        Raises:
            KeyError: If no document with that URN is found.

        Note: This performs a linear scan.  For repeated lookups,
        callers should build an index over corpus.documents().
        """
        for doc in self.documents():
            if doc.metadata.urn == urn:
                return doc
        raise KeyError(f"No document found with URN: {urn}")
