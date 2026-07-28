import json
import multiprocessing
import os
import re

from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache, partial
from pathlib import Path
from typing import Any

import markdown

from flask import Flask, abort, render_template, redirect, url_for
from lxml import etree

import citation_resolution

from citation_resolution.tei_cts_linker import Gazetteer, TEILinker
from kodon_py.tei_parser import TEIParser, TEIParserError, inject_tokens
from perseus_cts.chunker import Chunker
from perseus_cts.commentary import CommentaryLookup, links_for_passage
from perseus_cts.cts_resolver import available_refsDecl_ids
from perseus_cts.models import Corpus, CTSCatalog, CTSVersion
from mvp.site_map import SiteMap


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_GAZETTEER = (
    Path(citation_resolution.__file__).parent / "data" / "gazetteer.json"
)
GAZETTEER_PATH = Path(os.getenv("GAZETTEER_PATH", _DEFAULT_GAZETTEER))
CORPORA_DIR = Path(os.getenv("CORPORA_DIR", ROOT_DIR / "corpora"))
MARKDOWN_DIR = APP_DIR / "static" / "markdown"
NEWS_MARKDOWN = MARKDOWN_DIR / "news.md"
RESEARCH_MARKDOWN = MARKDOWN_DIR / "research.md"
MORPH_URL = os.getenv("MORPH_URL", "http://localhost:8000/morph")
PROTO_DIR = Path(os.getenv("PROTOPAGE_OUTPUT_DIR", ROOT_DIR / "proto-pages"))
# Proto-page compilation and page freezing are both CPU-bound and
# embarrassingly parallel (independent per document / per URL), so both
# phases of `mvp-build` fan out across this many worker processes. Defaults
# to all cores; set to 1 to force the old sequential behavior.
BUILD_WORKERS = max(1, int(os.getenv("MVP_BUILD_WORKERS", os.cpu_count() or 1)))

_CORPUS_LABELS = {
    "greekLit": "Greek",
    "hebrewlit": "Hebrew",
    "latinLit": "Latin",
}

_CORPUS_REPO = {
    "greekLit": "canonical-greekLit",
    "hebrewLit": "First1KGreek",
    "latinLit": "canonical-latinLit",
}


_LANGUAGE_LABELS = {
    "deu": "German",
    "eng": "English",
    "fre": "French",
    "ger": "German",
    "grc": "Greek",
    "ita": "Italian",
    "lat": "Latin",
}


_EDITOR_ROLE_LABELS = {
    "translator": "Translator",
    "transl": "Translator",
    "editor": "Editor",
    "associate editor": "Associate Editor",
    "assistant editor": "Assistant Editor",
    "commentator": "Commentator",
}


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
        label = _EDITOR_ROLE_LABELS.get(role)
        parts.append(f"{name} ({label})" if label else f"ed. {name}")
    return ", ".join(parts)


@dataclass
class _Chunk:
    cts_urn: str
    prev_urn: str | None
    next_urn: str | None
    title: str
    base_urn: str
    language: str
    elements: list[Any]


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


def _annotate_toc(
    entries: list[dict],
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    scheme: str | None = None,
) -> list[dict]:
    """Recursively add endpoint/route_kwargs to leaf TOC entries.

    ReferenceParser.toc() returns entries with urn/label/subpassages but no
    routing info.  NavigationItem.html.jinja needs endpoint/route_kwargs on
    leaf nodes to build hrefs via url_for(item.endpoint, **item.route_kwargs).
    """
    endpoint = "reading_view_scheme" if scheme else "reading_view"
    for entry in entries:
        if entry.get("subpassages"):
            _annotate_toc(
                entry["subpassages"], corpus, textgroup, work, version, scheme
            )
        else:
            route_kwargs = {
                "corpus": corpus,
                "textgroup": textgroup,
                "work": work,
                "version": version,
                "chunk": entry["urn"].rsplit(":", 1)[-1],
            }
            if scheme:
                route_kwargs["scheme"] = scheme
            entry["endpoint"] = endpoint
            entry["route_kwargs"] = route_kwargs
    return entries


