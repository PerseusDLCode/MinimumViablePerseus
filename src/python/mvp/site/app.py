import json
import os

from pathlib import Path

import markdown

from flask import Flask, abort, render_template

from mvp.corpus.corpus import Corpus
from mvp.site.compilers import CompilationError, ProtopageCompiler
from mvp.site.compilers.protopage_compiler import _parse_chunk
from mvp.site.site_map import SiteMap


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
CORPORA_DIR = Path(os.getenv("CORPORA_DIR", ROOT_DIR / "corpora"))
MARKDOWN_DIR = APP_DIR / "static" / "markdown"
NEWS_MARKDOWN = MARKDOWN_DIR / "news.md"
RESEARCH_MARKDOWN = MARKDOWN_DIR / "research.md"
MORPH_URL = os.getenv("MORPH_URL", "http://localhost:8000/morph")
PROTO_DIR = Path(os.getenv("PROTOPAGE_OUTPUT_DIR", ROOT_DIR / "proto-pages"))
XSL_FILE = APP_DIR.parents[2] / "xslt" / "html" / "generate_protopages.xsl"

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


def _build_toc(
    work_index: dict,
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
) -> dict:
    """Build a nested TOC dict from a flat index.json chunk list.

    If all chunks share the same book (or have no book), returns a flat list
    of chapter entries.  Otherwise nests chapter entries under book entries.

    Each leaf item carries a ``route_kwargs`` dict suitable for Flask's
    ``url_for('reading_view', **item.route_kwargs)``.
    """
    book_label = work_index.get("book_subtype", "book").capitalize()
    chapter_label = work_index.get("chapter_subtype", "chapter").capitalize()
    chunks = work_index["chunks"]

    unique_books = {entry["book"] for entry in chunks}
    single_level = len(unique_books) <= 1

    def _leaf(entry: dict) -> dict:
        passage = entry["urn"].rsplit(":", 1)[-1]
        return {
            "urn": entry["urn"],
            "label": f"{chapter_label} {entry['chapter']}",
            "subpassages": [],
            "route_kwargs": {
                "corpus": corpus,
                "textgroup": textgroup,
                "work": work,
                "version": version,
                "chunk": passage,
            },
        }

    if single_level:
        return {"table_of_contents": [_leaf(e) for e in chunks]}

    books: dict[str, dict] = {}
    for entry in chunks:
        book = entry["book"]
        if book not in books:
            books[book] = {
                "urn": f"{work_index['base_urn']}:{book}",
                "label": f"{book_label} {book}",
                "route_kwargs": None,
                "subpassages": [],
            }
        books[book]["subpassages"].append(_leaf(entry))
    return {"table_of_contents": list(books.values())}


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
                    if not index_file.exists():
                        continue
                    with open(index_file) as f:
                        idx = json.load(f)
                    chunks = idx.get("chunks", [])
                    if not chunks:
                        continue
                    first_passage = chunks[0]["urn"].rsplit(":", 1)[-1]
                    lang = idx.get("language", "")
                    versions.append(
                        {
                            "id": ver_dir.name,
                            "title": idx.get("title", ver_dir.name),
                            "language": lang,
                            "language_label": _LANGUAGE_LABELS.get(lang, lang),
                            "first_chunk_url": (
                                f"/{corpus}/{tg_dir.name}/{work_dir.name}"
                                f"/{ver_dir.name}/{first_passage}"
                            ),
                        }
                    )
                    tg_author = idx.get("author", tg_dir.name)

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
    xsl_file: Path,
) -> None:
    """Generate proto-page XML for all corpus documents.

    Skips documents whose index.json already exists in proto_dir so the
    function is safe to call on every startup without re-doing prior work.
    """
    site_map = SiteMap(proto_dir)
    compiler = ProtopageCompiler(xsl_file=xsl_file)
    generated = skipped = failed = 0

    for corpus in corpora:
        for doc in corpus.documents():
            if not doc.metadata.urn:
                continue
            if site_map.manifest_path(doc.metadata.urn).exists():
                skipped += 1
                continue
            try:
                compiler.compile(doc, site_map.chunk_dir(doc.metadata.urn))
                generated += 1
            except CompilationError as exc:
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
    generate_proto_pages(PROTO_DIR, corpora, XSL_FILE)

    @app.get("/")
    def index():
        with open(NEWS_MARKDOWN) as f:
            news_markdown = markdown.markdown(f.read())

        return (
            render_template("index.html.jinja", news_markdown=news_markdown),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/collections")
    def get_collections():
        collections = _build_collections(PROTO_DIR)
        return (
            render_template("collections.html.jinja", collections=collections),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/research")
    def get_research():
        with open(RESEARCH_MARKDOWN) as f:
            research_markdown = markdown.markdown(f.read())

        return (
            render_template("research.html.jinja", research_markdown=research_markdown),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/<path:corpus>/<path:textgroup>/<path:work>/<path:version>/<path:chunk>")
    def reading_view(corpus, textgroup, work, version, chunk):
        index_file = PROTO_DIR / corpus / textgroup / work / version / "index.json"
        if not index_file.exists():
            abort(404)

        with open(index_file) as f:
            work_index = json.load(f)

        urn = f"urn:cts:{corpus}:{textgroup}.{work}.{version}:{chunk}"
        chunk_entry = next((c for c in work_index["chunks"] if c["urn"] == urn), None)
        if chunk_entry is None:
            abort(404)

        chunk_file = (
            PROTO_DIR / corpus / textgroup / work / version / chunk_entry["file"]
        )
        if not chunk_file.exists():
            abort(404)

        chunk_obj, pub_info = _parse_chunk(chunk_file)
        toc = _build_toc(work_index, corpus, textgroup, work, version)

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


def main():
    app = create_app()

    app.run(debug=True)

    return app
