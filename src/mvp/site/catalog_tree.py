"""Building the corpus -> textgroup -> work -> version catalog tree.

Consumed by /collections/, /collections/search-index.json, and
_build_corpus_manifest (see manifest.py) for a `--mode corpus-only` build.
"""

import json
from collections.abc import Iterator
from pathlib import Path

from perseus_cts.models import Corpus, CTSCatalog

from mvp.site import config
from mvp.site.chunks import _format_editors


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


def _subdirs(path: Path) -> list[Path]:
    """Return the immediate subdirectories of ``path``, sorted by name.

    Returns an empty list when ``path`` is not a directory, letting callers
    iterate without a separate existence check.
    """
    if not path.is_dir():
        return []
    return [child for child in sorted(path.iterdir()) if child.is_dir()]


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
    version_urn = f"{work_urn}.{version_dir.name}"
    cts_version = catalog.version_for(version_urn)
    version = {
        "id": version_dir.name,
        "title": _work_title(catalog, work_urn, fallback=work_dir.name),
        "label": (cts_version.label if cts_version else "") or version_dir.name,
        "language": language,
        "language_label": config._LANGUAGE_LABELS.get(language, language),
        "editors": _format_editors(document.get("editors", [])),
        "first_chunk_kwargs": {
            "corpus": corpus,
            "textgroup": textgroup_dir.name,
            "work": work_dir.name,
            "version": version_dir.name,
            "chunk": first_passage,
        },
    }
    return version, document


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
                    work_urn = f"urn:cts:{corpus}:{textgroup_dir.name}.{work_dir.name}"
                    works.append(
                        {
                            "id": work_dir.name,
                            "title": _work_title(
                                catalog, work_urn, fallback=work_dir.name
                            ),
                            "versions": versions,
                        }
                    )

            if works:
                textgroups.append(
                    {"id": textgroup_dir.name, "author": author, "works": works}
                )

        if textgroups:
            collections.append(
                {
                    "id": corpus,
                    "label": config._CORPUS_LABELS.get(corpus, corpus),
                    "textgroups": textgroups,
                }
            )

    return collections


def _merge_collections(all_collections: list[list[dict]]) -> list[dict]:
    """Merge N _build_collections()-shaped lists into one collections tree.

    A single CTS namespace can be contributed to by more than one source:
    e.g. First1KGreek's documents declare urn:cts:greekLit:... (it's
    supplementary Greek literature from a different repo than
    canonical-greekLit, not a namespace of its own — see the
    hebrewLit/First1KGreek note in build-corpus.yml), and a single corpus
    repo can itself contain a stray document mistagged under a different
    namespace than the rest of its content. Either way, two contributions
    to the same corpus id must combine into one collections entry — not
    sit side by side as visually duplicate entries (e.g. two "Greek"
    sections) or silently overwrite each other. Matches by id at every
    level (corpus, textgroup, work); a version id collision (least likely,
    hardest to define "merge" for) is resolved last-write-wins.
    """
    corpora: dict[str, dict] = {}
    for collections in all_collections:
        for corpus in collections:
            c = corpora.setdefault(
                corpus["id"],
                {"id": corpus["id"], "label": corpus["label"], "textgroups": {}},
            )
            for tg in corpus["textgroups"]:
                t = c["textgroups"].setdefault(
                    tg["id"], {"id": tg["id"], "author": tg["author"], "works": {}}
                )
                for work in tg["works"]:
                    w = t["works"].setdefault(
                        work["id"],
                        {"id": work["id"], "title": work["title"], "versions": {}},
                    )
                    for version in work["versions"]:
                        w["versions"][version["id"]] = version

    collections = []
    for corpus in corpora.values():
        textgroups = []
        for tg in corpus["textgroups"].values():
            works = [
                {
                    "id": w["id"],
                    "title": w["title"],
                    "versions": list(w["versions"].values()),
                }
                for w in tg["works"].values()
            ]
            textgroups.append({"id": tg["id"], "author": tg["author"], "works": works})
        collections.append(
            {"id": corpus["id"], "label": corpus["label"], "textgroups": textgroups}
        )
    return collections


def _flatten_search_index(collections: list[dict]) -> list[dict]:
    """Flatten a collections tree into a list of typeahead search entries.

    Each entry pairs a version's display fields with the href a click
    should land on. Requires every version to already carry a resolved
    ``href`` (as `collections_override` does, and as the live `/collections/
    `route arranges via url_for before calling this) rather than resolving
    urls itself, so this stays agnostic to whether it's called inside a
    request context.
    """
    entries = []
    for corpus in collections:
        for textgroup in corpus["textgroups"]:
            for work in textgroup["works"]:
                for version in work["versions"]:
                    entries.append(
                        {
                            "title": version["title"],
                            "author": textgroup["author"] or textgroup["id"],
                            "corpus": corpus["label"],
                            "language": version["language_label"],
                            "editors": version.get("editors", ""),
                            "url": version["href"],
                        }
                    )
    return entries


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


def _xml_src_url(corpus: str, textgroup: str, work: str, version: str) -> str:
    repo = config._CORPUS_REPO.get(corpus, f"canonical-{corpus}")
    filename = f"{textgroup}.{work}.{version}.xml"
    return (
        f"https://raw.githubusercontent.com/PerseusDL/{repo}/master"
        f"/data/{textgroup}/{work}/{filename}"
    )
