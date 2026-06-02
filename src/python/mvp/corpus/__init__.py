# mvp/corpus — TEI document model and corpus infrastructure.
#
# Primary layer: foundational, independent of any interface.

from mvp.corpus.tei_constants import TEI_NS, XML_NS, NS, XML_BASE, XML_ID, XML_LANG
from mvp.corpus.tei_document import LenientTEIDocument, expected_div_base, expected_leaf_base
from mvp.corpus.models import (
    TEIMetadata, CitationRecord, CitationChunk,
    WordOccurrence, WordIndex,
    ChunkOccurrence, ChunkIndex,
)
from mvp.corpus.document import TEIDocument, LANGUAGE_NAMES, normalize_lang
from mvp.corpus.corpus import Corpus
from mvp.corpus.auditors import StructureAuditor, ReferenceAuditor
from mvp.corpus.indexers import TEIIndexer, WordIndexer, ChunkIndexer
from mvp.corpus.reference_parser import ReferenceParser, ConfigurationError, CitationError

__all__ = [
    "TEI_NS", "XML_NS", "NS", "XML_BASE", "XML_ID", "XML_LANG",
    "LenientTEIDocument", "expected_div_base", "expected_leaf_base",
    "TEIMetadata", "CitationRecord", "CitationChunk",
    "WordOccurrence", "WordIndex",
    "ChunkOccurrence", "ChunkIndex",
    "TEIDocument", "LANGUAGE_NAMES", "normalize_lang",
    "Corpus",
    "StructureAuditor", "ReferenceAuditor",
    "TEIIndexer", "WordIndexer", "ChunkIndexer",
    "ReferenceParser", "ConfigurationError", "CitationError",
]
