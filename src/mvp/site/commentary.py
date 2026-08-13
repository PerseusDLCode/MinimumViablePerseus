"""Grouping and rendering CommentaryLookup links for a reading-view passage."""

from dataclasses import dataclass
from typing import Any

from kodon_py.tei_parser import TEIParser
from lxml import etree
from perseus_cts.commentary import CommentaryLookup
from perseus_cts.models.cts_catalog import CTSCatalog

from mvp.site import config
from mvp.site.chunks import _load_index_chunks
from mvp.site.siblings import _reading_view_url


@dataclass
class _CommentaryEntry:
    anchor_id: str
    line_ref: str | None
    lemma_elements: list[Any]
    comment_elements: list[Any]


@dataclass
class _CommentaryGroup:
    label: str
    description: str
    focus_url: str | None
    entries: list[_CommentaryEntry]


def _parse_seg_elements(xml: str | None) -> list[Any]:
    """Parse a serialized <seg> element into TEIParser elements for rendering."""
    if not xml:
        return []
    seg_el = etree.fromstring(xml)
    return TEIParser(seg_el, base_urn="", chunk_unit="").elements


def _commentary_focus_url(
    commentary_urn: str, entries: list[_CommentaryEntry]
) -> str | None:
    """Link into the commentary's own reading view, focused on this passage.

    Commentary chunk files are raw TEI (the same source _parse_chunk reads),
    so the chunk actually containing a given entry's comment <seg> can be
    found directly by searching each chunk file's text for that seg's
    @xml:id — this works regardless of how a commentary structures its own
    citation scheme (per-line "commline" divs, per-page/section divs, or a
    single chunk covering the whole work), unlike matching against `line_ref`
    (the base-text line commented on, not a citation in the commentary's own
    structure), which only lined up by coincidence for line-chunked sources.
    """
    corpus = commentary_urn.split(":")[2]
    textgroup, work, version = commentary_urn.split(":")[3].split(".")
    version_dir = config.PROTO_DIR / corpus / textgroup / work / version
    chunks = _load_index_chunks(version_dir / "index.json")
    if not chunks:
        return None

    for entry in entries:
        if not entry.anchor_id:
            continue
        needle = f'xml:id="{entry.anchor_id}"'
        for chunk in chunks:
            chunk_file = version_dir / chunk["file"]
            if not chunk_file.exists():
                continue
            if needle in chunk_file.read_text(encoding="utf-8"):
                citation = chunk["cts_urn"].rsplit(":", 1)[-1]
                return _reading_view_url(corpus, textgroup, work, version, citation)

    if len(chunks) == 1:
        citation = chunks[0]["cts_urn"].rsplit(":", 1)[-1]
        return _reading_view_url(corpus, textgroup, work, version, citation)

    return None


def _build_commentary_groups(
    lookup: CommentaryLookup, catalog: CTSCatalog
) -> list[_CommentaryGroup]:
    """Group a CommentaryLookup's links by commentary, rendering lemma/comment XML.

    Each CommentaryLink carries its lemma/comment as serialized <seg> XML
    (see perseus_cts.commentary); this parses that XML through the same
    TEIParser used for the base text so it renders with ReadableTextContainer.
    """
    labels: dict[str, str] = {}
    entries_by_urn: dict[str, list[_CommentaryEntry]] = {}
    for link in lookup.links:
        labels[link.commentary_urn] = link.commentary_label
        entries_by_urn.setdefault(link.commentary_urn, []).append(
            _CommentaryEntry(
                anchor_id=link.anchor_id,
                line_ref=link.line_ref,
                lemma_elements=_parse_seg_elements(link.lemma),
                comment_elements=_parse_seg_elements(link.comment),
            )
        )

    groups = []
    for commentary_urn, entries in entries_by_urn.items():
        version = catalog.version_for(commentary_urn)
        groups.append(
            _CommentaryGroup(
                label=labels[commentary_urn],
                description=version.description if version else "",
                focus_url=_commentary_focus_url(commentary_urn, entries),
                entries=entries,
            )
        )
    return groups
