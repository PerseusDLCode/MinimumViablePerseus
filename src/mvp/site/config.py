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
FUNDING_MARKDOWN = MARKDOWN_DIR / "funding.md"
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
    "engLit": "English",
    "greekLit": "Greek",
    "hebrewlit": "Hebrew",
    "itaLit": "Italian",
    "latinLit": "Latin",
    "Notre-Dame-Digitized-Latin-Collection": "Notre Dame Digitized Latin Collection",
    "grcnewxml": "Greek (New XML)",
}

# Fallback original language for a corpus's works, used to tell editions
# from translations on /collections when the CTS catalog doesn't classify a
# version itself (see catalog_tree._version_kind).
_CORPUS_LANGUAGES = {
    "engLit": "eng",
    "greekLit": "grc",
    "grcnewxml": "grc",
    "hebrewlit": "heb",
    "itaLit": "ita",
    "japaneseLit": "jpn",
    "latinLit": "lat",
    "Notre-Dame-Digitized-Latin-Collection": "lat",
}

# Source repos (subdirectories of CORPORA_DIR) whose texts are provisional,
# uncorrected OCR. Every version they contribute is flagged "Experimental"
# on /collections and the reading page and sorted below curated versions
# (see catalog_tree._experimental_version_ids). Keyed by repo rather than
# CTS namespace: grcnewxml declares greekLit/latinLit/itaLit URNs.
_EXPERIMENTAL_SOURCES = {"grcnewxml"}

# Version-id prefixes of the Perseus and First1KGreek projects' own curated
# editions and translations, and the badge label each gets on /collections
# and the reading page (see catalog_tree._curated_source). Keyed by version
# id rather than source repo: both projects' ids are distinctive, and a
# global build only has ids to go on.
_CURATED_SOURCES = {
    "perseus-": "Perseus",
    "1st1K-": "First1KGreek",
}

# Licence each source repo (subdirectory of CORPORA_DIR) declares for its
# texts as a whole, in its license.md/LICENSE/README. The reading page uses
# this only when a document's own TEI header has no
# publicationStmt/availability/licence (see chunks._resolve_licence). Repos
# absent here (canonical-engLit, grcnewxml, canonical_pdlrefwk) state no
# licence, so the page makes no licence claim for them.
_CC_BY_SA_4 = {
    "text": "Available under a Creative Commons Attribution-ShareAlike 4.0 International License",
    "target": "https://creativecommons.org/licenses/by-sa/4.0/",
}
_SOURCE_LICENCES = {
    "canonical-greekLit": _CC_BY_SA_4,
    "canonical-latinLit": _CC_BY_SA_4,
    "canonical-pdlrefwk": _CC_BY_SA_4,
    "First1KGreek": _CC_BY_SA_4,
    "Notre-Dame-Digitized-Latin-Collection": {
        "text": "Available under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License",
        "target": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    },
    "ajmc-tei": {
        "text": "Available under the GNU General Public License, version 3 or later",
        "target": "https://www.gnu.org/licenses/gpl-3.0.html",
    },
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

# Per-version overrides for the /collections page's "preferred edition"
# logic (see catalog_tree._mark_preferred_versions). Keyed by the full
# version URN (urn:cts:<corpus>:<textgroup>.<work>.<version>) rather than
# the bare version id -- ids like "perseus-grc2" repeat across every work,
# so a bare-id key would apply the override everywhere at once. Empty by
# default: absent an entry, the highest-numbered id in each version-id
# family (e.g. perseus-grc2 over perseus-grc1) is preferred.
_VERSION_OVERRIDES: dict[str, dict] = {}

_EDITOR_ROLE_LABELS = {
    "translator": "Translator",
    "transl": "Translator",
    "editor": "Editor",
    "associate editor": "Associate Editor",
    "assistant editor": "Assistant Editor",
    "commentator": "Commentator",
}
