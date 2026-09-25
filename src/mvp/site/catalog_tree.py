"""Building the corpus -> textgroup -> work -> version catalog tree.

Consumed by /collections/, /collections/search-index.json, and
_build_corpus_manifest (see manifest.py) for a `--mode corpus-only` build.
"""

import json
import re
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
    experimental: frozenset[str] = frozenset(),
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
    kind = _version_kind(corpus, work_urn, version_dir.name, document, catalog)
    about = _about_work_urn(document, cts_version) if kind == "commentary" else None
    version = {
        "id": version_dir.name,
        "title": _work_title(catalog, work_urn, fallback=work_dir.name),
        "label": (cts_version.label if cts_version else "") or version_dir.name,
        "language": language,
        "language_label": config._LANGUAGE_LABELS.get(language, language),
        "editors": _format_editors(document.get("editors", [])),
        "kind": kind,
        "experimental": f"{textgroup_dir.name}.{work_dir.name}.{version_dir.name}"
        in experimental,
        "about": about,
        "commentator": _commentator(
            catalog, work_urn, about, document.get("author", "")
        ),
        "first_chunk_kwargs": {
            "corpus": corpus,
            "textgroup": textgroup_dir.name,
            "work": work_dir.name,
            "version": version_dir.name,
            "chunk": first_passage,
        },
    }
    return version, document


_VERSION_KINDS = ("edition", "translation", "commentary")

# A version id's trailing language token, e.g. "grc" in "1st1K-grc1" or
# "eng" in "perseus-eng2".
_VERSION_ID_LANG_RE = re.compile(r"-([a-z]{3})\d*[a-z]?$")


def _original_language(corpus: str, work_urn: str, catalog: CTSCatalog) -> str:
    """Return the language a work was originally written in.

    Taken from the work's catalog editions (in CTS, an <ti:edition> is by
    definition in the original language), falling back to the corpus's
    default language when the catalog has no editions for the work.
    """
    work = catalog.work_for(work_urn)
    if work is not None:
        for v in work.versions:
            if v.version_type == "edition" and v.lang:
                return v.lang
    return config._CORPUS_LANGUAGES.get(corpus, "")


def _version_kind(
    corpus: str,
    work_urn: str,
    version_id: str,
    document: dict,
    catalog: CTSCatalog,
) -> str:
    """Classify a version as an "edition", "translation", or "commentary".

    Trusts the catalog's own <ti:edition>/<ti:translation>/<ti:commentary>
    element when there is one. Otherwise a version with a <ti:about> target
    is a commentary, and the rest are editions when in the work's original
    language and translations when not. For that comparison the version id's
    language token ("1st1K-grc1") is preferred over metadata.json's
    language: the latter comes from the TEI header, which is often wrong or
    nonstandard (e.g. First1KGreek editions tagged "lat" for their Latin
    front matter, or "greek" instead of "grc").
    """
    cts_version = catalog.version_for(f"{work_urn}.{version_id}")
    if cts_version is not None and cts_version.version_type in _VERSION_KINDS:
        return cts_version.version_type
    if document.get("about"):
        return "commentary"

    match = _VERSION_ID_LANG_RE.search(version_id)
    if match and match.group(1) in config._LANGUAGE_LABELS:
        language = match.group(1)
    else:
        language = document.get("language", "")
    original = _original_language(corpus, work_urn, catalog)
    if not original or language == original:
        return "edition"
    return "translation"


def _about_work_urn(document: dict, cts_version) -> str | None:
    """Return the work-level urn a commentary comments on, if it names one.

    Strips any passage (":2") or version (".perseus-grc2") component from
    the <ti:about> urn, so a commentary on part of a work is still listed
    with that work. Returns None when about names only a textgroup.
    """
    about = (cts_version.about if cts_version else None) or document.get("about")
    if not about or not about.startswith("urn:cts:"):
        return None
    parts = about.split(":")
    if len(parts) < 4:
        return None
    work_parts = parts[3].split(".")
    if len(work_parts) < 2:
        return None
    return f"urn:cts:{parts[2]}:{work_parts[0]}.{work_parts[1]}"


