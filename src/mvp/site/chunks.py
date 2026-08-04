"""Parsing a proto-page chunk file and comparing citation values.

Citation values (e.g. "94", "1-93", "1.93") are compared via a tuple of
leading integers per dot-separated component, never as raw strings, so
sibling-alignment and TOC/scheme lookups sort and range-check correctly
across schemes of differing depth and granularity.
"""

import json
import re
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import zstandard
from citation_resolution.tei_cts_linker import Gazetteer, TEILinker
from kodon_py.tei_parser import TEIParser, TEIParserError, inject_tokens
from lxml import etree

from mvp.site import config
from mvp.site_map import token_sidecar_name


@dataclass
class _Chunk:
    cts_urn: str
    prev_urn: str | None
    next_urn: str | None
    title: str
    base_urn: str
    language: str
    elements: list[Any]


def _format_editors(editors: list[dict]) -> str:
    """Return a display string for a document's editors/translators.

    Each entry is {"name": str, "role": str} (see perseus_cts.chunker's
    document metadata, which preserves TEI's <editor role="..."> attribute).
    A recognized role is appended parenthetically (e.g. "Rudolf G. Binding
    (Translator)") so readers can tell a translation's translator from an
    edition's editor; an unrecognized or absent role is shown as a bare name,
    since most TEI <editor> elements carry no role attribute at all and are
    plain editors.
    """
    parts = []
    for editor in editors:
        name = (editor.get("name") or "").strip()
        if not name:
            continue
        role = (editor.get("role") or "").strip().lower()
        label = config._EDITOR_ROLE_LABELS.get(role)
        parts.append(f"{name} ({label})" if label else f"ed. {name}")
    return ", ".join(parts)


@cache
def _load_index_chunks(index_file: Path) -> list[dict]:
    """Load and cache an index.json's chunk list.

    Sibling-version lookups re-read a sibling's index.json on every request
    for the version family; the file doesn't change within a build, so
    caching turns O(pages) re-reads into one read per sibling version.
    """
    if not index_file.exists():
        return []
    with open(index_file, encoding="utf-8") as f:
        return json.load(f).get("chunks", [])


@lru_cache(maxsize=1)
def _gazetteer() -> Gazetteer:
    """Load and index the gazetteer once per process.

    Gazetteer.from_json parses an ~800KB file and rebuilds lookup indices;
    _parse_chunk runs once per rendered chunk (thousands per build), so
    reloading it per-call previously dominated build time.
    """
    return Gazetteer.from_json(config.GAZETTEER_PATH)


@lru_cache(maxsize=1)
def _zstd_decompressor() -> zstandard.ZstdDecompressor:
    return zstandard.ZstdDecompressor()


def _load_token_sidecar(chunk_path: Path) -> dict[str, Any] | None:
    """Return the parsed token sidecar for a chunk, decompressing on demand.

    Each sidecar is its own independently zstd-compressed file (see
    src/tools/run_tokenizer.py) rather than part of one bulk archive, so a
    single chunk's tokens can be decompressed in isolation without ever
    materializing the full token tree on disk — the uncompressed set runs
    to tens of GB for a large corpus, well past CI runner disk budgets.

    Checked in order: TOKENS_DIR (the separate, pre-generated sidecar tree,
    mirroring PROTO_DIR's layout), then a sidecar co-located with the chunk
    XML itself (compressed or, for old local checkouts, plain JSON) — the
    layout `run_tokenizer.py` writes when pointed directly at proto-pages
    for local development.
    """
    name = token_sidecar_name(chunk_path)
    candidates = []
    if config.TOKENS_DIR is not None:
        with suppress(ValueError):
            rel_dir = chunk_path.parent.resolve().relative_to(
                config.PROTO_DIR.resolve()
            )
            candidates.append(config.TOKENS_DIR / rel_dir / name)
    candidates.append(chunk_path.parent / name)

    for candidate in candidates:
        if candidate.exists():
            raw = _zstd_decompressor().decompress(candidate.read_bytes())
            return json.loads(raw)

    legacy = chunk_path.with_suffix(".tokens.json")
    if legacy.exists():
        with open(legacy, encoding="utf-8") as f:
            return json.load(f)

    return None


