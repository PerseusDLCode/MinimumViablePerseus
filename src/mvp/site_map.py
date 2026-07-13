from __future__ import annotations

from pathlib import Path


class SiteMap:
    """Output path and URL scheme for all Perseus6 compiled artifacts.

    All path construction is centralised here.  Pipeline stages obtain
    output paths from SiteMap rather than constructing them directly.

    The URL scheme is:
        /{namespace}/{textgroup}/{work}/{version}/    — chunk pages
        /catalog/{language}.html                     — catalog pages
        /{namespace}/{textgroup}/{work}/{version}/index.json  — manifests

    URN components are mapped as follows:
        urn:cts:{namespace}:{textgroup}.{work}.{version}:{passage}
        → {namespace}/{textgroup}/{work}/{version}/

    Args:
        output_root: Root directory for all compiled output.
    """

    def __init__(self, output_root: Path | str) -> None:
        self._root = Path(output_root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def chunk_dir(self, urn: str, scheme: str | None = None) -> Path:
        """Return the output directory for chunk pages of a document.

        A document may declare more than one citeStructure/refsDecl scheme
        (e.g. scene/line vs. card-based chunking for a tragedy). The default
        scheme is compiled directly into the version directory; any
        additional scheme is compiled into a same-named subdirectory.
        """
        path = self._root / self._urn_to_path(urn)
        if scheme:
            path = path / scheme
        path.mkdir(parents=True, exist_ok=True)
        return path

    def chunk_path(self, urn: str, chunk_id: str) -> Path:
        """Return the output path for a single chunk HTML file."""
        return self.chunk_dir(urn) / f"chunk_{chunk_id}.html"

    def manifest_path(self, urn: str) -> Path:
        """Return the output path for a document's index.json manifest."""
        return self.chunk_dir(urn) / "index.json"

    def citations_path(self, urn: str) -> Path:
        """Return the output path for a document's citation index JSON sidecar."""
        return self.chunk_dir(urn) / "citations.json"

    def chunk_index_path(self, urn: str) -> Path:
        """Return the output path for a document's chunk index JSON file."""
        return self.chunk_dir(urn) / "chunks.json"

    def word_index_path(self, urn: str) -> Path:
        """Return the output path for a document's word index JSONL file."""
        return self.chunk_dir(urn) / "words.jsonl"

    def catalog_path(self, language: str) -> Path:
        """Return the output path for a language catalog page."""
        catalog_dir = self._root / "catalog"
        catalog_dir.mkdir(parents=True, exist_ok=True)
        return catalog_dir / f"{language}.html"

    # ------------------------------------------------------------------
    # Private

    def _urn_to_path(self, urn: str) -> Path:
        """Convert a CTS URN to a relative filesystem path.

        urn:cts:greekLit:tlg0011.tlg001.perseus-grc2
        → greekLit/tlg0011/tlg001/perseus-grc2

        urn:cts:latinLit:phi1017.phi007.perseus-lat2:57
        → latinLit/phi1017/phi007/perseus-lat2  (passage citation stripped)
        """
        bare = urn.removeprefix("urn:cts:")
        parts = bare.split(":", 1)
        if len(parts) == 2:
            namespace = parts[0]
            work = parts[1].split(":")[0]
            return Path(namespace, *work.split("."))
        return Path(bare.replace(":", "_").replace(".", "_"))
