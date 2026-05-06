"""
Perseus Morphology API

Serves morphological analyses for Latin and Ancient Greek by looking up
pre-computed Morpheus data from latin.morph.xml and greek.morph.xml.

Both indexes are built once at startup and held in memory. All subsequent
requests are constant-time dictionary lookups.
"""

import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

XML_DIR = Path(__file__).parent

LANGUAGE_FILES = {
    "la":  "latin.morph.xml",
    "grc": "greek.morph.xml",
}

# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

FEATURE_TAGS = frozenset({
    "lemma", "pos", "person", "number", "tense", "mood",
    "voice", "gender", "case", "degree", "dialect", "feature",
})


def _build_index(xml_path: Path, key_fn) -> dict[str, list[dict]]:
    """
    Stream through an XML file and return a dict mapping
    normalized form -> list of analysis dicts (one per <analysis> element).
    """
    index: dict[str, list[dict]] = defaultdict(list)
    current: dict[str, str] = {}
    all_tags = FEATURE_TAGS | {"form"}

    for event, elem in ET.iterparse(xml_path, events=("start", "end")):
        if event == "start" and elem.tag == "analysis":
            current = {}
        elif event == "end" and elem.tag == "analysis":
            if "form" in current:
                key = key_fn(current["form"])
                index[key].append({k: v for k, v in current.items() if k != "form"})
            elem.clear()
        elif event == "end" and elem.tag in all_tags and elem.text:
            current[elem.tag] = elem.text.strip()

    return dict(index)

# ---------------------------------------------------------------------------
# Form normalization
# ---------------------------------------------------------------------------

def _normalize_greek(form: str) -> str:
    """
    Normalize a Beta Code form for index lookup.

    Mirrors the logic in GreekAdapter.getLookupForm():
      - Convert grave accents (\) to acute (/)
      - Remove secondary accents (a trailing / caused by a following enclitic)
      - Remove philological marks (square brackets)
    """
    form = form.replace("\\", "/")
    form = re.sub(r"([/=].*)\/", r"\1", form, count=1)
    form = re.sub(r"[\[\]]", "", form)
    return form


def _greek_key(form: str) -> str:
    """Case-insensitive Beta Code key. In Beta Code, * marks a capital letter."""
    return _normalize_greek(form).replace("*", "").lower()


def _latin_key(form: str) -> str:
    return form.lower()


_KEY_FN = {
    "la":  _latin_key,
    "grc": _greek_key,
}

# ---------------------------------------------------------------------------
# Unicode Greek → Beta Code conversion
# ---------------------------------------------------------------------------

# Maps lowercase Unicode Greek base letters to their Beta Code equivalents.
_GREEK_LETTER_TO_BETA: Dict[str, str] = {
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z",
    "η": "h", "θ": "q", "ι": "i", "κ": "k", "λ": "l", "μ": "m",
    "ν": "n", "ξ": "c", "ο": "o", "π": "p", "ρ": "r", "σ": "s",
    "ς": "s", "τ": "t", "υ": "u", "φ": "f", "χ": "x", "ψ": "y",
    "ω": "w",
}

# Maps Unicode combining marks (as they appear in NFD decomposition) to Beta Code.
_COMBINING_TO_BETA: Dict[str, str] = {
    "̓": ")",   # smooth breathing (psili)
    "̔": "(",   # rough breathing (dasia)
    "́": "/",   # acute accent (oxia)
    "̀": "\\",  # grave accent (varia)
    "͂": "=",   # circumflex (perispomeni)
    "ͅ": "|",   # iota subscript (ypogegrammeni)
    "̈": "+",   # diaeresis
}


def _is_unicode_greek(text: str) -> bool:
    """Return True if text contains any Unicode Greek characters."""
    return any("Ͱ" <= c <= "Ͽ" or "ἀ" <= c <= "῿" for c in text)