@cache
def _parse_chunk(path: Path) -> tuple[_Chunk, dict[str, Any]]:
    """Parse a protopage XML file into a (_Chunk, pub_info) tuple.

    Document-level metadata (title, author, language, etc.) is read from the
    sibling metadata.json written by Chunker.compile().

    Cached because sibling-version lookups (see _build_sibling_data) often
    resolve the same chunk file repeatedly across many source pages, e.g. via
    the positional-fallback strategy.
    """
    tree = etree.parse(path)

    linker = TEILinker(kb=_gazetteer(), decompose=True)
    linker.run(tree)

    # `base_urn` and `cts_urn` do not resolve to the same value:
    # `cts_urn` is the URN for the specific passage; `base_urn`
    # is the URN for the version as a whole (i.e., without the
    # citaton fragment).
    root = tree.getroot()
    base_urn = root.get("base_urn", "")
    cts_urn = root.get("cts_urn", "")
    chunk_unit = root.get("unit", "")

    metadata_path = path.parent / "metadata.json"
    document: dict[str, Any] = {}
    if metadata_path.exists():
        with open(metadata_path, encoding="utf-8") as f:
            document = json.load(f).get("document", {})

    pub_info: dict[str, Any] = {
        "title": document.get("title", ""),
        "author": document.get("author", ""),
        "editors": _format_editors(document.get("editors", [])),
        "pub_place": document.get("pub_place", ""),
        "pub_date": document.get("pub_date", ""),
    }

    content_el = root.find("elements")
    if content_el is None:
        raise TEIParserError("No content element found!")

    parser = TEIParser(content_el, base_urn, chunk_unit)

    tokens_data = _load_token_sidecar(path)
    if tokens_data is not None:
        inject_tokens(parser.elements, tokens_data.get("tokens", []))

    chunk = _Chunk(
        cts_urn=cts_urn,
        prev_urn=root.get("prev_urn"),
        next_urn=root.get("next_urn"),
        title=document.get("title", ""),
        base_urn=cts_urn.rsplit(":", 1)[0],
        language=document.get("language", ""),
        elements=parser.elements,
    )
    return chunk, pub_info


def _load_chunk_unit(metadata_path: Path) -> str:
    """Return the ``chunk_unit`` recorded in a compiled scheme's metadata.json."""
    if not metadata_path.exists():
        return ""
    with open(metadata_path, encoding="utf-8") as f:
        return json.load(f).get("chunk_unit", "")


_LEADING_INT_RE = re.compile(r"\d+")


def _chunk_end_line(cts_urn: str) -> tuple[int, ...]:
    """Return the ending position of a chunk's passage citation as a sortable key.

    Mirrors _chunk_start_line but reads the last dash-separated segment of the
    passage (e.g. the "93" in "1-93") instead of the first, so callers can
    test whether some other citation value falls anywhere within this chunk's
    full range, not just at its start.
    """
    passage = cts_urn.rsplit(":", 1)[-1]
    last_segment = passage.split("-", 1)[-1]
    key = []
    for component in last_segment.split("."):
        match = _LEADING_INT_RE.match(component)
        key.append(int(match.group()) if match else 0)
    return tuple(key)


def _chunk_start_line(cts_urn: str) -> tuple[int, ...]:
    """Return the starting position of a chunk's passage citation as a sortable key.

    Scene-level passages are line ranges ("1-93"); card-level passages are
    a single line number ("49"); some works cite by dotted components
    ("1.1" for book.line in Thucydides) or mix in a letter suffix ("1a").

    The passage is split on "." *before* any digit extraction, so each
    dot-separated component (e.g. book, then line) contributes its own
    leading integer to the key. Comparing the resulting tuples sorts
    correctly across component rollovers (e.g. "1.93" < "2.1"), unlike
    parsing the whole string as one number would. A component with no
    leading digits (unexpected input) contributes 0 rather than raising.
    """
    passage = cts_urn.rsplit(":", 1)[-1]
    first_segment = passage.split("-", 1)[0]
    key = []
    for component in first_segment.split("."):
        match = _LEADING_INT_RE.match(component)
        key.append(int(match.group()) if match else 0)
    return tuple(key)


def _iter_citation_values(elements: list[Any]) -> Iterator[str]:
    """Yield every element's own ``n`` citation value, recursively.

    TEIParser only stamps an element's ``urn`` field when it carries *both*
    ``type`` and ``n`` (see kodon_py.tei_parser.handle_element) — but a
    verse-line milestone scheme like Sophocles' commonly cites via bare
    ``<l n="...">`` (no ``type``), so ``urn`` stays None throughout and can't
    be used here. Structural wrapper elements (``div``, ``sp``, ``speaker``,
    etc.) never carry their own ``n``, so reading ``n`` directly off each
    element, whatever its tag, reliably picks out just the citable leaves.
    """
    for element in elements:
        n = element.get("n")
        if n:
            yield n
        yield from _iter_citation_values(element.get("children", []))


