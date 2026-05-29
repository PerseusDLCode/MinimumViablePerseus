# mvp/corpus/index_serializers.py
#
# Serialisers for ChunkIndex and WordIndex.
#
# Each serialiser follows the same two-method contract as CitationIndexGenerator:
#   generate() -> pure data transformation, no I/O
#   write(path) -> creates parents and writes the output file
#
# ChunkIndex  serialises to JSON   (one structured document per TEI file)
# WordIndex   serialises to JSONL  (one occurrence per line; streaming-friendly
#                                   for corpora with millions of word tokens)
#
# The ChunkOccurrence.chunk field is emitted as "text" in the JSON output
# to be more intuitive for downstream consumers.

from __future__ import annotations

import json
from pathlib import Path

from mvp.corpus.models import ChunkIndex, TEIMetadata, WordIndex


class ChunkIndexSerializer:
    """Serialises a ChunkIndex to a JSON file.

    Output format:
        {
          "version": "1",
          "document": { "source_path": ..., "base_urn": ..., "language": ... },
          "chunks": [
            { "xpath": ..., "urn": null, "element": "l", "text": ... },
            ...
          ]
        }
    """

    def __init__(self, chunk_index: ChunkIndex, metadata: TEIMetadata) -> None:
        self._index = chunk_index
        self._meta = metadata

    def generate(self) -> dict:
        """Return the chunk index as a dict ready for json.dump."""
        return {
            "version": "1",
            "document": {
                "source_path": str(self._meta.source_path),
                "base_urn": self._meta.urn,
                "language": self._meta.language,
            },
            "chunks": [
                {
                    "xpath": entry.xpath,
                    "urn": entry.urn,
                    "element": entry.element,
                    "text": entry.chunk,
                }
                for entry in self._index.entries
            ],
        }

    def write(self, output_path: Path) -> None:
        """Write the chunk index JSON to output_path, creating parents as needed."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(self.generate(), f, ensure_ascii=False, indent=2)


class WordIndexSerializer:
    """Serialises a WordIndex to a JSONL file (one occurrence per line).

    Records are emitted in approximate document order, sorted by
    (xpath, start).  Each line is a self-contained JSON object:
        {"word": ..., "xpath": ..., "urn": null, "start": N, "end": N}

    "word" is the lowercased form stored in the index.
    """

    def __init__(self, word_index: WordIndex, metadata: TEIMetadata) -> None:
        self._index = word_index
        self._meta = metadata

    def generate(self) -> list[dict]:
        """Return all word occurrences as a list of dicts in document order."""
        records: list[dict] = []
        for word, occurrences in self._index.entries.items():
            for occ in occurrences:
                records.append({
                    "word": word,
                    "xpath": occ.xpath,
                    "urn": occ.urn,
                    "start": occ.start,
                    "end": occ.end,
                })
        records.sort(key=lambda r: (r["xpath"], r["start"]))
        return records

    def write(self, output_path: Path) -> None:
        """Write the word index to output_path as JSONL, creating parents as needed."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        records = self.generate()
        with output_path.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
