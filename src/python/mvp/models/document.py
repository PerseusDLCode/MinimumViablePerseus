# mvp/models/document.py
#
# TEIDocument: parses and holds a single TEI source file.
#
# Uses a lenient parser (recover=True) so that malformed corpus files
# are handled gracefully.  Metadata is extracted lazily on first access.

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from mvp.models.core import TEIMetadata
from mvp.constants import NS, XML_BASE

# Mapping from ISO 639-1 (2-letter) to ISO 639-3 (3-letter) codes.
# Generated from the SIL ISO 639-3 registration authority table:
#   https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3.tab
# All 184 entries with an ISO 639-1 Part1 code are included.
_ISO_639_1_TO_3: dict[str, str] = {
    "aa": "aar", "ab": "abk", "ae": "ave", "af": "afr", "ak": "aka",
    "am": "amh", "an": "arg", "ar": "ara", "as": "asm", "av": "ava",
    "ay": "aym", "az": "aze", "ba": "bak", "be": "bel", "bg": "bul",
    "bi": "bis", "bm": "bam", "bn": "ben", "bo": "bod", "br": "bre",
    "bs": "bos", "ca": "cat", "ce": "che", "ch": "cha", "co": "cos",
    "cr": "cre", "cs": "ces", "cu": "chu", "cv": "chv", "cy": "cym",
    "da": "dan", "de": "deu", "dv": "div", "dz": "dzo", "ee": "ewe",
    "el": "ell", "en": "eng", "eo": "epo", "es": "spa", "et": "est",
    "eu": "eus", "fa": "fas", "ff": "ful", "fi": "fin", "fj": "fij",
    "fo": "fao", "fr": "fra", "fy": "fry", "ga": "gle", "gd": "gla",
    "gl": "glg", "gn": "grn", "gu": "guj", "gv": "glv", "ha": "hau",
    "he": "heb", "hi": "hin", "ho": "hmo", "hr": "hrv", "ht": "hat",
    "hu": "hun", "hy": "hye", "hz": "her", "ia": "ina", "id": "ind",
    "ie": "ile", "ig": "ibo", "ii": "iii", "ik": "ipk", "io": "ido",
    "is": "isl", "it": "ita", "iu": "iku", "ja": "jpn", "jv": "jav",
    "ka": "kat", "kg": "kon", "ki": "kik", "kj": "kua", "kk": "kaz",
    "kl": "kal", "km": "khm", "kn": "kan", "ko": "kor", "kr": "kau",
    "ks": "kas", "ku": "kur", "kv": "kom", "kw": "cor", "ky": "kir",
    "la": "lat", "lb": "ltz", "lg": "lug", "li": "lim", "ln": "lin",
    "lo": "lao", "lt": "lit", "lu": "lub", "lv": "lav", "mg": "mlg",
    "mh": "mah", "mi": "mri", "mk": "mkd", "ml": "mal", "mn": "mon",
    "mr": "mar", "ms": "msa", "mt": "mlt", "my": "mya", "na": "nau",
    "nb": "nob", "nd": "nde", "ne": "nep", "ng": "ndo", "nl": "nld",
    "nn": "nno", "no": "nor", "nr": "nbl", "nv": "nav", "ny": "nya",
    "oc": "oci", "oj": "oji", "om": "orm", "or": "ori", "os": "oss",
    "pa": "pan", "pi": "pli", "pl": "pol", "ps": "pus", "pt": "por",
    "qu": "que", "rm": "roh", "rn": "run", "ro": "ron", "ru": "rus",
    "rw": "kin", "sa": "san", "sc": "srd", "sd": "snd", "se": "sme",
    "sg": "sag", "sh": "hbs", "si": "sin", "sk": "slk", "sl": "slv",
    "sm": "smo", "sn": "sna", "so": "som", "sq": "sqi", "sr": "srp",
    "ss": "ssw", "st": "sot", "su": "sun", "sv": "swe", "sw": "swa",
    "ta": "tam", "te": "tel", "tg": "tgk", "th": "tha", "ti": "tir",
    "tk": "tuk", "tl": "tgl", "tn": "tsn", "to": "ton", "tr": "tur",
    "ts": "tso", "tt": "tat", "tw": "twi", "ty": "tah", "ug": "uig",
    "uk": "ukr", "ur": "urd", "uz": "uzb", "ve": "ven", "vi": "vie",
    "vo": "vol", "wa": "wln", "wo": "wol", "xh": "xho", "yi": "yid",
    "yo": "yor", "za": "zha", "zh": "zho", "zu": "zul",
}

