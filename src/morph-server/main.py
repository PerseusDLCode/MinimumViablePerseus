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
from itertools import groupby
from operator import itemgetter

import json
import pickle

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import beta_code

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

# Stable sorted tuple for frequency key construction — frozenset iteration order
# is hash-randomized per process, so keys built in the notebook would never match
# keys built in the server without this fixed ordering.
_FREQ_TAGS = tuple(sorted(FEATURE_TAGS | {"form"}))


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
# Dictionary lookup
# ---------------------------------------------------------------------------
class Sense(BaseModel):
    id: str # "n72.2"
    n: str # "1", "I", "IV" — the display label
    level: int # nesting depth
    parent_id: str | None
    translation: str | None # extracted <tr> content, e.g. "good, gentle, noble"
    text: str # full rendered text of the sense, HTML or plain

class DictionaryEntry(BaseModel):
    key: str  # beta code key for morph lookup
    headword: str # unicode display form
    etymology: str | None
    senses: list[Sense] # flat list, reconstructed as tree via parent_id

greek_morphs = pickle.load(open(XML_DIR / "greek_morph_freqs.pkl", "rb"))
latin_morphs = pickle.load(open(XML_DIR / "latin_morph_freqs.pkl", "rb"))

with open(XML_DIR / "lsj_index.json", "r", encoding="utf-8") as f:
    lsj_index = {k: DictionaryEntry.model_validate(v) for k, v in json.load(f).items()}
with open(XML_DIR / "ls_index.json", "r", encoding="utf-8") as f:
    ls_index = {k: DictionaryEntry.model_validate(v) for k, v in json.load(f).items()}

_MORPH_FREQS = {"grc": greek_morphs, "la": latin_morphs}
_DICT_INDEXES = {"grc": lsj_index, "la": ls_index}

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

def _lookup_freqs(form: str, lang: str) -> dict[str, float]:
    """Return {display_lemma: summed_corpus_frequency} for all lemmas of form."""
    index = app.state.indexes[lang]
    lookup_form = form
    if lang == "grc" and _is_unicode_greek(form):
        lookup_form = _unicode_to_betacode(form)
    lookup_key = _KEY_FN[lang](lookup_form)
    parses = index.get(lookup_key, [])

    morph_freqs = _MORPH_FREQS[lang]
    lemma_scores: dict[str, float] = defaultdict(float)
    
    counting_sum = 0
    for parse in parses:
        if "lemma" not in parse:
            continue
        freq_key = (lang,) + tuple(parse.get(tag, None) for tag in _FREQ_TAGS)
        counting_sum += morph_freqs.get(freq_key, 0.0)    
    
    for parse in parses:
        if "lemma" not in parse:
            continue
        freq_key = (lang,) + tuple(parse.get(tag, None) for tag in _FREQ_TAGS)
        lemma = _beta_to_unicode(parse["lemma"]) if lang == "grc" else parse["lemma"]
        lemma_scores[lemma] += (morph_freqs.get(freq_key, 0.0)/counting_sum)*100.0 if counting_sum > 0 else 0.0

    return dict(sorted(lemma_scores.items(), key=lambda x: x[1], reverse=True))

def _beta_to_unicode(beta: str) -> str:
    """Convert a Beta Code string to Unicode Greek."""
    return beta_code.beta_code_to_greek(beta)

def _dictionary_lookup(form: str, lang: str) -> DictionaryEntry | None:
    return _DICT_INDEXES[lang].get(form.lower())

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
.lemma    { border: 2px solid black }
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
    sorted_by_lemma = sorted(raw, key=itemgetter('lemma'))
    lemma_display = _beta_to_unicode if lang == "grc" else (lambda x: x)
    grouped_by_lemma = {lemma_display(k): list(v) for k, v in groupby(sorted_by_lemma, key=itemgetter('lemma'))}

    scores = _lookup_freqs(form, lang)
    shared_keys = set(scores.keys()) & set(grouped_by_lemma.keys())
    aligned_scores = {k: (grouped_by_lemma[k], scores[k], _dictionary_lookup(k, lang) if _dictionary_lookup(k, lang) else None) for k in shared_keys}
    ordered_aligned_scores = dict(sorted(aligned_scores.items(), key=lambda item: item[1][1], reverse=True)) # order by frequency

    lang_name = _LANG_NAMES.get(lang, lang)
    title_esc = form.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    lemma_box_template = """
<div class='analysis'>
    <div class='lemma' id='{lemma}'>
        <div class='lemma_header'>
            <h4 class='{lang}'>{lemma}</h4>
            <span class='lemma_definitions'>{first_def}</span>
        </div>
        <p class='confidence'>{score}</p>
        <table>
            <tbody>
                {features}
            </tbody>
        </table>
    </div>
</div>
<div class="lexicon_entry">
    {full_entry}
</div>
"""

    feature_row_template = """<tr>
    <td class='la'>{lemma}</td>
    <td>{feats}</td>
</tr>
"""

    if raw:
        # analyses_html = f"<pre>{json.dumps(ordered_aligned_scores, indent=2, ensure_ascii=False)}</pre>"
        analyses_html = ""
        for lemma, (parses, score, dict_entry) in ordered_aligned_scores.items():
            if dict_entry:
                first_def = dict_entry.senses[0].translation if dict_entry.senses and dict_entry.senses[0].translation else ""
                first_def = first_def.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            else:
                first_def = ""

            features_html = ""
            for parse in parses:
                feats = ", ".join(f"{k}={v}" for k, v in parse.items() if k != "lemma")
                features_html += feature_row_template.format(lemma=lemma, feats=feats)

            full_entry = ""
            if dict_entry:
                full_entry += f"<h3>{dict_entry.headword}</h3>"
                if dict_entry.etymology:
                    full_entry += f"<p><em>Etymology:</em> {dict_entry.etymology}</p>"
                for sense in dict_entry.senses:
                    sense_text = sense.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    full_entry += f"<div class='sense'><strong>{sense.n}.</strong> {sense_text}</div>"
            
            analyses_html += lemma_box_template.format(
                lemma=lemma,
                lang=lang,
                score=f"{score:.2f}%",
                first_def=first_def,
                features=features_html,
                full_entry=full_entry,
            )
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
