// Match keys for the corpus search index: a port of mvp-tokenization's
// src/mvp_tokenization/normalize.py, which computed the keys stored in the
// index. The two must agree exactly; tests/data/search_normalization.json
// (a copy of mvp-tokenization's tests/fixtures/normalization.json) is the
// shared contract, checked by tests/test_search_normalize.py.
//
// matchKey keeps accents but erases differences that don't distinguish
// words: case, grave vs. acute, final vs. medial sigma, elision apostrophes,
// and Latin u/v and i/j (and, for Latin, all marks). looseKey also strips
// every accent and breathing.

const APOSTROPHES = new Set(["'", '’', 'ʼ', '᾽', '′', '΄']);
const LATIN_LANGS = new Set(['la', 'lat']);
const MARK = /\p{M}/u;

function fold(text, lang, stripMarks) {
    let out = '';
    for (const ch of text.normalize('NFD')) {
        if (APOSTROPHES.has(ch)) {
            out += "'";
        } else if (MARK.test(ch)) {
            if (stripMarks) continue;
            if (ch === '̀') out += '́';
            else if (ch === '̃') out += '͂';
            else out += ch;
        } else {
            out += ch;
        }
    }
    let folded = out.toLowerCase().replaceAll('ς', 'σ');
    if (LATIN_LANGS.has(lang)) {
        folded = folded.replaceAll('j', 'i').replaceAll('v', 'u');
    }
    return folded.normalize('NFC');
}

export function matchKey(text, lang) {
    return fold(text, lang, LATIN_LANGS.has(lang));
}

export function looseKey(text, lang) {
    return fold(text, lang, true);
}

// morph.db's own lookup normalization (lemmas.headword_normalized): NFD,
// strip combining marks, lowercase -- see pdl-morph-server's
// web/src/morph/language.ts normalizeUnicode.
export function morphNormalize(text) {
    return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

const GREEK = /[Ͱ-Ͽἀ-῿]/u;

export function guessLang(text) {
    return GREEK.test(text) ? 'grc' : 'la';
}
