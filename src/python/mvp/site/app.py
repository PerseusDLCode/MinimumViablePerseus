import os

from pathlib import Path

import markdown
from flask import Flask, render_template


APP_DIR = Path(__file__).resolve().parent
MARKDOWN_DIR = APP_DIR / "static" / "markdown"
NEWS_MARKDOWN = MARKDOWN_DIR / "news.md"
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
CORPORA_DIR = Path(os.getenv("CORPORA_DIR", ROOT_DIR / "corpora"))


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

    @app.get("/")
    def index():
        with open(NEWS_MARKDOWN) as f:
            news_markdown = markdown.markdown(f.read())

        return (
            render_template("index.html.jinja", news_markdown=news_markdown),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/<path:corpus>/<path:textgroup>/<path:work>/<path:version>/<path:chunk>")
    def get_chunk(corpus, textgroup, work, version, chunk):
        pass

    return app


def main():
    app = create_app()

    app.run(debug=True)

    return app
