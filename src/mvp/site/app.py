import json
import os

import markdown
from flask import Flask, abort, redirect, render_template, url_for
from perseus_cts.commentary import links_for_passage
from perseus_cts.models import CTSCatalog

from mvp.site import chunks, config
from mvp.site.catalog_tree import (
    _build_collections,
    _build_urn_index,
    _discover_corpora,
    _flatten_search_index,
    _work_title,
    _xml_src_url,
)
from mvp.site.chunks import _chunk_citation_range, _chunk_end_line, _chunk_start_line
from mvp.site.commentary import _build_commentary_groups
from mvp.site.new_alexandria import build_new_alexandria_index
from mvp.site.proto_pages import generate_proto_pages
from mvp.site.siblings import _build_sibling_data, _reading_view_url
from mvp.site.toc import _scheme_toggle_links, _toc_from_metadata


def create_app(
    test_config=None,
    collections_override: list[dict] | None = None,
    urn_index_override: dict[str, dict[str, str]] | None = None,
):
    """Build the Flask app.

    collections_override/urn_index_override let a `--mode global-only` build
    (see mvp.site.build.build()) serve /collections/ and /urn-index.json
    from manifests merged across corpora instead of computing them from
    CORPORA_DIR/PROTO_DIR — that build has no corpus data checked out at
    all, just manifest.json files. Both are None in normal (non-split)
    operation, which is unchanged from before this parameter existed.
    """
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
        app.config.from_pyfile("config.py", silent=True)
    else:
        app.config.from_mapping(test_config)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    corpora = _discover_corpora(config.CORPORA_DIR)

    generate_proto_pages(config.PROTO_DIR, corpora)

    catalog = CTSCatalog([c.root for c in corpora])
    app.catalog = catalog  # ty: ignore[unresolved-attribute]
    app.new_alexandria = build_new_alexandria_index(  # ty: ignore[unresolved-attribute]
        config.NEW_ALEXANDRIA_DIR
    )

    @app.get("/urn-index.json")
    def urn_index():
        data = (
            urn_index_override
            if urn_index_override is not None
            else _build_urn_index(config.PROTO_DIR)
        )
        return data, 200, {"Content-Type": "application/json"}

    @app.get("/")
    def index():
        with open(config.NEWS_MARKDOWN, encoding="utf-8") as f:
            news_markdown = markdown.markdown(f.read())

        return (
            render_template("index.html.jinja", news_markdown=news_markdown),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/collections/")
    def get_collections():
        collections = (
            collections_override
            if collections_override is not None
            else _build_collections(config.PROTO_DIR, catalog)
        )
        return (
            render_template("collections.html.jinja", collections=collections),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/collections/search-index.json")
    def get_collections_search_index():
        if collections_override is not None:
            collections = collections_override
        else:
            collections = _build_collections(config.PROTO_DIR, catalog)
            for corpus in collections:
                for textgroup in corpus["textgroups"]:
                    for work in textgroup["works"]:
                        for version in work["versions"]:
                            version["href"] = url_for(
                                "reading_view", **version["first_chunk_kwargs"]
                            )
        return (
            _flatten_search_index(collections),
            200,
            {"Content-Type": "application/json"},
        )

    def _render_markdown_page(markdown_path, page_title):
        with open(markdown_path, encoding="utf-8") as f:
            markdown_content = markdown.markdown(f.read())

        return (
            render_template(
                "markdown.html.jinja",
                markdown_content=markdown_content,
                page_title=page_title,
            ),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/about/")
    def get_about():
        return _render_markdown_page(config.ABOUT_MARKDOWN, "About")

    @app.get("/grants/")
    def get_grants():
        return _render_markdown_page(config.GRANTS_MARKDOWN, "Grants")

    @app.get("/help/")
    def get_help():
        return _render_markdown_page(config.HELP_MARKDOWN, "Help")

    @app.get("/history/")
    def get_history():
        return _render_markdown_page(config.HISTORY_MARKDOWN, "History")

    @app.get("/open-source/")
    def get_open_source():
        return _render_markdown_page(config.OPEN_SOURCE_MARKDOWN, "Open Source")

    @app.get("/research/")
    def get_research():
        return _render_markdown_page(config.RESEARCH_MARKDOWN, "Research")

    def _redirect_to_first_chunk(corpus, textgroup, work, version, scheme, index_file):
        if not index_file.exists():
            abort(404)

        with open(index_file, encoding="utf-8") as f:
            work_index = json.load(f)

        chunk_list = work_index.get("chunks")
        if not chunk_list:
            abort(404)

        passage = chunk_list[0]["cts_urn"].rsplit(":", 1)[-1]

        route_kwargs = {
            "corpus": corpus,
            "textgroup": textgroup,
            "work": work,
            "version": version,
            "chunk": passage,
        }
        if scheme:
            route_kwargs["scheme"] = scheme
        return redirect(
            url_for("reading_view_scheme" if scheme else "reading_view", **route_kwargs)
        )

    @app.get("/urn:cts:<path:corpus>:<path:textgroup>.<path:work>.<string:version>/")
    def get_first_chunk(corpus, textgroup, work, version):
        index_file = (
            config.PROTO_DIR / corpus / textgroup / work / version / "index.json"
        )
        return _redirect_to_first_chunk(
            corpus, textgroup, work, version, None, index_file
        )

    @app.get(
        "/urn:cts:<path:corpus>:<path:textgroup>.<path:work>.<string:version>"
        "/<string:scheme>/"
    )
    def get_first_scheme_chunk(corpus, textgroup, work, version, scheme):
        index_file = (
            config.PROTO_DIR
            / corpus
            / textgroup
            / work
            / version
            / scheme
            / "index.json"
        )
        return _redirect_to_first_chunk(
            corpus, textgroup, work, version, scheme, index_file
        )

    def _render_nav_fragment(corpus, textgroup, work, version, scheme=None):
        version_dir = config.PROTO_DIR / corpus / textgroup / work / version
        data_dir = version_dir / scheme if scheme else version_dir

        toc = _toc_from_metadata(
            data_dir / "metadata.json", corpus, textgroup, work, version, scheme
        )

        return (
            render_template("nav_fragment.html.jinja", toc=toc),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get(
        "/urn:cts:<path:corpus>:<path:textgroup>.<path:work>.<string:version>/_toc/"
    )
    def get_nav_fragment(corpus, textgroup, work, version):
        return _render_nav_fragment(corpus, textgroup, work, version)

    @app.get(
        "/urn:cts:<path:corpus>:<path:textgroup>.<path:work>.<string:version>"
        "/<string:scheme>/_toc/"
    )
    def get_nav_fragment_scheme(corpus, textgroup, work, version, scheme):
        return _render_nav_fragment(corpus, textgroup, work, version, scheme=scheme)

    def _render_reading_view(corpus, textgroup, work, version, chunk, scheme=None):
        version_dir = config.PROTO_DIR / corpus / textgroup / work / version
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

        chunk_obj, pub_info = chunks._parse_chunk(chunk_file)
        nav_route_kwargs = {
            "corpus": corpus,
            "textgroup": textgroup,
            "work": work,
            "version": version,
        }
        if scheme:
            nav_route_kwargs["scheme"] = scheme
        nav_fragment_url = url_for(
            "get_nav_fragment_scheme" if scheme else "get_nav_fragment",
            **nav_route_kwargs,
        )

        prev_url = (
            _reading_view_url(
                corpus,
                textgroup,
                work,
                version,
                chunk_obj.prev_urn.rsplit(":", 1)[-1],
                scheme,
            )
            if chunk_obj.prev_urn
            else None
        )
        next_url = (
            _reading_view_url(
                corpus,
                textgroup,
                work,
                version,
                chunk_obj.next_urn.rsplit(":", 1)[-1],
                scheme,
            )
            if chunk_obj.next_urn
            else None
        )
        current_line = _chunk_start_line(chunk_obj.cts_urn)
        current_end = _chunk_end_line(chunk_obj.cts_urn)
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
            corpus,
            textgroup,
            work,
            version,
            chunk,
            current_line,
            current_end,
            catalog,
            base_urn,
            scheme=scheme,
        )

        citation_range = _chunk_citation_range(chunk_obj)
        commentary = links_for_passage(catalog, work_base_urn, citation_range)
        commentary_groups = _build_commentary_groups(commentary)
        new_alexandria_groups = app.new_alexandria.entries_for_passage(
            work_base_urn, citation_range
        )
        work_title = _work_title(catalog, work_base_urn, fallback=f"{textgroup}.{work}")

        return (
            render_template(
                "reading.html.jinja",
                catalog_record_uri=f"http://catalog.perseus.org/catalog/{base_urn}",
                chunk=chunk_obj,
                work_title=work_title,
                commentary_groups=commentary_groups,
                commentary_warnings=commentary.warnings,
                new_alexandria_groups=new_alexandria_groups,
                citation_uri=f"http://catalog.perseus.org/citations/{chunk_obj.cts_urn}",
                current_urn=urn,
                document_id=f"{textgroup}.{work}.{version}",
                sibling_data=sibling_data,
                language_labels=config._LANGUAGE_LABELS,
                morph_url=config.MORPH_URL,
                nav_fragment_url=nav_fragment_url,
                next_url=next_url,
                prev_url=prev_url,
                pub_info=pub_info,
                scheme_links=scheme_links,
                text_uri=f"http://catalog.perseus.org/texts/{base_urn}",
                textgroup_urn=f"urn:cts:{corpus}:{textgroup}",
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


def main():
    app = create_app()

    app.run(debug=True)

    return app