def _commentator(
    catalog: CTSCatalog, work_urn: str, about: str | None, fallback: str
) -> str:
    """Return who wrote a standalone commentary, or "" if it isn't one.

    A commentary filed under its own textgroup (e.g. Jebb's on Sophocles,
    under viaf2603144 rather than Sophocles' tlg0011) is authored by that
    textgroup, and its TEI usually lists no editors, so without this it
    would be listed with no name at all. One filed alongside the work it
    annotates (e.g. an index to Iatrica) shares that work's textgroup,
    whose name is the ancient author's, not the commentator's -- so it
    gets none here and relies on its editors instead.
    """
    if about is None:
        return ""
    textgroup_urn = work_urn.rsplit(".", 1)[0]
    if about.rsplit(".", 1)[0] == textgroup_urn:
        return ""
    return _group_name(catalog, textgroup_urn, fallback)


def _attach_commentaries(collections: list[dict]) -> None:
    """Cross-list each commentary under the work it comments on, in place.

    A commentary is a work of its own in CTS (e.g. a commentary on Cicero's
    letters lives under its commentator's textgroup, not Cicero's), so it
    stays in its own work's ``versions`` and is additionally referenced from
    the commented-on work's ``commentaries`` list. The same dict is shared
    by both, so an href resolved on one (see get_collections_search_index)
    shows up on the other. ``commentaries`` is derived data: it's rebuilt
    from scratch here, and _merge_collections ignores it.
    """
    works_by_urn: dict[str, dict] = {}
    for corpus in collections:
        for tg in corpus["textgroups"]:
            for work in tg["works"]:
                work["commentaries"] = []
                works_by_urn[f"urn:cts:{corpus['id']}:{tg['id']}.{work['id']}"] = work

    for work in works_by_urn.values():
        for version in work["versions"]:
            target = works_by_urn.get(version.get("about") or "")
            if target is not None and target is not work:
                target["commentaries"].append(version)


_VERSION_NUMBER_RE = re.compile(r"^(.*?)(\d+)$")


def _version_family(version_id: str) -> tuple[str, int]:
    """Split a version id into an (id-family, number) pair.

    e.g. "perseus-grc2" -> ("perseus-grc", 2). An id with no trailing digits
    is its own family with number 0, so it's trivially preferred among
    itself rather than crashing or being silently excluded.
    """
    match = _VERSION_NUMBER_RE.match(version_id)
    if match:
        return match.group(1), int(match.group(2))
    return version_id, 0


def _mark_preferred_versions(work_urn: str, versions: list[dict]) -> None:
    """Flag each version dict in-place with a ``preferred`` bool.

    Within each id family (e.g. all "perseus-grc*" ids for this work), the
    highest-numbered version is preferred by default -- perseus-grc2 over
    perseus-grc1 -- so /collections can headline the current edition of
    each language/tradition and tuck superseded ones behind a disclosure.
    Families are split by ``kind`` too, so e.g. a "1st1K-grc2" commentary
    can't outrank the "1st1K-grc1" edition it's filed alongside.
    An experimental version (see _experimental_version_ids) is never
    preferred over a curated one: it's only preferred when its kind has no
    curated version at all. `config._VERSION_OVERRIDES` (keyed by version
    URN) can force a specific version to be preferred instead, for cases
    where the highest number isn't actually the best edition.
    """
    overrides = config._VERSION_OVERRIDES
    forced = {
        v["id"]
        for v in versions
        if overrides.get(f"{work_urn}.{v['id']}", {}).get("preferred") is True
    }

    if forced:
        preferred_ids = forced
    else:
        curated_kinds = {
            v.get("kind", "") for v in versions if not v.get("experimental")
        }
        best_by_family: dict[tuple[str, str], tuple[int, str]] = {}
        for v in versions:
            if v.get("experimental") and v.get("kind", "") in curated_kinds:
                continue
            id_family, number = _version_family(v["id"])
            family = (v.get("kind", ""), id_family)
            current = best_by_family.get(family)
            if current is None or number > current[0]:
                best_by_family[family] = (number, v["id"])
        preferred_ids = {vid for _, vid in best_by_family.values()}

    for v in versions:
        v["preferred"] = v["id"] in preferred_ids