def _work_title(catalog: CTSCatalog, work_urn: str, fallback: str = "") -> str:
    """Return a work's title for display, via CTSWork.title_for.

    Prefers English, then falls back to Latin — some __cts__.xml files only
    supply a <ti:title xml:lang="lat"> (e.g. Trachiniae, or First1KGreek's
    ggm0001.ggm001), and a Latin title is still far more useful to a reader
    than the raw URN fragment. Falls back to `fallback` only when neither is
    available. Callers should pass a script-neutral fallback (e.g. a work
    ID), not a document's own-language title, or the same title-availability
    problem just resurfaces one level down.
    """
    work = catalog.work_for(work_urn)
    if work is not None:
        title = work.title_for("eng") or work.title_for("lat")
        if title:
            return title
    return fallback


def _group_name(catalog: CTSCatalog, textgroup_urn: str, fallback: str = "") -> str:
    """Return a textgroup's display name for the collections tree.

    Reads CTSGroup.group_names (parsed from __cts__.xml's <ti:groupname>
    elements), preferring English and falling back to whatever language is
    available. This is the textgroup-level source of truth; per-work TEI
    <author> elements are unreliable (e.g. missing/mis-nested in some
    First1KGreek headers), so callers should prefer this over a document's
    own author field.

    Falls back to a namespace-agnostic id match when the exact urn misses:
    the proto-page tree is keyed by a document's own urn namespace, but a
    textgroup's __cts__.xml occasionally declares a different namespace for
    the same numeric id (e.g. a commentary's own file says "latinLit" while
    its work/version files and TEI documents say "greekLit") — a data bug
    in the corpus, not something this lookup can otherwise route around.
    """
    group = catalog.group_for(textgroup_urn)
    if group is None:
        textgroup_id = textgroup_urn.rsplit(":", 1)[-1]
        for candidate in catalog.groups.values():
            if candidate.urn.rsplit(":", 1)[-1] == textgroup_id:
                group = candidate
                break
    if group is not None:
        name = group.group_names.get("eng") or next(
            iter(group.group_names.values()), ""
        )
        if name:
            return name
    return fallback


def _build_collections(proto_dir: Path, catalog: CTSCatalog) -> list[dict]:
    """Build the nested corpus → textgroup → work → version catalog tree.

    Each level is included only when it has at least one populated child, so
    empty directories never surface in the catalog.
    """
    collections = []

    for corpus_dir in _subdirs(proto_dir):
        corpus = corpus_dir.name
        textgroups = []

        for textgroup_dir in _subdirs(corpus_dir):
            textgroup_urn = f"urn:cts:{corpus}:{textgroup_dir.name}"
            author = _group_name(catalog, textgroup_urn, textgroup_dir.name)
            works = []

            for work_dir in _subdirs(textgroup_dir):
                versions = []

                for version_dir in _subdirs(work_dir):
                    entry = _version_entry(
                        corpus, textgroup_dir, work_dir, version_dir, catalog
                    )
                    if entry is None:
                        continue
                    version, _document = entry
                    versions.append(version)

                if versions:
                    works.append({"id": work_dir.name, "versions": versions})

            if works:
                textgroups.append(
                    {"id": textgroup_dir.name, "author": author, "works": works}
                )

        if textgroups:
            collections.append(
                {
                    "id": corpus,
                    "label": _CORPUS_LABELS.get(corpus, corpus),
                    "textgroups": textgroups,
                }
            )

    return collections


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


@lru_cache(maxsize=None)
def _load_index_chunks(index_file: Path) -> list[dict]:
    """Load and cache an index.json's chunk list.

    _build_sibling_data re-reads a sibling version's index.json on every
    request for the version family; the file doesn't change within a build,
    so caching turns O(pages) re-reads into one read per sibling version.
    """
    if not index_file.exists():
        return []
    with open(index_file, encoding="utf-8") as f:
        return json.load(f).get("chunks", [])


