from __future__ import annotations

from dataclasses import dataclass, field


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
