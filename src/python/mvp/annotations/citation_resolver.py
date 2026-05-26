from __future__ import annotations

import json
from pathlib import Path


class CitationResolver:
    """Resolves classical citation strings to CTS URNs.

    Ported from Charles Pletcher's citation-resolution module
    (https://github.com/PerseusDLCode/citation-resolution).

    Args:
        abbreviations_dir: Directory containing ocd_abbreviations.json
                           and inverted_urn.json.

    Usage::

        resolver = CitationResolver(Path("data/abbreviations"))
        urn = resolver.resolve("Hom. Od. 1.1")
        # -> "urn:cts:greekLit:tlg0012.tlg002:1.1"
    """

    def __init__(self, abbreviations_dir: Path) -> None:
        abbreviations_dir = Path(abbreviations_dir)

        abbrevs_list: list[dict] = json.loads(
            (abbreviations_dir / "ocd_abbreviations.json").read_text(encoding="utf-8")
        )
        self._abbreviations: dict[str, list[str]] = {}
        for entry in abbrevs_list:
            self._abbreviations.setdefault(entry["abbrev"], []).append(entry["full"])

        self._inverted_urns: dict[str, dict[str, str]] = json.loads(
            (abbreviations_dir / "inverted_urn.json").read_text(encoding="utf-8")
        )

    def resolve(self, citation: str) -> str | None:
        """Resolve a citation string to a CTS URN with location.

        Citation format: "AUTHOR_ABBREV [WORK_ABBREV] LOCATION"
        where author and work are standard scholarly abbreviations.

        Returns the CTS URN string ("urn:cts:...:location"), or None if
        the author, work, or URN cannot be resolved.
        """
        parts = citation.split()
        if len(parts) < 2:
            return None

        author_abbrev = parts[0]
        location = parts[-1]
        work_abbrev = " ".join(parts[1:-1])

        if not work_abbrev:
            return None

        author_full = self._expand(author_abbrev)
        if author_full is None:
            return None

        author_dict = self._inverted_urns.get(author_full.lower())
        if author_dict is None:
            return None

        work_full = self._expand(work_abbrev)
        if work_full is None:
            return None

        cts_urn = author_dict.get(work_full.lower())

        if cts_urn is None:
            prefix = work_full.lower()
            matches = [v for k, v in author_dict.items() if k.startswith(prefix)]
            cts_urn = matches[0] if matches else None

        if cts_urn is None:
            return None

        return f"{cts_urn}:{location}"

    def _expand(self, abbreviation: str) -> str | None:
        """Return the first full expansion of abbreviation, or None."""
        matches = self._abbreviations.get(abbreviation, [])
        return matches[0] if matches else None