def _build_sibling_data(
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    chunk: str,
    current_line: tuple[int, ...],
    catalog: CTSCatalog,
    base_urn: str,
) -> dict:
    """Build sibling edition/translation chunk data using catalog + citation value.

    For each sibling version, loads its index.json and finds the corresponding
    chunk by:
      Strategy 1 — exact passage reference match
      Strategy 2 — nearest chunk to the same citation value, before or after

    Chunk boundaries can differ in granularity between sibling versions (e.g.
    a card-chunked edition against a line-chunked translation), so falling
    back to raw chunk position (as opposed to citation value) can land on a
    wildly mismatched passage; see _chunk_start_line/_find_nearest_chunk.
    This lookup runs symmetrically for both edition_chunks and
    translation_chunks regardless of which version is currently displayed
    (base_urn), so alignment is consistent in both directions: reading an
    edition aligns sibling translations, and reading a translation aligns
    sibling editions, to the nearest counterpart passage.

    Returns dict with keys:
      current_version: CTSVersion | None
      edition_chunks: list[(CTSVersion, _Chunk | None)]
      translation_chunks: list[(CTSVersion, _Chunk | None)]
    """
    work_urn = base_urn.rsplit(".", 1)[0]

    def _lookup(sib: CTSVersion) -> tuple[CTSVersion, _Chunk | None] | None:
        sib_id = sib.urn.split(":")[3].split(".")[-1]
        if sib_id == version:
            return sib, None

        index_file = PROTO_DIR / corpus / textgroup / work / sib_id / "index.json"
        sib_chunks = _load_index_chunks(index_file)
        if not sib_chunks:
            return sib, None

        # A partial version (e.g. a translation covering only a few chapters
        # of a work) shouldn't be shown as a sibling of every chunk in the
        # full text — only of chunks actually within its own citation range.
        # Outside that range there is no meaningful "nearest" passage, so
        # exclude the sibling entirely rather than clamping to an edge chunk.
        starts = [_chunk_start_line(c["cts_urn"]) for c in sib_chunks]
        if current_line < min(starts) or current_line > max(starts):
            return None

        # Strategy 1: exact passage-reference match.
        entry = next(
            (c for c in sib_chunks if c["cts_urn"].endswith(f":{chunk}")),
            None,
        )
        # Strategy 2: nearest chunk to the same citation value, before or after.
        if entry is None:
            entry = _find_nearest_chunk(sib_chunks, current_line) or sib_chunks[0]
        if entry is None:
            return sib, None

        chunk_file = PROTO_DIR / corpus / textgroup / work / sib_id / entry["file"]
        if not chunk_file.exists():
            return sib, None

        sib_chunk, _ = _parse_chunk(chunk_file)
        return sib, sib_chunk

    return {
        "current_version": catalog.version_for(base_urn),
        "edition_chunks": [
            result
            for sib in catalog.editions_of(work_urn)
            if sib.urn != base_urn and (result := _lookup(sib)) is not None
        ],
        "translation_chunks": [
            result
            for sib in catalog.translations_of(work_urn)
            if sib.urn != base_urn and (result := _lookup(sib)) is not None
        ],
    }


def _build_urn_index(proto_dir: Path) -> dict[str, dict[str, str]]:
    """Map work-level CTS URNs to a language→URL-prefix dict.

    e.g. "urn:cts:latinLit:phi0917.phi001" -> {"lat": "/latinLit:phi0917.phi001.perseus-lat1/",
                                                "eng": "/latinLit:phi0917.phi001.perseus-eng2/"}
    For each language, the first version found (sorted) wins.
    The JS appends the passage and a trailing slash to the chosen prefix.
    """
    index: dict[str, dict[str, str]] = {}

    for corpus_dir, tg_dir, work_dir, ver_dir in _iter_version_dirs(proto_dir):
        meta_file = ver_dir / "metadata.json"
        if not meta_file.exists():
            continue
        with open(meta_file, encoding="utf-8") as f:
            language = json.load(f).get("document", {}).get("language", "")
        if not language:
            continue

        corpus = corpus_dir.name
        work_urn = f"urn:cts:{corpus}:{tg_dir.name}.{work_dir.name}"
        url_prefix = f"/{corpus}:{tg_dir.name}.{work_dir.name}.{ver_dir.name}"
        index.setdefault(work_urn, {}).setdefault(language, url_prefix)

    return index


def _discover_corpora(corpora_dir: Path) -> list[Corpus]:
    """Return a Corpus for each subdirectory of corpora_dir that exists."""
    corpora = []
    for subdir in _subdirs(corpora_dir):
        data = subdir / "data"
        root = data if data.is_dir() else subdir
        try:
            corpora.append(Corpus(root))
        except FileNotFoundError:
            pass
    return corpora


