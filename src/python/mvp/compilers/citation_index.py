from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mvp.corpus.reference_parser import ReferenceParser
from mvp.corpus.tei_document import LenientTEIDocument


def _xml_id(unit: str, passage: str) -> str:
    """Compute a valid XML/HTML id from a unit name and passage string.

    Passage dots (sub-level delimiters) are replaced with hyphens so the
    result is a valid XML Name: e.g. unit='section', passage='1.1.3'
    → 'section-1-1-3'.
    """
    return f"{unit}-{passage.replace('.', '-')}"


class CitationIndexGenerator:
    """Generates a per-document citation index from a prepared TEI document.

    'Prepared' means the document has already been through the migration
    stylesheet (transform1.xsl or equivalent): it must have <body @xml:base>
    carrying the base CTS URN and a <citeStructure> refsDecl.

    Raises ConfigurationError (from ReferenceParser) if the document is not
    properly prepared.
    """

    def __init__(self, doc: LenientTEIDocument) -> None:
        self._parser = ReferenceParser(doc)

    def generate(self) -> dict[str, Any]:
        """Return the citation index as a dict ready for JSON serialisation."""
        base_urn = self._parser.base_urn
        prefix = base_urn + ":"
        citations = []
        for record in self._parser.citation_records(depth=-1):
            passage = record.urn[len(prefix):]
            citations.append({
                "urn": record.urn,
                "unit": record.unit,
                "xml_id": _xml_id(record.unit, passage),
                "depth": record.depth,
            })
        return {"base_urn": base_urn, "citations": citations}

    def write(self, output_path: Path) -> None:
        """Write the citation index JSON to output_path, creating parents as needed."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(self.generate(), f, ensure_ascii=False, indent=2)
