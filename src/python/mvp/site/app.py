import json
import os

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import markdown

from flask import Flask, abort, render_template, url_for
from lxml import etree
from markupsafe import Markup

from citation_resolution.tei_cts_linker import Gazetteer, TEILinker
from perseus_cts.chunker import Chunker
from perseus_cts.cts_resolver import ConfigurationError
from perseus_cts.models import Corpus
from mvp.site_map import SiteMap
from mvp.site.tei_parser import TEIParser, TEIParserError, inject_tokens


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
_DEFAULT_GAZETTEER = (
    ROOT_DIR.parent / "citation-resolution" / "kb" / "data" / "gazetteer.json"
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
    "latinLit": "Latin",
}

_CORPUS_REPO = {
    "greekLit": "canonical-greekLit",
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
class _Section:
    cts_urn: str
    paragraphs: list[Markup]


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


def _build_urn_index(proto_dir: Path) -> dict[str, dict[str, str]]:
    """Map work-level CTS URNs to a language→URL-prefix dict.

    e.g. "urn:cts:latinLit:phi0917.phi001" -> {"lat": "/latinLit/phi0917/phi001/perseus-lat1/",
                                                "eng": "/latinLit/phi0917/phi001/perseus-eng2/"}
    For each language, the first version found (sorted) wins.
    The JS appends the passage and a trailing slash to the chosen prefix.
    """
    index: dict[str, dict[str, str]] = {}
    if not proto_dir.is_dir():
        return index

    for corpus_dir in sorted(proto_dir.iterdir()):
        if not corpus_dir.is_dir():
            continue
        corpus = corpus_dir.name
        for tg_dir in sorted(corpus_dir.iterdir()):
            if not tg_dir.is_dir():
                continue
            for work_dir in sorted(tg_dir.iterdir()):
                if not work_dir.is_dir():
                    continue
                for ver_dir in sorted(work_dir.iterdir()):
                    if not ver_dir.is_dir():
                        continue
                    meta_file = ver_dir / "metadata.json"
                    if not meta_file.exists():
                        continue
                    with open(meta_file) as f:
                        lang = json.load(f).get("document", {}).get("language", "")
                    if not lang:
                        continue
                    work_urn = f"urn:cts:{corpus}:{tg_dir.name}.{work_dir.name}"
                    url_prefix = (
                        f"/{corpus}/{tg_dir.name}/{work_dir.name}/{ver_dir.name}/"
                    )
                    index.setdefault(work_urn, {}).setdefault(lang, url_prefix)

    return index


def _build_collections(proto_dir: Path) -> list[dict]:
    if not proto_dir.is_dir():
        return []

    collections = []

    for corpus_dir in sorted(proto_dir.iterdir()):
        if not corpus_dir.is_dir():
            continue
        corpus = corpus_dir.name
        textgroups = []

        for tg_dir in sorted(corpus_dir.iterdir()):
            if not tg_dir.is_dir():
                continue
            tg_author = tg_dir.name
            works = []

            for work_dir in sorted(tg_dir.iterdir()):
                if not work_dir.is_dir():
                    continue
                versions = []

                for ver_dir in sorted(work_dir.iterdir()):
                    if not ver_dir.is_dir():
                        continue
                    index_file = ver_dir / "index.json"
                    metadata_file = ver_dir / "metadata.json"
                    if not index_file.exists() or not metadata_file.exists():
                        continue
                    with open(index_file) as f:
                        idx = json.load(f)
                    with open(metadata_file) as f:
                        doc_meta = json.load(f).get("document", {})
                    chunks = idx.get("chunks", [])
                    if not chunks:
                        continue
                    first_passage = chunks[0]["cts_urn"].rsplit(":", 1)[-1]
                    lang = doc_meta.get("language", "")
                    versions.append(
                        {
                            "id": ver_dir.name,
                            "title": doc_meta.get("title", ver_dir.name),
                            "language": lang,
                            "language_label": _LANGUAGE_LABELS.get(lang, lang),
                            "first_chunk_kwargs": dict(
                                corpus=corpus,
                                textgroup=tg_dir.name,
                                work=work_dir.name,
                                version=ver_dir.name,
                                chunk=first_passage,
                            ),
                        }
                    )
                    tg_author = doc_meta.get("author", tg_dir.name)

                if versions:
                    works.append(
                        {
                            "id": work_dir.name,
                            "versions": versions,
                        }
                    )

            if works:
                textgroups.append(
                    {
                        "id": tg_dir.name,
                        "author": tg_author,
                        "works": works,
                    }
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


def _discover_corpora(corpora_dir: Path) -> list[Corpus]:
    """Return a Corpus for each subdirectory of corpora_dir that exists."""
    corpora = []
    if not corpora_dir.is_dir():
        return corpora
    for subdir in sorted(corpora_dir.iterdir()):
        if not subdir.is_dir():
            continue
        data = subdir / "data"
        root = data if data.is_dir() else subdir
        try:
            corpora.append(Corpus(root))
        except FileNotFoundError:
            pass
    return corpora


def _parse_chunk(path: Path) -> tuple[_Chunk, dict[str, Any]]:
    """Parse a protopage XML file into a (_Chunk, pub_info) tuple.

    Document-level metadata (title, author, language, etc.) is read from the
    sibling metadata.json written by Chunker.compile().
    """
    tree = etree.parse(path)

    # Resolve citations inline
    linker = TEILinker(kb=Gazetteer.from_json(GAZETTEER_PATH), decompose=True)
    _stats = linker.run(tree)

    root = tree.getroot()

    base_urn = root.get("base_urn", "")
    cts_urn = root.get("cts_urn", "")
    prev_urn = root.get("prev_urn")
    next_urn = root.get("next_urn")
    chunk_unit = root.get("unit", "")

    metadata_path = path.parent / "metadata.json"
    doc_meta: dict[str, Any] = {}
    if metadata_path.exists():
        with open(metadata_path) as f:
            doc_meta = json.load(f).get("document", {})

    title = doc_meta.get("title", "")
    language = doc_meta.get("language", "")
    pub_info: dict[str, Any] = {
        "title": title,
        "author": doc_meta.get("author", ""),
        "editors": doc_meta.get("editors", []),
        "pub_place": doc_meta.get("pub_place", ""),
        "pub_date": doc_meta.get("pub_date", ""),
    }

    content_el = root.find("elements")

    if content_el is None:
        raise TEIParserError("No content element found!")

    parser = TEIParser(content_el, base_urn, chunk_unit)

    sidecar = path.with_suffix(".tokens.json")
    if sidecar.exists():
        with open(sidecar) as f:
            inject_tokens(parser.elements, json.load(f).get("tokens", []))

    chunk = _Chunk(
        cts_urn=cts_urn,
        prev_urn=prev_urn,
        next_urn=next_urn,
        title=title,
        base_urn=cts_urn.rsplit(":", 1)[0],
        language=language,
        elements=parser.elements,
    )
    return chunk, pub_info


def _max_toc_depth(es: list[dict]) -> int:
    d = -1
    for e in es:
        d = max(d, e["depth"])
        if e.get("subpassages"):
            d = max(d, _max_toc_depth(e["subpassages"]))
    return d


def _do_prune_toc(es: list[dict], max_depth: int) -> list[dict]:
    return [
        {**e, "subpassages": _do_prune_toc(e.get("subpassages", []), max_depth)}
        for e in es
        if e["depth"] < max_depth
    ]


def _prune_toc_leaves(entries: list[dict]) -> list[dict]:
    """Remove the deepest citation level, keeping only the penultimate level as leaves."""
    if not entries:
        return entries

    max_d = _max_toc_depth(entries)
    if max_d <= 0:
        return entries

    return _do_prune_toc(entries, max_d)


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
    with open(metadata_path) as f:
        toc_entries = json.load(f).get("toc", [])
    toc_entries = _prune_toc_leaves(toc_entries)
    _annotate_toc(toc_entries, corpus, textgroup, work, version)
    return {"table_of_contents": toc_entries}


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
            except (ConfigurationError, Exception) as exc:
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

    @app.get("/urn-index.json")
    def urn_index():
        return _build_urn_index(PROTO_DIR), 200, {"Content-Type": "application/json"}

    @app.get("/")
    def index():
        with open(NEWS_MARKDOWN) as f:
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
        with open(RESEARCH_MARKDOWN) as f:
            research_markdown = markdown.markdown(f.read())

        return (
            render_template("research.html.jinja", research_markdown=research_markdown),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/<path:corpus>/<path:textgroup>/<path:work>/<path:version>/<path:chunk>/")
    def reading_view(corpus, textgroup, work, version, chunk):
        index_file = PROTO_DIR / corpus / textgroup / work / version / "index.json"
        if not index_file.exists():
            abort(404)

        with open(index_file) as f:
            work_index = json.load(f)

        urn = f"urn:cts:{corpus}:{textgroup}.{work}.{version}:{chunk}"
        chunk_entry = next(
            (c for c in work_index["chunks"] if c["cts_urn"] == urn), None
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

        base_urn = (
            chunk_obj.base_urn
        )  # e.g. urn:cts:greekLit:tlg0003.tlg001.perseus-grc2
        work_base_urn = base_urn.rsplit(".", 1)[0]  # drop version component

        return (
            render_template(
                "reading.html.jinja",
                chunk=chunk_obj,
                pub_info=pub_info,
                toc=toc,
                current_urn=urn,
                textgroup_urn=f"urn:cts:{corpus}:{textgroup}",
                work_urn=f"urn:cts:{corpus}:{textgroup}.{work}",
                prev_url=prev_url,
                next_url=next_url,
                citation_uri=f"http://data.perseus.org/citations/{chunk_obj.cts_urn}",
                text_uri=f"http://data.perseus.org/texts/{base_urn}",
                work_uri=f"http://data.perseus.org/texts/{work_base_urn}",
                catalog_record_uri=f"http://data.perseus.org/catalog/{base_urn}",
                xml_src_url=_xml_src_url(corpus, textgroup, work, version),
                morph_url=MORPH_URL,
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

    freezer.freeze()


def main():
    app = create_app()

    app.run(debug=True)

    return app
