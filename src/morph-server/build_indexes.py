"""
Build pre-computed data files for the Perseus Morphology API.

Outputs (written to the same directory as this script):
  greek_morph_freqs.pkl  — {(lang, *sorted_feature_vals): float} frequency table
  lsj_index.json         — LSJ dictionary entries keyed by Unicode headword
  latin_morph_freqs.pkl  — same structure, Latin corpus
  ls_index.json          — Lewis & Short entries keyed by lowercase ASCII headword

Run from any directory:
  python src/morph-server/build_indexes.py
"""

import json
import pickle
import re
import unicodedata
import warnings
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Dict

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from pydantic import BaseModel
from tqdm import tqdm

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

HERE = Path(__file__).parent
ROOT = HERE.parent.parent

GREEK_MORPH_XML  = HERE / "greek.morph.xml"
GREEK_CORPUS_DIR = ROOT / "data" / "canonical-greekLit" / "data"
LSJ_XML          = ROOT / "notebooks" / "refwork_test" / "viaf66541464.001.perseus-eng1.xml"

LATIN_MORPH_XML  = HERE / "latin.morph.xml"
LATIN_CORPUS_DIR = ROOT / "data" / "canonical-latinLit" / "data"
LS_XML           = ROOT / "notebooks" / "refwork_test" / "lat.ls.perseus-eng2.xml"

OUTPUT_GREEK_FREQS = HERE / "greek_morph_freqs.pkl"
OUTPUT_LSJ         = HERE / "lsj_index.json"
OUTPUT_LATIN_FREQS = HERE / "latin_morph_freqs.pkl"
OUTPUT_LS          = HERE / "ls_index.json"

# ---------------------------------------------------------------------------
# Shared constants (must stay in sync with main.py)
# ---------------------------------------------------------------------------

FEATURE_TAGS = frozenset({
    "lemma", "pos", "person", "number", "tense", "mood",
    "voice", "gender", "case", "degree", "dialect", "feature",
})

# Stable sorted tuple — frozenset iteration is hash-randomized per process,
# so this fixed ordering keeps pickle keys consistent across builds and servers.
_FREQ_TAGS = tuple(sorted(FEATURE_TAGS | {"form"}))

# ---------------------------------------------------------------------------
# Beta Code / Unicode helpers
# ---------------------------------------------------------------------------

_GREEK_LETTER_TO_BETA: Dict[str, str] = {
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z",
    "η": "h", "θ": "q", "ι": "i", "κ": "k", "λ": "l", "μ": "m",
    "ν": "n", "ξ": "c", "ο": "o", "π": "p", "ρ": "r", "σ": "s",
    "ς": "s", "τ": "t", "υ": "u", "φ": "f", "χ": "x", "ψ": "y",
    "ω": "w",
}

_COMBINING_TO_BETA: Dict[str, str] = {
    "̓": ")",  # smooth breathing
    "̔": "(",  # rough breathing
    "́": "/",  # acute
    "̀": "\\", # grave
    "͂": "=",  # circumflex
    "ͅ": "|",  # iota subscript
    "̈": "+",  # diaeresis
}


def _is_unicode_greek(text: str) -> bool:
    return any("Ͱ" <= c <= "Ͽ" or "ἀ" <= c <= "῿" for c in text)


def _unicode_to_betacode(text: str) -> str:
    result = []
    for char in unicodedata.normalize("NFD", text):
        lower = char.lower()
        if lower in _GREEK_LETTER_TO_BETA:
            if char != lower:
                result.append("*")
            result.append(_GREEK_LETTER_TO_BETA[lower])
        elif char in _COMBINING_TO_BETA:
            result.append(_COMBINING_TO_BETA[char])
        else:
            result.append(char)
    return "".join(result)


def _normalize_greek(form: str) -> str:
    form = form.replace("\\", "/")
    form = re.sub(r"([/=].*)\/", r"\1", form, count=1)
    form = re.sub(r"[\[\]]", "", form)
    return form


