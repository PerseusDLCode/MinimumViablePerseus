# mvp/models.py — shim; to be removed in cleanup commit
# Corpus-layer models now live in mvp.corpus.models.
# Site-layer models (ChunkManifestEntry, ChunkManifest) move to mvp.site.models in commit 5.

from __future__ import annotations

from dataclasses import dataclass, field

from mvp.corpus.models import (  # noqa: F401
    TEIMetadata, WordOccurrence, WordIndex,
    ChunkOccurrence, ChunkIndex, CitationRecord,
)


@dataclass
class ChunkManifestEntry:
    """A single entry in a chunk manifest: one compiled HTML page."""
    n: str
    file: str
    urn: str


@dataclass
class ChunkManifest:
    """The full manifest for a compiled document."""
    base_urn: str
    title: str
    chunks: list[ChunkManifestEntry] = field(default_factory=list)
