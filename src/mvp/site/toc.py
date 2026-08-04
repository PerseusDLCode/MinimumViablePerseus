"""Table-of-contents annotation and citeStructure-scheme toggle links."""

import json
from pathlib import Path

from mvp.site.chunks import _find_chunk_for_line, _load_chunk_unit, _load_index_chunks
from mvp.site.siblings import _reading_view_url


def _annotate_toc(
    entries: list[dict],
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    scheme: str | None = None,
) -> list[dict]:
    """Recursively add endpoint/route_kwargs to routable TOC entries.

    ReferenceParser.toc() returns entries with urn/label/subpassages but no
    routing info. NavigationItem.html.jinja needs endpoint/route_kwargs on
    every entry a reader should be able to click to build hrefs via
    url_for(item.endpoint, **item.route_kwargs).

    An entry compiled with a unit_scheme_map (see CTSResolver.toc) carries
    its own "scheme" key — None for a level that isn't independently
    paginated (e.g. "book"), or the scheme slug to route to otherwise
    (possibly a *different* scheme than the one this TOC file lives under,
    e.g. a "chapter" entry inside the "section" scheme's own TOC). That lets
    every hierarchically-nested paginated level be clickable, not just the
    leaf. An entry compiled without a map (single-scheme documents, and
    schemes like tragedy's card/scene that aren't a depth-truncation of one
    shared tree) has no "scheme" key at all, so it falls back to the old
    behavior: only leaves are linked, always within the current ``scheme``.
    """
    for entry in entries:
        if entry.get("subpassages"):
            _annotate_toc(
                entry["subpassages"], corpus, textgroup, work, version, scheme
            )

        has_own_scheme = "scheme" in entry
        if has_own_scheme:
            target_scheme = entry["scheme"]
            if target_scheme is None:
                continue
        elif entry.get("subpassages"):
            continue
        else:
            target_scheme = scheme

        route_kwargs = {
            "corpus": corpus,
            "textgroup": textgroup,
            "work": work,
            "version": version,
            "chunk": entry["urn"].rsplit(":", 1)[-1],
        }
        if target_scheme:
            route_kwargs["scheme"] = target_scheme
        entry["endpoint"] = "reading_view_scheme" if target_scheme else "reading_view"
        entry["route_kwargs"] = route_kwargs
    return entries


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


def _scheme_dirs(version_dir: Path) -> list[str]:
    """Return the names of alternate citeStructure scheme subdirectories.

    The default scheme's index.json/metadata.json live directly in
    version_dir; any additional scheme (see _scheme_slug) lives in a
    same-named subdirectory alongside its own index.json/metadata.json."""
    if not version_dir.is_dir():
        return []
    return [
        d.name
        for d in sorted(version_dir.iterdir())
        if d.is_dir() and (d / "index.json").exists()
    ]


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
        chunk_unit = _load_chunk_unit(data_dir / "metadata.json") or scheme or "scene"
        label = f"By {chunk_unit.capitalize()}"
        url = _reading_view_url(corpus, textgroup, work, version, passage, scheme)
        links.append({"label": label, "url": url})
    return links