def _greek_key(form: str) -> str:
    return _normalize_greek(form).replace("*", "").lower()


# ---------------------------------------------------------------------------
# Morph index
# ---------------------------------------------------------------------------

def _build_morph_index(xml_path: Path, key_fn) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    current: dict[str, str] = {}
    all_tags = FEATURE_TAGS | {"form"}

    for event, elem in ET.iterparse(xml_path, events=("start", "end")):
        if event == "start" and elem.tag == "analysis":
            current = {}
        elif event == "end" and elem.tag == "analysis":
            if "form" in current:
                index[key_fn(current["form"])].append(
                    {k: v for k, v in current.items() if k != "form"}
                )
            elem.clear()
        elif event == "end" and elem.tag in all_tags and elem.text:
            current[elem.tag] = elem.text.strip()

    return dict(index)


def _get_parses(form: str, index: dict, lang: str) -> list[dict] | None:
    if lang == "grc":
        key = _unicode_to_betacode(form) if _is_unicode_greek(form) else form
        key = _greek_key(key)
    else:
        key = form.lower()
    return index.get(key)


# ---------------------------------------------------------------------------
# TEI token extraction
# ---------------------------------------------------------------------------

def _parse_tei_tokens(tei_file: Path) -> list[str]:
    try:
        tree = ET.parse(tei_file)
    except ET.ParseError:
        return []
    root = tree.getroot()
    body = root.find(".//{http://www.tei-c.org/ns/1.0}body")
    if body is None:
        return []
    words = []
    for elem in body.iter():
        if elem.text and elem.text.strip():
            words.extend(re.split(r"\s+", elem.text.strip()))
    return words


# ---------------------------------------------------------------------------
# Frequency table build
# ---------------------------------------------------------------------------

def build_morph_frequencies(corpus_dir: Path, morph_index: dict, lang: str) -> dict[tuple, float]:
    counts: dict[tuple, float] = defaultdict(float)
    xml_files = [f for f in corpus_dir.glob("**/*.xml") if "__cts__" not in f.name]

    for tei_file in tqdm(xml_files, desc=f"Building {lang} frequencies"):
        tokens = _parse_tei_tokens(tei_file)
        for token in tokens:
            parses = _get_parses(token, morph_index, lang)
            if not parses:
                continue
            weight = 1.0 / len(parses)
            for parse in parses:
                counts[(lang,) + tuple(parse.get(tag, None) for tag in _FREQ_TAGS)] += weight

    return dict(counts)


# ---------------------------------------------------------------------------
# Dictionary indexes
# ---------------------------------------------------------------------------

class Sense(BaseModel):
    id: str
    n: str
    level: int
    parent_id: str | None
    translation: str | None
    text: str


class DictionaryEntry(BaseModel):
    key: str
    headword: str
    etymology: str | None
    senses: list[Sense]


def build_lsj_index(dict_xml_path: Path) -> dict[str, DictionaryEntry]:
    """LSJ Greek lexicon — entries use <entry>, keyed by Unicode headword."""
    index: dict[str, DictionaryEntry] = {}
    soup = BeautifulSoup(open(dict_xml_path, encoding="utf-8"), "lxml")

    for i, entry in enumerate(tqdm(soup.find_all("entry"), desc="Indexing LSJ")):
        orth_tag = entry.find("orth")
        if not orth_tag:
            continue
        headword = orth_tag.text.strip()
        key = headword.lower()
        etymology_tag = entry.find("etym")
        etymology = etymology_tag.text.strip() if etymology_tag else None

        senses = []
        for s in entry.find_all("sense"):
            sense_id = s.get("id", f"sense_{i}")
            n = s.get("n", "")
            level = int(s.get("level", 1))
            parent_id = sense_id.rsplit(".", 1)[0] if "." in sense_id else None
            tr_tag = s.find("tr")
            translation = tr_tag.text.strip() if tr_tag else None
            senses.append(Sense(
                id=sense_id, n=n, level=level,
                parent_id=parent_id, translation=translation, text=str(s),
            ))

        index[key] = DictionaryEntry(key=key, headword=headword, etymology=etymology, senses=senses)

    return index


