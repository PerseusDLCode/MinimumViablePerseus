import json
import os

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import markdown

from flask import Flask, abort, render_template, redirect, url_for
from lxml import etree

import citation_resolution

from citation_resolution.tei_cts_linker import Gazetteer, TEILinker
from kodon_py.tei_parser import TEIParser, TEIParserError, inject_tokens
from perseus_cts.chunker import Chunker
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

_CORPUS_LABELS = {
    "greekLit": "Greek",
    "hebrewLit": "Hebrew",
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


@dataclass
class _Chunk:
    cts_urn: str
    prev_urn: str | None
    next_urn: str | None
    title: str
    base_urn: str
    language: str
    elements: list[Any]


def _annotate_toc(
    entries: list[dict],
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
) -> list[dict]:
    """Recursively add route_kwargs to leaf TOC entries.

    ReferenceParser.toc() returns entries with urn/label/subpassages but no
    route_kwargs.  NavigationItem.html.jinja needs route_kwargs on leaf nodes
    to build hrefs via url_for('reading_view', ...).
    """
    for entry in entries:
        if entry.get("subpassages"):
            _annotate_toc(entry["subpassages"], corpus, textgroup, work, version)
        else:
            entry["route_kwargs"] = {
                "corpus": corpus,
                "textgroup": textgroup,
                "work": work,
                "version": version,
                "chunk": entry["urn"].rsplit(":", 1)[-1],
            }
    return entries


def _build_collections(proto_dir: Path) -> list[dict]:
    """Build the nested corpus → textgroup → work → version catalog tree.

    Each level is included only when it has at least one populated child, so
    empty directories never surface in the catalog.
    """
    collections = []

    for corpus_dir in _subdirs(proto_dir):
        corpus = corpus_dir.name
        textgroups = []

        for textgroup_dir in _subdirs(corpus_dir):
            author = textgroup_dir.name
            works = []

            for work_dir in _subdirs(textgroup_dir):
                versions = []

                for version_dir in _subdirs(work_dir):
                    entry = _version_entry(corpus, textgroup_dir, work_dir, version_dir)
                    if entry is None:
                        continue
                    version, document = entry
                    versions.append(version)
                    # The textgroup author is the same across versions; take
                    # it from whichever version supplies one.
                    author = document.get("author", textgroup_dir.name)

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


def _build_sibling_data(
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    chunk: str,
    chunk_index: int | None,
    catalog: CTSCatalog,
    base_urn: str,
) -> dict:
    """Build sibling edition/translation chunk data using catalog + chunk offset.

    For each sibling version, loads its index.json and finds the corresponding
    chunk by:
      Strategy 1 — exact passage reference match
      Strategy 2 — positional (offset) fallback, clamped to bounds

    Returns dict with keys:
      current_version: CTSVersion | None
      edition_chunks: list[(CTSVersion, _Chunk | None)]
      translation_chunks: list[(CTSVersion, _Chunk | None)]
    """
    work_urn = base_urn.rsplit(".", 1)[0]

    def _lookup(sib: CTSVersion) -> tuple[CTSVersion, _Chunk | None]:
        sib_id = sib.urn.split(":")[3].split(".")[-1]
        if sib_id == version:
            return sib, None

        index_file = PROTO_DIR / corpus / textgroup / work / sib_id / "index.json"
        if not index_file.exists():
            return sib, None

        with open(index_file, encoding="utf-8") as f:
            sib_chunks = json.load(f).get("chunks", [])
        if not sib_chunks:
            return sib, None

        # Strategy 1: exact passage-reference match.
        entry = next(
            (c for c in sib_chunks if c["cts_urn"].endswith(f":{chunk}")),
            None,
        )
        # Strategy 2: positional fallback, clamped to the sibling's bounds.
        if entry is None and chunk_index is not None:
            entry = sib_chunks[min(chunk_index, len(sib_chunks) - 1)]
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
            _lookup(sib) for sib in catalog.editions_of(work_urn) if sib.urn != base_urn
        ],
        "translation_chunks": [
            _lookup(sib)
            for sib in catalog.translations_of(work_urn)
            if sib.urn != base_urn
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


def _do_prune_toc(entries: list[dict], max_depth: int) -> list[dict]:
    """Return a copy of entries with every node at or below max_depth removed."""
    return [
        {**e, "subpassages": _do_prune_toc(e.get("subpassages", []), max_depth)}
        for e in entries
        if e["depth"] < max_depth
    ]


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


def _max_toc_depth(entries: list[dict]) -> int:
    """Return the greatest ``depth`` value anywhere in the TOC tree, or -1."""
    depth = -1
    for entry in entries:
        depth = max(depth, entry["depth"])
        if entry.get("subpassages"):
            depth = max(depth, _max_toc_depth(entry["subpassages"]))
    return depth


def _parse_chunk(path: Path) -> tuple[_Chunk, dict[str, Any]]:
    """Parse a protopage XML file into a (_Chunk, pub_info) tuple.

    Document-level metadata (title, author, language, etc.) is read from the
    sibling metadata.json written by Chunker.compile().
    """
    tree = etree.parse(path)

    # Resolve citations inline.
    linker = TEILinker(kb=Gazetteer.from_json(GAZETTEER_PATH), decompose=True)
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
        "editors": document.get("editors", []),
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


def _prune_toc_leaves(entries: list[dict]) -> list[dict]:
    """Remove the deepest citation level, keeping only the penultimate level as leaves."""
    if not entries:
        return entries

    max_depth = _max_toc_depth(entries)
    if max_depth <= 0:
        return entries

    return _do_prune_toc(entries, max_depth)


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
) -> dict:
    """Load and annotate the TOC from a metadata.json file.

    Returns a dict shaped as {"table_of_contents": [...]}, matching
    what reading.html.jinja expects from toc.get("table_of_contents", []).
    """
    if not metadata_path.exists():
        return {"table_of_contents": []}

    with open(metadata_path, encoding="utf-8") as f:
        toc_entries = json.load(f).get("toc", [])

    toc_entries = _prune_toc_leaves(toc_entries)
    _annotate_toc(toc_entries, corpus, textgroup, work, version)
    return {"table_of_contents": toc_entries}