def _iter_version_dirs(
    proto_dir: Path,
) -> Iterator[tuple[Path, Path, Path, Path]]:
    """Yield ``(corpus_dir, textgroup_dir, work_dir, version_dir)`` tuples.

    Walks the four-level proto-page tree
    (``corpus / textgroup / work / version``), skipping non-directory entries
    at every level.
    """
    for corpus_dir in _subdirs(proto_dir):
        for textgroup_dir in _subdirs(corpus_dir):
            for work_dir in _subdirs(textgroup_dir):
                for version_dir in _subdirs(work_dir):
                    yield corpus_dir, textgroup_dir, work_dir, version_dir


def _parse_seg_elements(xml: str | None) -> list[Any]:
    """Parse a serialized <seg> element into TEIParser elements for rendering."""
    if not xml:
        return []
    seg_el = etree.fromstring(xml)
    return TEIParser(seg_el, base_urn="", chunk_unit="").elements


@lru_cache(maxsize=1)
def _gazetteer() -> Gazetteer:
    """Load and index the gazetteer once per process.

    Gazetteer.from_json parses an ~800KB file and rebuilds lookup indices;
    _parse_chunk runs once per rendered chunk (thousands per build), so
    reloading it per-call previously dominated build time.
    """
    return Gazetteer.from_json(GAZETTEER_PATH)


@lru_cache(maxsize=None)
def _parse_chunk(path: Path) -> tuple[_Chunk, dict[str, Any]]:
    """Parse a protopage XML file into a (_Chunk, pub_info) tuple.

    Document-level metadata (title, author, language, etc.) is read from the
    sibling metadata.json written by Chunker.compile().

    Cached because sibling-version lookups (see _build_sibling_data) often
    resolve the same chunk file repeatedly across many source pages, e.g. via
    the positional-fallback strategy.
    """
    tree = etree.parse(path)

    # Resolve citations inline.
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

    sidecar = path.with_suffix(".tokens.json")
    if sidecar.exists():
        with open(sidecar, encoding="utf-8") as f:
            inject_tokens(parser.elements, json.load(f).get("tokens", []))

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


def _scheme_dirs(version_dir: Path) -> list[str]:
    """Return the names of alternate citeStructure scheme subdirectories.

    The default scheme's index.json/metadata.json live directly in
    version_dir; any additional scheme (see _scheme_slug) lives in a
    same-named subdirectory alongside its own index.json/metadata.json."""
    return [d.name for d in _subdirs(version_dir) if (d / "index.json").exists()]


_LEADING_INT_RE = re.compile(r"\d+")


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


def _scheme_toggle_links(
    version_dir: Path,
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    current_scheme: str | None,
    current_line: tuple[int, ...],
) -> list[dict]:
    """Return links to the same passage under each other available scheme."""
    links: list[dict] = []
    for scheme in [None, *_scheme_dirs(version_dir)]:
        if scheme == current_scheme:
            continue
        data_dir = version_dir / scheme if scheme else version_dir
        chunks = _load_index_chunks(data_dir / "index.json")
        if not chunks:
            continue
        target = _find_chunk_for_line(chunks, current_line) or chunks[0]
        passage = target["cts_urn"].rsplit(":", 1)[-1]
        base_path = f"/urn:cts:{corpus}:{textgroup}.{work}.{version}"
        if scheme:
            base_path += f"/{scheme}"
        label = f"By {scheme.capitalize()}" if scheme else "By Scene"
        links.append({"label": label, "url": f"{base_path}:{passage}/"})
    return links


def _subdirs(path: Path) -> list[Path]:
    """Return the immediate subdirectories of ``path``, sorted by name.

    Returns an empty list when ``path`` is not a directory, letting callers
    iterate without a separate existence check.
    """
    if not path.is_dir():
        return []
    return [child for child in sorted(path.iterdir()) if child.is_dir()]


def _toc_from_metadata(
    metadata_path: Path,
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    scheme: str | None = None,
) -> dict:
    """Load and annotate the TOC from a metadata.json file.

    Returns a dict shaped as {"table_of_contents": [...]}, matching
    what reading.html.jinja expects from toc.get("table_of_contents", []).
    """
    if not metadata_path.exists():
        return {"table_of_contents": []}

    with open(metadata_path, encoding="utf-8") as f:
        toc_entries = json.load(f).get("toc", [])

    _annotate_toc(toc_entries, corpus, textgroup, work, version, scheme)
    return {"table_of_contents": toc_entries}