def _qualify_citation_value(value: str, cts_citation: str) -> str:
    """Prepend leading dotted components missing from a bare citation value.

    A nested cite structure (e.g. Cicero's <div type="speech" n="1"><div
    type="section" n="1">) stamps a chunk-root element with only its own
    local ``n`` ("1" for the section), not the composite "1.1" (speech.
    section) that the chunk's own ``cts_urn`` carries and that commentary
    links are keyed against. When a value has fewer dot-separated
    components than the chunk's own citation, the missing leading
    components (e.g. the speech number) are taken from that citation.
    Flat schemes (e.g. tragedy's single-component "49") already match the
    chunk citation's depth, so this is a no-op for them. Range values
    ("94-140") are qualified on each side independently.
    """
    cts_parts = cts_citation.split(".")

    def qualify(part: str) -> str:
        part_components = part.split(".")
        missing = len(cts_parts) - len(part_components)
        if missing <= 0:
            return part
        return ".".join([*cts_parts[:missing], *part_components])

    if "-" in value:
        start, end = value.split("-", 1)
        return f"{qualify(start)}-{qualify(end)}"
    return qualify(value)


def _chunk_citation_range(chunk_obj: "_Chunk") -> str:
    """Return the citation range actually spanned by a chunk's rendered elements.

    A milestone-based scheme (e.g. tragedy's "card") stamps a chunk's own
    cts_urn with only its *starting* milestone's citation value (see
    perseus_cts.cts_resolver._milestone_chunks), even though the chunk's
    elements can include several further lines up to the next milestone
    (e.g. card 1 of Trachiniae spans lines 1-48, all the way to the next
    <milestone unit="card">). Using the raw cts_urn/chunk value for a
    commentary lookup therefore only matches commentary anchored to that
    first line. This instead scans every citable value actually present in
    the chunk and returns the full "start-end" span (or a single value when
    the chunk covers only one line), so callers like links_for_passage see
    the whole rendered passage.
    """
    cts_citation = chunk_obj.cts_urn.rsplit(":", 1)[-1]
    values = list(_iter_citation_values(chunk_obj.elements))
    if not values:
        return cts_citation

    values = [_qualify_citation_value(v, cts_citation) for v in values]
    start = min(values, key=_chunk_start_line).split("-", 1)[0]
    end = max(values, key=_chunk_end_line).rsplit("-", 1)[-1]
    return start if start == end else f"{start}-{end}"


def _find_chunk_for_line(chunks: list[dict], line: tuple[int, ...]) -> dict | None:
    """Return the chunk with the greatest start line at or before ``line``.

    Works for both scene chunks (few, wide ranges) and card chunks (many,
    single-line starts) since chunk boundaries are always given by
    monotonically increasing start lines."""
    best: dict | None = None
    best_start: tuple[int, ...] | None = None
    for chunk in chunks:
        start = _chunk_start_line(chunk["cts_urn"])
        if start <= line and (best_start is None or start > best_start):
            best, best_start = chunk, start
    return best


def _chunk_distance(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, ...]:
    """Return an elementwise-absolute-difference key for comparing closeness of two citation keys.

    Shorter tuples are zero-padded so citation keys of differing depth (e.g.
    mismatched citeStructure schemes between sibling versions) compare
    safely. Lexicographic comparison of the resulting tuples orders "closer"
    correctly for hierarchical citations: a difference in a higher-order
    component (e.g. book) always outweighs any difference in a lower-order
    one (e.g. line), matching how the citation values themselves are ordered.
    """
    length = max(len(a), len(b))
    a = a + (0,) * (length - len(a))
    b = b + (0,) * (length - len(b))
    return tuple(abs(x - y) for x, y in zip(a, b))


def _find_nearest_chunk(chunks: list[dict], line: tuple[int, ...]) -> dict | None:
    """Return the chunk whose start line is closest to ``line``, before or after.

    Used to align sibling editions/translations whose chunk granularity
    differs from the currently displayed version (see _build_sibling_data):
    the aligned passage should be whichever sibling chunk is nearest to the
    current position, not merely the nearest preceding or following one.
    Ties (equal distance before and after) prefer the earlier chunk, since
    chunks are iterated in ascending order and only a strictly smaller
    distance replaces the current best.
    """
    best: dict | None = None
    best_dist: tuple[int, ...] | None = None
    for chunk in chunks:
        start = _chunk_start_line(chunk["cts_urn"])
        dist = _chunk_distance(line, start)
        if best_dist is None or dist < best_dist:
            best, best_dist = chunk, dist
    return best