def _version_entry(
    corpus: str,
    textgroup_dir: Path,
    work_dir: Path,
    version_dir: Path,
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
    version = {
        "id": version_dir.name,
        "title": document.get("title", version_dir.name),
        "language": language,
        "language_label": _LANGUAGE_LABELS.get(language, language),
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


def generate_proto_pages(
    proto_dir: Path,
    corpora: list[Corpus],
) -> None:
    """Generate proto-page XML for all corpus documents.

    Skips documents whose index.json already exists in proto_dir so the
    function is safe to call on every startup without re-doing prior work.
    """
    site_map = SiteMap(proto_dir)
    generated = skipped = failed = 0

    for corpus in corpora:
        for doc in corpus.documents():
            if not doc.metadata.urn:
                continue
            if site_map.manifest_path(doc.metadata.urn).exists():
                skipped += 1
                continue
            try:
                compiler = Chunker(doc)
                compiler.compile(site_map.chunk_dir(doc.metadata.urn))
                generated += 1
            except Exception as exc:
                failed += 1
                print(f"  FAILED:    {doc.path.name}: {exc}")

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
        collections = _build_collections(PROTO_DIR)
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

    @app.get("/urn:cts:<path:corpus>:<path:textgroup>.<path:work>.<path:version>/")
    def get_first_chunk(corpus, textgroup, work, version):
        index_file = PROTO_DIR / corpus / textgroup / work / version / "index.json"
        if not index_file.exists():
            abort(404)

        with open(index_file, encoding="utf-8") as f:
            work_index = json.load(f)

        chunks = work_index.get("chunks")
        if not chunks:
            abort(404)

        try:
            _urn, _cts, corpus, work_urn, chunk = chunks[0]["cts_urn"].split(":", 4)
            textgroup, work, version = work_urn.split(".")
        except (KeyError, ValueError):
            abort(404)

        return redirect(
            url_for(
                "reading_view",
                corpus=corpus,
                textgroup=textgroup,
                work=work,
                version=version,
                chunk=chunk,
            )
        )

    @app.get(
        "/urn:cts:<path:corpus>:<path:textgroup>.<path:work>.<path:version>:<path:chunk>/"
    )
    def reading_view(corpus, textgroup, work, version, chunk):
        index_file = PROTO_DIR / corpus / textgroup / work / version / "index.json"
        if not index_file.exists():
            abort(404)

        with open(index_file, encoding="utf-8") as f:
            work_index = json.load(f)

        urn = f"urn:cts:{corpus}:{textgroup}.{work}.{version}:{chunk}"
        chunk_entry, chunk_index = next(
            ((c, i) for i, c in enumerate(work_index["chunks"]) if c["cts_urn"] == urn),
            (None, None),
        )
        if chunk_entry is None:
            abort(404)

        chunk_file = (
            PROTO_DIR / corpus / textgroup / work / version / chunk_entry["file"]
        )
        if not chunk_file.exists():
            abort(404)

        chunk_obj, pub_info = _parse_chunk(chunk_file)
        metadata_file = (
            PROTO_DIR / corpus / textgroup / work / version / "metadata.json"
        )
        toc = _toc_from_metadata(metadata_file, corpus, textgroup, work, version)

        base_path = f"/{corpus}/{textgroup}/{work}/{version}"
        prev_url = (
            f"{base_path}/{chunk_obj.prev_urn.rsplit(':', 1)[-1]}"
            if chunk_obj.prev_urn
            else None
        )
        next_url = (
            f"{base_path}/{chunk_obj.next_urn.rsplit(':', 1)[-1]}"
            if chunk_obj.next_urn
            else None
        )

        # e.g. urn:cts:greekLit:tlg0003.tlg001.perseus-grc2
        base_urn = chunk_obj.base_urn
        work_base_urn = base_urn.rsplit(".", 1)[0]  # drop version component

        sibling_data = _build_sibling_data(
            corpus, textgroup, work, version, chunk, chunk_index, catalog, base_urn
        )

        return (
            render_template(
                "reading.html.jinja",
                catalog_record_uri=f"http://data.perseus.org/catalog/{base_urn}",
                chunk=chunk_obj,
                citation_uri=f"http://data.perseus.org/citations/{chunk_obj.cts_urn}",
                current_urn=urn,
                document_id=f"{textgroup}.{work}.{version}",
                sibling_data=sibling_data,
                language_labels=_LANGUAGE_LABELS,
                morph_url=MORPH_URL,
                next_url=next_url,
                prev_url=prev_url,
                pub_info=pub_info,
                text_uri=f"http://data.perseus.org/texts/{base_urn}",
                textgroup_urn=f"urn:cts:{corpus}:{textgroup}",
                toc=toc,
                work_uri=f"http://data.perseus.org/texts/{work_base_urn}",
                work_urn=f"urn:cts:{corpus}:{textgroup}.{work}",
                xml_src_url=_xml_src_url(corpus, textgroup, work, version),
            ),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    return app


def build():
    from flask_frozen import Freezer

    FREEZER_DESTINATION = ROOT_DIR / "build"

    app = create_app()

    app.config.update(
        FREEZER_BASE_URL=os.getenv("FREEZER_BASE_URL", ""),
        FREEZER_DEFAULT_MIMETYPE="text/html",
        FREEZER_DESTINATION=FREEZER_DESTINATION,
        FREEZER_IGNORE_404_NOT_FOUND=True,
    )

    freezer = Freezer(app)

    @freezer.register_generator
    def get_first_chunk():
        for metadata_path in PROTO_DIR.glob("**/metadata.json"):
            with metadata_path.open(encoding="utf-8") as f:
                document = json.load(f).get("document")

            if not document:
                continue

            base_urn = document.get("base_urn")
            if not base_urn:
                continue

            _urn, _cts, corpus, work_urn = base_urn.split(":")
            textgroup, work, version = work_urn.split(".")

            yield dict(corpus=corpus, textgroup=textgroup, work=work, version=version)

    freezer.freeze()


def main():
    app = create_app()

    app.run(debug=True)

    return app
