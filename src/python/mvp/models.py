# mvp/models.py — shim; to be removed in cleanup commit
from mvp.corpus.models import (  # noqa: F401
    TEIMetadata, WordOccurrence, WordIndex,
    ChunkOccurrence, ChunkIndex, CitationRecord,
)
from mvp.site.models import ChunkManifestEntry, ChunkManifest  # noqa: F401