def _unicode_to_betacode(text: str) -> str:
    """
    Convert Unicode Greek text to Perseus Beta Code.

    Works by NFD-decomposing each character into its base letter and combining
    marks, then mapping both to their Beta Code equivalents. NFD decomposition
    preserves the diacritic ordering that Beta Code expects (breathing before
    accent, accent before iota subscript).

    Uppercase letters are prefixed with * per Beta Code convention.
    Non-Greek characters are passed through unchanged.
    """
    result = []
    for char in unicodedata.normalize("NFD", text):
        lower = char.lower()
        if lower in _GREEK_LETTER_TO_BETA:
            if char != lower:  # uppercase Greek letter
                result.append("*")
            result.append(_GREEK_LETTER_TO_BETA[lower])
        elif char in _COMBINING_TO_BETA:
            result.append(_COMBINING_TO_BETA[char])
        else:
            result.append(char)  # punctuation, spaces, non-Greek letters
    return "".join(result)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Building morphology indexes — this takes about 30-60 seconds...")
    app.state.indexes = {}
    for lang, filename in LANGUAGE_FILES.items():
        path = XML_DIR / filename
        print(f"  Loading {filename} ...")
        app.state.indexes[lang] = _build_index(path, _KEY_FN[lang])
        count = len(app.state.indexes[lang])
        print(f"  [{lang}] {count:,} unique forms indexed.")
    print("Ready.\n")
    yield


app = FastAPI(
    title="Perseus Morphology API",
    description="Morphological analyses for Latin and Ancient Greek, backed by Morpheus data.",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class Analysis(BaseModel):
    lemma:   str
    pos:     Optional[str] = None
    person:  Optional[str] = None
    number:  Optional[str] = None
    tense:   Optional[str] = None
    mood:    Optional[str] = None
    voice:   Optional[str] = None
    gender:  Optional[str] = None
    case:    Optional[str] = None
    degree:  Optional[str] = None
    dialect: Optional[str] = None
    feature: Optional[str] = None


class AnalysisResponse(BaseModel):
    form:     str
    language: str
    analyses: List[Analysis]

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/analyze", response_model=AnalysisResponse)
def analyze(
    form: str = Query(..., description="Word form to look up. Greek accepts Unicode (ἔργα) or Beta Code (e)/rga)."),
    lang: str = Query(..., description="Language code: 'la' (Latin) or 'grc' (Ancient Greek)"),
):
    if lang not in LANGUAGE_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language '{lang}'. Use 'la' or 'grc'.",
        )

    lookup_form = form
    if lang == "grc" and _is_unicode_greek(form):
        lookup_form = _unicode_to_betacode(form)

    key = _KEY_FN[lang](lookup_form)
    raw = app.state.indexes[lang].get(key, [])

    return AnalysisResponse(
        form=form,
        language=lang,
        analyses=[Analysis(**a) for a in raw],
    )


_LANG_NAMES = {"la": "Latin", "grc": "Ancient Greek"}

_MORPH_CSS = """
body      { font-family: serif; max-width: 36em; margin: 2em auto; padding: 0 1em }
h1        { font-size: 1.6em; margin-bottom: .15em }
.meta     { color: #555; margin-bottom: 1.5em; font-size: .9em }
.none     { color: #888; font-style: italic }
pre       { background: #f5f5f5; padding: 1em; overflow-x: auto;
            font-size: .85em; line-height: 1.5; border-radius: 3px }
.back     { font-size: .85em; color: #555 }
"""


@app.get("/morph", response_class=HTMLResponse)
def morph_page(
    form: str = Query(..., description="Word form to display."),
    lang: str = Query(..., description="Language code: 'la' or 'grc'."),
):
    if lang not in LANGUAGE_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language '{lang}'. Use 'la' or 'grc'.",
        )

    lookup_form = form
    if lang == "grc" and _is_unicode_greek(form):
        lookup_form = _unicode_to_betacode(form)

    key = _KEY_FN[lang](lookup_form)
    raw = app.state.indexes[lang].get(key, [])

    lang_name = _LANG_NAMES.get(lang, lang)
    title_esc = form.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    if raw:
        analyses_html = f"<pre>{json.dumps(raw, indent=2, ensure_ascii=False)}</pre>"
    else:
        analyses_html = '<p class="none">No analyses found.</p>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>{title_esc} — Morphological Analysis | Perseus</title>
  <style>{_MORPH_CSS}</style>
</head>
<body>
  <h1>{title_esc}</h1>
  <p class="meta">Language: {lang_name}</p>
  {analyses_html}
  <p class="back"><a href="javascript:history.back()">&#x2190; back</a></p>
</body>
</html>
"""
    return HTMLResponse(content=html)