# Non-standard language identifiers found in the Perseus corpus.
_NONSTANDARD_LANG: dict[str, str] = {
    "greek":   "grc",
    "latin":   "lat",
    "english": "eng",
    "german":  "deu",
    "french":  "fra",
    "arabic":  "ara",
    "ger": "deu",
    "fre": "fra",
}


def normalize_lang(code: str) -> str:
    """Normalize a language code to ISO 639-3 (3-letter form)."""
    code = code.lower()
    if code in _NONSTANDARD_LANG:
        return _NONSTANDARD_LANG[code]
    if len(code) == 2:
        return _ISO_639_1_TO_3.get(code, code)
    return code


# Human-readable names for BCP 47 / ISO 639-3 language codes.
LANGUAGE_NAMES: dict[str, str] = {
    "lat": "Latin",
    "grc": "Greek",
    "eng": "English",
    "ara": "Arabic",
    "per": "Persian",
    "deu": "German",
    "fra": "French",
    "ita": "Italian",
    "spa": "Spanish",
    "rus": "Russian",
}


class TEIDocument:
    """A parsed TEI source document with lazily-extracted metadata.

    Uses a lenient parser (recover=True) so that malformed corpus files
    are handled gracefully rather than raising XMLSyntaxError.  DTD
    loading and external network access are disabled for security.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        if not self._path.exists():
            raise FileNotFoundError(f"TEI document not found: {self._path}")
        parser = etree.XMLParser(
            recover=True,
            load_dtd=False,
            resolve_entities=False,
            no_network=True,
            remove_comments=False,
        )
        self._tree: etree._ElementTree = etree.parse(str(self._path), parser)
        self._metadata: TEIMetadata | None = None

    @classmethod
    def from_path(cls, path: Path | str) -> TEIDocument:
        return cls(Path(path))

    @property
    def path(self) -> Path:
        return self._path

    @property
    def root(self) -> etree._Element:
        return self._tree.getroot()

    @property
    def tree(self) -> etree._ElementTree:
        return self._tree

    @property
    def metadata(self) -> TEIMetadata:
        if self._metadata is None:
            self._metadata = self._extract_metadata()
        return self._metadata

    # ------------------------------------------------------------------
    # Private

    def _extract_metadata(self) -> TEIMetadata:
        root = self._tree.getroot()
        return TEIMetadata(
            urn=self._extract_urn(root),
            title=self._extract_title(root),
            author=self._extract_author(root),
            language=self._extract_language(root),
            text_type=self._extract_text_type(root),
            source_path=self._path,
        )

    def _extract_urn(self, root: etree._Element) -> str:
        body = root.find(".//tei:text/tei:body", NS)
        if body is not None:
            xml_base = body.get(XML_BASE, "")
            if xml_base.startswith("urn:cts:"):
                return xml_base
        for div in root.findall(".//tei:text//tei:div", NS):
            n = div.get("n", "")
            if n.startswith("urn:cts:"):
                return n
        return ""

    def _extract_title(self, root: etree._Element) -> str:
        title_el = root.find(".//tei:titleStmt/tei:title", NS)
        if title_el is not None and title_el.text:
            return title_el.text.strip()
        return ""

    def _extract_author(self, root: etree._Element) -> str:
        author_el = root.find(".//tei:titleStmt/tei:author", NS)
        if author_el is not None and author_el.text:
            return author_el.text.strip()
        return ""

    def _extract_language(self, root: etree._Element) -> str:
        text_el = root.find("tei:text", NS)
        if text_el is not None:
            lang = text_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
            if lang:
                return normalize_lang(lang)
        lang_el = root.find(".//tei:langUsage/tei:language", NS)
        if lang_el is not None:
            return normalize_lang(lang_el.get("ident", ""))
        return ""

    def _extract_text_type(self, root: etree._Element) -> str:
        text_el = root.find("tei:text", NS)
        if text_el is None:
            return "prose"
        if text_el.find(".//tei:sp", NS) is not None:
            return "drama"
        if text_el.find(".//tei:l", NS) is not None:
            return "verse"
        return "prose"


# Backward-compatible alias — Charles's site/ code imports this name.
# Use TEIDocument directly in new code.
LenientTEIDocument = TEIDocument