def _version_entry(
    corpus: str,
    textgroup_dir: Path,
    work_dir: Path,
    version_dir: Path,
    catalog: CTSCatalog,
) -> tuple[dict, dict] | None:
    """Parse one version directory into a ``(version, document_metadata)`` pair.

    Returns ``None`` when the version is missing its ``index.json`` /
    ``metadata.json`` sidecars or has no chunks, so callers can skip it.
    """
    index_file = version_dir / "index.json"
    metadata_file = version_dir / "metadata.json"
    if not index_file.exists() or not metadata_file.exists():
        return None

    with open(index_file, encoding="utf-8") as f:
        chunks = json.load(f).get("chunks", [])
    if not chunks:
        return None

    with open(metadata_file, encoding="utf-8") as f:
        document = json.load(f).get("document", {})

    language = document.get("language", "")
    first_passage = chunks[0]["cts_urn"].rsplit(":", 1)[-1]
    work_urn = f"urn:cts:{corpus}:{textgroup_dir.name}.{work_dir.name}"
    version = {
        "id": version_dir.name,
        "title": _work_title(catalog, work_urn, fallback=work_dir.name),
        "language": language,
        "language_label": _LANGUAGE_LABELS.get(language, language),
        "editors": _format_editors(document.get("editors", [])),
        "first_chunk_kwargs": dict(
            corpus=corpus,
            textgroup=textgroup_dir.name,
            work=work_dir.name,
            version=version_dir.name,
            chunk=first_passage,
        ),
    }
    return version, document


def _xml_src_url(corpus: str, textgroup: str, work: str, version: str) -> str:
    repo = _CORPUS_REPO.get(corpus, f"canonical-{corpus}")
    filename = f"{textgroup}.{work}.{version}.xml"
    return (
        f"https://raw.githubusercontent.com/PerseusDL/{repo}/master"
        f"/data/{textgroup}/{work}/{filename}"
    )


def _scheme_slug(refsDecl_id: str) -> str:
    """Return the subdirectory name for a non-default citeStructure scheme.

    The default scheme (xml:id="CTS") compiles directly into the version
    directory (slug ""); any additional scheme (e.g. "CTS-card") compiles
    into a same-named subdirectory (e.g. "card")."""
    if refsDecl_id == "CTS":
        return ""
    return refsDecl_id.removeprefix("CTS-") or refsDecl_id.lower()


def _compile_proto_page(xml_path: Path, proto_dir: Path) -> tuple[str, str | None]:
    """Parse, urn/skip-check, and compile one TEI document.

    Runs in a worker process (see generate_proto_pages) — must never raise,
    since an uncaught exception here would abort the whole pool instead of
    just skipping this one document, unlike the previous sequential loop.

    Takes the source XML *path* rather than an already-constructed
    TEIDocument: a TEIDocument holds a parsed lxml ElementTree, which can't
    be pickled through Pool.imap_unordered's task queue, and re-parsing here
    (instead of once in the caller, then again in the worker) avoids paying
    for the parse twice.
    """
    from perseus_cts.models.document import TEIDocument

    site_map = SiteMap(proto_dir)
    try:
        doc = TEIDocument.from_path(xml_path)
        if not doc.metadata.urn:
            return "skipped", None
        if site_map.manifest_path(doc.metadata.urn).exists():
            return "skipped", None
        for refsDecl_id in available_refsDecl_ids(doc):
            scheme = _scheme_slug(refsDecl_id)
            compiler = Chunker(doc, refsDecl_id=refsDecl_id)
            compiler.compile(site_map.chunk_dir(doc.metadata.urn, scheme or None))
        return "ok", None
    except Exception as exc:
        return "failed", f"{xml_path}: {exc}"


def generate_proto_pages(
    proto_dir: Path,
    corpora: list[Corpus],
) -> None:
    """Generate proto-page XML for all corpus documents.

    A document may declare more than one citeStructure scheme (see
    perseus_cts.cts_resolver.available_refsDecl_ids); each is compiled
    separately (see _scheme_slug for the output layout).

    Skips documents whose index.json already exists in proto_dir so the
    function is safe to call on every startup without re-doing prior work.

    Parsing, the skip check, and compilation are all fanned out across
    BUILD_WORKERS processes (see _compile_proto_page) — only the cheap,
    parse-free directory walk (mirroring Corpus.documents()'s file
    discovery) stays single-threaded here.
    """
    work = []
    for corpus in corpora:
        for xml_path in sorted(corpus.root.rglob("*.xml")):
            if xml_path.name == "__cts__.xml":
                continue
            work.append(xml_path)

    generated = skipped = failed = 0
    total = len(work)
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(BUILD_WORKERS) as pool:
        results = pool.imap_unordered(
            partial(_compile_proto_page, proto_dir=proto_dir), work
        )
        for i, (status, error) in enumerate(results, 1):
            if status == "ok":
                generated += 1
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1
                print(f"  FAILED:    {error}")
            if i % 500 == 0 or i == total:
                print(f"  proto-pages: {i}/{total} processed")

    print(f"Proto-pages: {generated} generated, {skipped} skipped, {failed} failed.")


