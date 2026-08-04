"""Grouping and rendering CommentaryLookup links for a reading-view passage."""

from dataclasses import dataclass
from typing import Any

from kodon_py.tei_parser import TEIParser
from lxml import etree
from perseus_cts.commentary import CommentaryLookup


@dataclass
class _CommentaryEntry:
    anchor_id: str
    line_ref: str | None
    lemma_elements: list[Any]
    comment_elements: list[Any]


@dataclass
class _CommentaryGroup:
    label: str
    entries: list[_CommentaryEntry]


def _parse_seg_elements(xml: str | None) -> list[Any]:
    """Parse a serialized <seg> element into TEIParser elements for rendering."""
    if not xml:
        return []
    seg_el = etree.fromstring(xml)
    return TEIParser(seg_el, base_urn="", chunk_unit="").elements


def _build_commentary_groups(lookup: CommentaryLookup) -> list[_CommentaryGroup]:
    """Group a CommentaryLookup's links by commentary, rendering lemma/comment XML.

    Each CommentaryLink carries its lemma/comment as serialized <seg> XML
    (see perseus_cts.commentary); this parses that XML through the same
    TEIParser used for the base text so it renders with ReadableTextContainer.
    """
    groups: dict[str, _CommentaryGroup] = {}
    for link in lookup.links:
        group = groups.setdefault(
            link.commentary_label,
            _CommentaryGroup(label=link.commentary_label, entries=[]),
        )
        group.entries.append(
            _CommentaryEntry(
                anchor_id=link.anchor_id,
                line_ref=link.line_ref,
                lemma_elements=_parse_seg_elements(link.lemma),
                comment_elements=_parse_seg_elements(link.comment),
            )
        )
    return list(groups.values())