def _build_collections(
    proto_dir: Path,
    catalog: CTSCatalog,
    experimental: frozenset[str] = frozenset(),
) -> list[dict]:
    """Build the nested corpus → textgroup → work → version catalog tree.

    Each level is included only when it has at least one populated child, so
    empty directories never surface in the catalog. ``experimental`` (see
    _experimental_version_ids) flags each version dict's ``experimental``.
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
                        corpus,
                        textgroup_dir,
                        work_dir,
                        version_dir,
                        catalog,
                        experimental,
                    )
                    if entry is None:
                        continue
                    version, _document = entry
                    versions.append(version)

                if versions:
                    work_urn = f"urn:cts:{corpus}:{textgroup_dir.name}.{work_dir.name}"
                    _mark_preferred_versions(work_urn, versions)
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

    _attach_commentaries(collections)
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
            works = []
            for w in tg["works"].values():
                versions = list(w["versions"].values())
                work_urn = f"urn:cts:{corpus['id']}:{tg['id']}.{w['id']}"
                # Recomputed here rather than trusted from each source's own
                # _build_collections call: merging can combine version sets
                # from more than one source for the same work (see the
                # docstring above), so a version's "preferred" family-mate
                # may not have been in the same source's list yet.
                _mark_preferred_versions(work_urn, versions)
                works.append(
                    {"id": w["id"], "title": w["title"], "versions": versions}
                )
            textgroups.append({"id": tg["id"], "author": tg["author"], "works": works})
        collections.append(
            {"id": corpus["id"], "label": corpus["label"], "textgroups": textgroups}
        )
    _attach_commentaries(collections)
    return collections


_KIND_HEADINGS = {
    "edition": "Editions",
    "translation": "Translations",
    "commentary": "Commentaries",
}


def _version_sort_key(version: dict) -> tuple[bool, bool, str, str]:
    """Sort experimental versions last and perseus-* versions first, then
    by label and id."""
    return (
        bool(version.get("experimental")),
        not version["id"].startswith("perseus-"),
        version["label"].casefold(),
        version["id"],
    )


def _collections_display_tree(collections: list[dict]) -> list[dict]:
    """Sort a collections tree and split each work's versions by kind.

    /collections nests corpus -> author -> work -> kind -> version. Corpora,
    authors, and works are sorted by display name; each work gets a
    ``kinds`` list of ``{"kind", "heading", "versions"}`` in edition,
    translation, commentary order, omitting empty kinds, with perseus-*
    versions first and experimental ones last. A work's commentaries include those cross-listed from
    other works (see _attach_commentaries).

    Returns new dicts rather than sorting in place: a global build's
    collections_override is shared across requests.
    """
    display = []
    for corpus in sorted(collections, key=lambda c: (c["label"].casefold(), c["id"])):
        textgroups = []
        for tg in sorted(
            corpus["textgroups"],
            key=lambda t: ((t["author"] or t["id"]).casefold(), t["id"]),
        ):
            works = []
            for work in sorted(
                tg["works"], key=lambda w: (w["title"].casefold(), w["id"])
            ):
                by_kind: dict[str, list[dict]] = {kind: [] for kind in _VERSION_KINDS}
                for version in work["versions"]:
                    by_kind[version["kind"]].append(version)
                by_kind["commentary"] += work.get("commentaries") or []
                kinds = [
                    {
                        "kind": kind,
                        "heading": _KIND_HEADINGS[kind],
                        "versions": sorted(versions, key=_version_sort_key),
                    }
                    for kind, versions in by_kind.items()
                    if versions
                ]
                works.append({**work, "kinds": kinds})
            textgroups.append({**tg, "works": works})
        display.append({**corpus, "textgroups": textgroups})
    return display


def _version_status(version: dict) -> str:
    """Return a version's /collections "status" facet value."""
    return "experimental" if version.get("experimental") else "curated"


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
                            # Facet values, matching the data-* attributes
                            # /collections filters its tree on.
                            "corpus_id": corpus["id"],
                            "lang": version["language"],
                            "kind": version["kind"],
                            "status": _version_status(version),
                            "editors": version.get("editors", ""),
                            "url": version["href"],
                        }
                    )
    return entries