def create_app(test_config=None):
    app = Flask(
        __name__,
        static_url_path=None,
        static_host=None,
        static_folder="static",
        host_matching=False,
        subdomain_matching=False,
        template_folder="templates",
        instance_path=None,
        instance_relative_config=True,
        root_path=None,
    )

    app.config.from_mapping(SECRET_KEY=os.getenv("FLASK_APP_SECRET_KEY", "dev"))

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile("config.py", silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    corpora = _discover_corpora(CORPORA_DIR)

    generate_proto_pages(PROTO_DIR, corpora)

    catalog = CTSCatalog([c.root for c in corpora])

    @app.get("/urn-index.json")
    def urn_index():
        return _build_urn_index(PROTO_DIR), 200, {"Content-Type": "application/json"}

    @app.get("/")
    def index():
        with open(NEWS_MARKDOWN, encoding="utf-8") as f:
            news_markdown = markdown.markdown(f.read())

        return (
            render_template("index.html.jinja", news_markdown=news_markdown),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/collections/")
    def get_collections():
        collections = _build_collections(PROTO_DIR, catalog)
        return (
            render_template("collections.html.jinja", collections=collections),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/research/")
    def get_research():
        with open(RESEARCH_MARKDOWN, encoding="utf-8") as f:
            research_markdown = markdown.markdown(f.read())

        return (
            render_template("research.html.jinja", research_markdown=research_markdown),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    def _redirect_to_first_chunk(corpus, textgroup, work, version, scheme, index_file):
        if not index_file.exists():
            abort(404)

        with open(index_file, encoding="utf-8") as f:
            work_index = json.load(f)

        chunks = work_index.get("chunks")
        if not chunks:
            abort(404)

        passage = chunks[0]["cts_urn"].rsplit(":", 1)[-1]

        route_kwargs = dict(
            corpus=corpus,
            textgroup=textgroup,
            work=work,
            version=version,
            chunk=passage,
        )
        if scheme:
            route_kwargs["scheme"] = scheme
        return redirect(
            url_for("reading_view_scheme" if scheme else "reading_view", **route_kwargs)
        )

    @app.get("/urn:cts:<path:corpus>:<path:textgroup>.<path:work>.<string:version>/")
    def get_first_chunk(corpus, textgroup, work, version):
        index_file = PROTO_DIR / corpus / textgroup / work / version / "index.json"
        return _redirect_to_first_chunk(
            corpus, textgroup, work, version, None, index_file
        )

    @app.get(
        "/urn:cts:<path:corpus>:<path:textgroup>.<path:work>.<string:version>"
        "/<string:scheme>/"
    )
    def get_first_scheme_chunk(corpus, textgroup, work, version, scheme):
        index_file = (
            PROTO_DIR / corpus / textgroup / work / version / scheme / "index.json"
        )
        return _redirect_to_first_chunk(
            corpus, textgroup, work, version, scheme, index_file
        )

    def _render_reading_view(corpus, textgroup, work, version, chunk, scheme=None):
        version_dir = PROTO_DIR / corpus / textgroup / work / version
        data_dir = version_dir / scheme if scheme else version_dir

        index_file = data_dir / "index.json"
        if not index_file.exists():
            abort(404)

        with open(index_file, encoding="utf-8") as f:
            work_index = json.load(f)

        urn = f"urn:cts:{corpus}:{textgroup}.{work}.{version}:{chunk}"
        chunk_entry = next(
            (c for c in work_index["chunks"] if c["cts_urn"] == urn),
            None,
        )
        if chunk_entry is None:
            abort(404)

        chunk_file = data_dir / chunk_entry["file"]
        if not chunk_file.exists():
            abort(404)

        chunk_obj, pub_info = _parse_chunk(chunk_file)
        toc = _toc_from_metadata(
            data_dir / "metadata.json", corpus, textgroup, work, version, scheme
        )

        base_path = f"/urn:cts:{corpus}:{textgroup}.{work}.{version}"
        if scheme:
            base_path += f"/{scheme}"
        prev_url = (
            f"{base_path}:{chunk_obj.prev_urn.rsplit(':', 1)[-1]}"
            if chunk_obj.prev_urn
            else None
        )
        next_url = (
            f"{base_path}:{chunk_obj.next_urn.rsplit(':', 1)[-1]}"
            if chunk_obj.next_urn
            else None
        )
        current_line = _chunk_start_line(chunk_obj.cts_urn)
        scheme_links = _scheme_toggle_links(
            version_dir,
            corpus,
            textgroup,
            work,
            version,
            scheme,
            current_line,
        )

        # e.g. urn:cts:greekLit:tlg0003.tlg001.perseus-grc2
        base_urn = chunk_obj.base_urn
        work_base_urn = base_urn.rsplit(".", 1)[0]  # drop version component

        sibling_data = _build_sibling_data(
            corpus, textgroup, work, version, chunk, current_line, catalog, base_urn
        )

        commentary = links_for_passage(catalog, work_base_urn, chunk)
        commentary_groups = _build_commentary_groups(commentary)
        work_title = _work_title(catalog, work_base_urn, fallback=f"{textgroup}.{work}")

        return (
            render_template(
                "reading.html.jinja",
                catalog_record_uri=f"http://catalog.perseus.org/catalog/{base_urn}",
                chunk=chunk_obj,
                work_title=work_title,
                commentary_groups=commentary_groups,
                commentary_warnings=commentary.warnings,
                citation_uri=f"http://catalog.perseus.org/citations/{chunk_obj.cts_urn}",
                current_urn=urn,
                document_id=f"{textgroup}.{work}.{version}",
                sibling_data=sibling_data,
                language_labels=_LANGUAGE_LABELS,
                morph_url=MORPH_URL,
                next_url=next_url,
                prev_url=prev_url,
                pub_info=pub_info,
                scheme_links=scheme_links,
                text_uri=f"http://catalog.perseus.org/texts/{base_urn}",
                textgroup_urn=f"urn:cts:{corpus}:{textgroup}",
                toc=toc,
                work_uri=f"http://catalog.perseus.org/texts/{work_base_urn}",
                work_urn=f"urn:cts:{corpus}:{textgroup}.{work}",
                xml_src_url=_xml_src_url(corpus, textgroup, work, version),
            ),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get(
        "/urn:cts:<path:corpus>:<path:textgroup>.<path:work>.<string:version>"
        ":<path:chunk>/"
    )
    def reading_view(corpus, textgroup, work, version, chunk):
        return _render_reading_view(corpus, textgroup, work, version, chunk)

    @app.get(
        "/urn:cts:<path:corpus>:<path:textgroup>.<path:work>.<string:version>"
        "/<string:scheme>:<path:chunk>/"
    )
    def reading_view_scheme(corpus, textgroup, work, version, scheme, chunk):
        return _render_reading_view(
            corpus, textgroup, work, version, chunk, scheme=scheme
        )

    return app


# Set just before the freeze worker pool is created (see build()) and read
# by _freeze_one in each forked worker. A Freezer/Flask app can't be pickled
# (Jinja templates, compiled routing regexes, etc.), so it can't be passed
# through Pool.imap_unordered's task queue directly — instead we rely on
# fork's copy-on-write semantics: workers are forked *after* this global is
# set, so each one simply inherits its own copy already in memory.
_ACTIVE_FREEZER = None


def _freeze_one(url_and_last_modified: tuple[str, Any]) -> Path:
    """Render and write one frozen page. Runs in a worker process."""
    url, last_modified = url_and_last_modified
    return _ACTIVE_FREEZER._build_one(url, last_modified)


def build():
    from flask_frozen import Freezer, walk_directory

    global _ACTIVE_FREEZER

    FREEZER_DESTINATION = ROOT_DIR / "build"

    app = create_app()

    app.config.update(
        FREEZER_BASE_URL=os.getenv("FREEZER_BASE_URL", ""),
        FREEZER_DEFAULT_MIMETYPE="text/html",
        FREEZER_DESTINATION=FREEZER_DESTINATION,
        FREEZER_IGNORE_404_NOT_FOUND=True,
        FREEZER_REMOVE_EXTRA_FILES=True,
    )

    freezer = Freezer(app, with_no_argument_rules=True, log_url_for=False)

    def _iter_version_metadata():
        """Yield (corpus, textgroup, work, version, scheme, metadata_path) tuples.

        scheme is None for a document's default citeStructure (metadata.json
        directly in the version directory) and the subdirectory name for any
        additional scheme (see _scheme_slug / SiteMap.chunk_dir)."""
        for metadata_path in PROTO_DIR.glob("**/metadata.json"):
            with metadata_path.open(encoding="utf-8") as f:
                meta = json.load(f)

            document = meta.get("document")
            if not document:
                continue

            base_urn = document.get("base_urn")
            if not base_urn:
                continue

            _urn, _cts, corpus, work_urn = base_urn.split(":")
            textgroup, work, version = work_urn.split(".")
            scheme = (
                None
                if meta.get("refsDecl_id", "CTS") == "CTS"
                else (metadata_path.parent.name)
            )

            yield corpus, textgroup, work, version, scheme, metadata_path

    @freezer.register_generator
    def get_first_chunk():
        for corpus, textgroup, work, version, scheme, _ in _iter_version_metadata():
            if scheme is None:
                yield dict(
                    corpus=corpus, textgroup=textgroup, work=work, version=version
                )

    @freezer.register_generator
    def get_first_scheme_chunk():
        for corpus, textgroup, work, version, scheme, _ in _iter_version_metadata():
            if scheme is not None:
                yield dict(
                    corpus=corpus,
                    textgroup=textgroup,
                    work=work,
                    version=version,
                    scheme=scheme,
                )

    @freezer.register_generator
    def reading_view():
        for (
            corpus,
            textgroup,
            work,
            version,
            scheme,
            metadata_path,
        ) in _iter_version_metadata():
            if scheme is not None:
                continue
            with (metadata_path.parent / "index.json").open(encoding="utf-8") as f:
                chunks = json.load(f).get("chunks")
            for chunk in chunks:
                yield f"/{chunk.get('cts_urn')}/"

    @freezer.register_generator
    def reading_view_scheme():
        for (
            corpus,
            textgroup,
            work,
            version,
            scheme,
            metadata_path,
        ) in _iter_version_metadata():
            if scheme is None:
                continue
            with (metadata_path.parent / "index.json").open(encoding="utf-8") as f:
                chunks = json.load(f).get("chunks")
            for chunk in chunks:
                passage = chunk["cts_urn"].rsplit(":", 1)[-1]
                yield (
                    f"/urn:cts:{corpus}:{textgroup}.{work}.{version}"
                    f"/{scheme}:{passage}/"
                )

    from timeit import default_timer

    start = default_timer()

    # Mirrors flask_frozen.Freezer.freeze_yield() (frozen_flask==1.0.2), but
    # fans the expensive per-URL render+write step (_build_one) out across
    # BUILD_WORKERS processes instead of a single sequential loop. URL
    # enumeration stays single-threaded here — it's cheap (no rendering).
    seen_urls: set[str] = set()
    seen_endpoints: set[str] = set()
    work: list[tuple[str, Any]] = []
    for url, endpoint, last_modified in freezer._generate_all_urls():
        seen_endpoints.add(endpoint)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        work.append((url, last_modified))

    total = len(work)
    built_paths: set[Path] = set()
    _ACTIVE_FREEZER = freezer
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(BUILD_WORKERS) as pool:
        for i, path in enumerate(pool.imap_unordered(_freeze_one, work), 1):
            built_paths.add(path)
            if i % 500 == 0 or i == total:
                print(f"  froze {i}/{total} pages")
    _ACTIVE_FREEZER = None

    freezer._check_endpoints(seen_endpoints)
    if app.config["FREEZER_REMOVE_EXTRA_FILES"]:
        ignore = app.config["FREEZER_DESTINATION_IGNORE"]
        previous_paths = {
            Path(freezer.root / name)
            for name in walk_directory(freezer.root, ignore=ignore)
        }
        for extra_path in previous_paths - built_paths:
            extra_path.unlink()
            with suppress(OSError):
                extra_path.parent.rmdir()

    end = default_timer()

    print(f"MVP took {end - start} seconds to build.")


def main():
    app = create_app()

    app.run(debug=True)

    return app
