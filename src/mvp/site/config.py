"""Env-derived paths and lookup tables shared across mvp.site.

Other modules must `from mvp.site import config` and reference `config.X`
rather than `from mvp.site.config import X`: PROTO_DIR/CORPORA_DIR/TOKENS_DIR
are monkeypatched by tests as module attributes, which only takes effect on
readers that look the name up on this module at call time.
"""

import os
from pathlib import Path

import citation_resolution

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_GAZETTEER = (
    Path(citation_resolution.__file__).parent / "data" / "gazetteer.json"
)
GAZETTEER_PATH = Path(os.getenv("GAZETTEER_PATH", _DEFAULT_GAZETTEER))
CORPORA_DIR = Path(os.getenv("CORPORA_DIR", ROOT_DIR / "corpora"))
MARKDOWN_DIR = APP_DIR / "static" / "markdown"
ABOUT_MARKDOWN = MARKDOWN_DIR / "about.md"
GRANTS_MARKDOWN = MARKDOWN_DIR / "grants.md"
HELP_MARKDOWN = MARKDOWN_DIR / "help.md"
HISTORY_MARKDOWN = MARKDOWN_DIR / "history.md"
NEWS_MARKDOWN = MARKDOWN_DIR / "news.md"
OPEN_SOURCE_MARKDOWN = MARKDOWN_DIR / "open-source.md"
RESEARCH_MARKDOWN = MARKDOWN_DIR / "research.md"
MORPH_URL = os.getenv("MORPH_URL", "http://localhost:8000/morph")
PROTO_DIR = Path(os.getenv("PROTOPAGE_OUTPUT_DIR", ROOT_DIR / "proto-pages"))
# Token sidecars (.tokens.json.zst) live in their own tree, mirroring
# PROTO_DIR's corpus/textgroup/work/version layout, rather than in the
# proto-pages checkout itself: they're generated and shipped separately
# (see src/tools/run_tokenizer.py) so a corpus build never has to pull or
# regenerate them. Unset by default — reading views render fine without
# token-level data.
_tokens_dir_env = os.getenv("MVP_TOKENS_DIR")
TOKENS_DIR = Path(_tokens_dir_env) if _tokens_dir_env else None
# New Alexandria Commentaries (see src/tools/fetch_new_alexandria.py and
# mvp.site.new_alexandria) are fetched separately from the main build, same
# reasoning as TOKENS_DIR above. Unset by default — reading views render
# fine without them.
_new_alexandria_dir_env = os.getenv("NEW_ALEXANDRIA_DIR")
NEW_ALEXANDRIA_DIR = Path(_new_alexandria_dir_env) if _new_alexandria_dir_env else None
# Proto-page compilation and page freezing are both CPU-bound and
# parallel (independent per document / per URL), so both
# phases of `mvp-build` fan out across this many worker processes. Defaults
# to all cores; set to 1 to force the old sequential behavior.
BUILD_WORKERS = max(1, int(os.getenv("MVP_BUILD_WORKERS", os.cpu_count() or 1)))

_CORPUS_LABELS = {
    "englishLit": "English",
    "greekLit": "Greek",
    "hebrewlit": "Hebrew",
    "latinLit": "Latin",
}

### Deprecated. Do not use.
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