def _build_urn_index(
    proto_dir: Path, catalog: CTSCatalog
) -> dict[str, list[dict]]:
    """Map work-level CTS URNs to the list of versions available for that work.

    e.g. "urn:cts:latinLit:phi0917.phi001" -> [
        {"id": "perseus-lat1", "label": "...", "language": "lat",
         "language_label": "Latin",
         "route_kwargs": {"corpus": "latinLit", "textgroup": "phi0917",
                           "work": "phi001", "version": "perseus-lat1"}},
        {"id": "perseus-eng2", ..., "language": "eng", ...},
    ]
    Every version this work has gets an entry (not just one per language),
    so a caller can offer a reader every edition that resolves, e.g. as a
    popover menu, rather than silently picking one.
    """
    index: dict[str, list[dict]] = {}

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
        version_urn = f"{work_urn}.{ver_dir.name}"
        cts_version = catalog.version_for(version_urn)
        version = {
            "id": ver_dir.name,
            "label": (cts_version.label if cts_version else "") or ver_dir.name,
            "language": language,
            "language_label": config._LANGUAGE_LABELS.get(language, language),
            "route_kwargs": {
                "corpus": corpus,
                "textgroup": tg_dir.name,
                "work": work_dir.name,
                "version": ver_dir.name,
            },
        }
        index.setdefault(work_urn, []).append(version)

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


def _version_id(urn: str) -> str:
    """Return a version URN's namespace-free ``textgroup.work.version`` part.

    e.g. "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2" ->
    "tlg0012.tlg001.perseus-grc2". Tolerates a trailing passage.
    """
    parts = urn.split(":")
    return parts[3] if len(parts) > 3 else urn


def _curated_source(urn: str) -> str | None:
    """Return the badge label for a Perseus or First1KGreek version, else None.

    Takes a version URN, a ``textgroup.work.version`` id, or a bare version
    id like "perseus-grc2" (see config._CURATED_SOURCES).
    """
    version = _version_id(urn).split(".")[-1]
    for prefix, label in config._CURATED_SOURCES.items():
        if version.startswith(prefix):
            return label
    return None


def _experimental_version_ids(
    corpora_dir: Path, catalog: CTSCatalog
) -> frozenset[str]:
    """Return the ``textgroup.work.version`` ids contributed by any repo in
    config._EXPERIMENTAL_SOURCES.

    Keyed without the CTS namespace, since these repos declare URNs across
    several (see config._EXPERIMENTAL_SOURCES). Two sources, since neither
    is complete on its own: the catalog's versions whose __cts__.xml lives
    in one of these repos, plus the repos' own document filenames
    (``textgroup.work.version.xml``), which covers documents with no
    __cts__.xml entry at all.
    """
    roots = [
        corpora_dir / source
        for source in config._EXPERIMENTAL_SOURCES
        if (corpora_dir / source).is_dir()
    ]
    if not roots:
        return frozenset()

    ids = {
        _version_id(urn)
        for urn, version in catalog.versions.items()
        if version.source_path is not None
        and any(version.source_path.is_relative_to(root) for root in roots)
    }
    for root in roots:
        ids.update(
            path.stem for path in root.rglob("*.xml") if path.name != "__cts__.xml"
        )
    return frozenset(ids)


def _xml_src_url(corpus: str, textgroup: str, work: str, version: str) -> str:
    """Deprecated. This lookup will often fail (e.g., for First1KGreek). Should we
    instead have a static page of source repositories with instructions for finding
    specific works therein?
    """
    repo = config._CORPUS_REPO.get(corpus, f"canonical-{corpus}")
    filename = f"{textgroup}.{work}.{version}.xml"
    return (
        f"https://raw.githubusercontent.com/PerseusDLCode/{repo}/master"
        f"/data/{textgroup}/{work}/{filename}"
    )