def build_latin_index(dict_xml_path: Path) -> dict[str, DictionaryEntry]:
    """Lewis & Short Latin lexicon — entries use <entryFree>.

    The key attribute on <entryFree> holds the clean ASCII lemma (no macrons,
    no hyphens) that aligns with the Morpheus Latin lemma spellings, so it is
    used as the index key. The <orth> text is kept as the display headword.
    """
    index: dict[str, DictionaryEntry] = {}
    # lxml's XML parser cannot resolve the external DTD entities in this file,
    # so we use the HTML parser which tolerates them.
    soup = BeautifulSoup(open(dict_xml_path, encoding="utf-8"), "lxml")

    for i, entry in enumerate(tqdm(soup.find_all("entryfree"), desc="Indexing L&S")):
        orth_tag = entry.find("orth")
        if not orth_tag:
            continue
        headword = orth_tag.text.strip()
        key = entry.get("key", headword).lower()
        etymology_tag = entry.find("etym")
        etymology = etymology_tag.text.strip() if etymology_tag else None

        senses = []
        for s in entry.find_all("sense"):
            sense_id = s.get("id", f"sense_{i}")
            n = s.get("n", "")
            level = int(s.get("level", 1))
            parent_id = sense_id.rsplit(".", 1)[0] if "." in sense_id else None
            tr_tag = s.find("tr")
            translation = tr_tag.text.strip() if tr_tag else None
            senses.append(Sense(
                id=sense_id, n=n, level=level,
                parent_id=parent_id, translation=translation, text=str(s),
            ))

        index[key] = DictionaryEntry(key=key, headword=headword, etymology=etymology, senses=senses)

    return index


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Greek ===")
    print("Building morph index...")
    greek_index = _build_morph_index(GREEK_MORPH_XML, _greek_key)
    print(f"  {len(greek_index):,} unique forms.")

    print("Building corpus frequency table...")
    greek_freqs = build_morph_frequencies(GREEK_CORPUS_DIR, greek_index, "grc")
    print(f"  {len(greek_freqs):,} keys.")
    with open(OUTPUT_GREEK_FREQS, "wb") as f:
        pickle.dump(greek_freqs, f)
    print(f"  Saved → {OUTPUT_GREEK_FREQS}")

    print("Building LSJ index...")
    lsj = build_lsj_index(LSJ_XML)
    print(f"  {len(lsj):,} entries.")
    with open(OUTPUT_LSJ, "w", encoding="utf-8") as f:
        json.dump({k: v.model_dump() for k, v in lsj.items()}, f, ensure_ascii=False, indent=2)
    print(f"  Saved → {OUTPUT_LSJ}")

    print()
    print("=== Latin ===")
    print("Building morph index...")
    latin_index = _build_morph_index(LATIN_MORPH_XML, str.lower)
    print(f"  {len(latin_index):,} unique forms.")

    print("Building corpus frequency table...")
    latin_freqs = build_morph_frequencies(LATIN_CORPUS_DIR, latin_index, "la")
    print(f"  {len(latin_freqs):,} keys.")
    with open(OUTPUT_LATIN_FREQS, "wb") as f:
        pickle.dump(latin_freqs, f)
    print(f"  Saved → {OUTPUT_LATIN_FREQS}")

    print("Building L&S index...")
    ls = build_latin_index(LS_XML)
    print(f"  {len(ls):,} entries.")
    with open(OUTPUT_LS, "w", encoding="utf-8") as f:
        json.dump({k: v.model_dump() for k, v in ls.items()}, f, ensure_ascii=False, indent=2)
    print(f"  Saved → {OUTPUT_LS}")

    print()
    print("Done.")
