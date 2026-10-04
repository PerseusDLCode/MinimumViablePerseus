import { openMorphDb, openSearchDb } from './search/db.js';
import { guessLang, matchKey } from './search/normalize.js';
import {
    countsByWork,
    describeHits,
    formsByKeys,
    formsByText,
    hitsInWork,
    lemmasByText,
    morphFormKeys,
    morphLemmas,
} from './search/queries.js';

const PAGE = 50;
const CONTEXT_WORDS = 10;
// "All works" walks works in list order to fill a page; stop after this
// many works per click so a rare form scattered across hundreds of works
// doesn't turn one click into hundreds of queries.
const MAX_WORKS_PER_PAGE = 25;

const MODES = ['lemma', 'tagged', 'form'];
const LANGS = ['auto', 'grc', 'la'];
const LANG_ALIASES = { lat: 'la' };

// Alpine component for /search: corpus-wide search of the Greek and Latin
// texts by dictionary lemma (every form Morpheus generates for it, matched
// against the corpus), by lemma as tagged by the lemmatizer, or by exact
// form. Everything runs in the browser against two SQLite files read over
// HTTP range requests: the search index (/search-index/) and
// pdl-morph-server's morph.db. See search/db.js.
export default function corpusSearch(config) {
    // Query state that doesn't need to be reactive.
    let db = null;
    let match = null; // { kind: 'form'|'lemma', ids: [...] }
    let cursor = null; // { workIndex, after: [chunk_id, seq] }

    return {
        q: '',
        mode: 'lemma',
        lang: 'auto',
        loose: false,
        // Set when arriving from pdl-morph-server with an exact headword.
        headword: null,
        seq: null,

        candidates: [], // Morpheus lemmas matching q, each { id, headword, sequence_number, selected }
        forms: [], // matched corpus forms, most frequent first
        works: [],
        total: 0,
        selectedWork: null, // doc_id, or null for all works
        hits: [],
        done: true,

        searching: false,
        loadingMore: false,
        error: '',
        notice: '',
        kbRead: 0,
        searched: false,

        init() {
            const params = new URLSearchParams(window.location.search);
            this.headword = params.get('lemma');
            this.seq = params.get('seq');
            this.q = this.headword || params.get('q') || '';
            if (MODES.includes(params.get('mode'))) this.mode = params.get('mode');
            const lang = LANG_ALIASES[params.get('lang')] || params.get('lang');
            if (LANGS.includes(lang)) this.lang = lang;
            this.loose = params.get('loose') === '1';
            const doc = Number(params.get('doc'));
            this.selectedWork = doc || null;
            if (this.q) this.search({ keepWork: true });
        },

        effectiveLang() {
            return this.lang === 'auto' ? guessLang(this.q) : this.lang;
        },

        submit() {
            // Typing a new query drops the exact headword from pdl-morph-server.
            this.headword = null;
            this.seq = null;
            this.search({ keepWork: false });
        },

        syncUrl() {
            const params = new URLSearchParams();
            if (this.headword) {
                params.set('lemma', this.headword);
                if (this.seq !== null) params.set('seq', this.seq);
            } else {
                params.set('q', this.q);
            }
            if (this.mode !== 'lemma') params.set('mode', this.mode);
            if (this.lang !== 'auto') params.set('lang', this.lang);
            if (this.loose) params.set('loose', '1');
            if (this.selectedWork) params.set('doc', this.selectedWork);
            history.replaceState(null, '', `${window.location.pathname}?${params}`);
        },

        async updateBytes() {
            if (db) this.kbRead = Math.round(await db.bytesRead() / 1024);
        },

        async search({ keepWork }) {
            const q = this.q.trim();
            if (!q) return;
            this.searching = true;
            this.searched = true;
            this.error = this.notice = '';
            this.candidates = [];
            this.forms = [];
            this.works = [];
            this.hits = [];
            this.total = 0;
            if (!keepWork) this.selectedWork = null;
            this.syncUrl();
            try {
                db = await openSearchDb(config.indexUrl);
                const lang = this.effectiveLang();
                if (this.mode === 'lemma') {
                    match = await this.resolveMorpheus(q, lang);
                } else if (this.mode === 'tagged') {
                    match = await this.resolveTagged(q, lang);
                } else {
                    const forms = await formsByText(db, q, lang, this.loose);
                    match = { kind: 'form', ids: forms.map(function (f) { return f.form_id; }) };
                    this.forms = forms.sort(function (a, b) { return b.n - a.n; });
                }
                await this.loadWorks();
            } catch (err) {
                console.error(err);
                this.error = `Search failed: ${err.message || err}`;
            } finally {
                this.searching = false;
                this.updateBytes();
            }
        },

        async resolveTagged(q, lang) {
            const lemmas = await lemmasByText(db, q, lang, this.loose);
            return { kind: 'lemma', ids: lemmas.map(function (l) { return l.lemma_id; }) };
        },

        async resolveMorpheus(q, lang) {
            let candidates;
            try {
                const morph = await openMorphDb(config.morphUrl);
                candidates = await morphLemmas(morph, {
                    text: q, headword: this.headword, seq: this.seq, lang: lang,
                });
            } catch (err) {
                console.warn('morph.db unavailable', err);
                this.notice = 'The morphology database is unavailable, so this shows lemmas as tagged by the lemmatizer instead.';
                return this.resolveTagged(q, lang);
            }
            if (!candidates.length) {
                this.notice = `“${q}” isn't a dictionary headword in Morpheus, so this shows lemmas as tagged by the lemmatizer instead.`;
                return this.resolveTagged(q, lang);
            }
            // morph.db matches headwords ignoring accents, so "ὁ" also finds
            // ὅ, ὀ, ...: start with just the ones accented as typed, if any.
            const key = matchKey(q, lang);
            const exact = candidates.some(function (c) { return matchKey(c.headword, lang) === key; });
            this.candidates = candidates.map(function (c) {
                return { ...c, selected: !exact || matchKey(c.headword, lang) === key };
            });
            return this.resolveMorpheusForms(lang);
        },

        async resolveMorpheusForms(lang) {
            const morph = await openMorphDb(config.morphUrl);
            const ids = this.candidates.filter(function (c) { return c.selected; }).map(function (c) { return c.id; });
            const keys = ids.length ? await morphFormKeys(morph, ids, lang) : [];
            const forms = keys.length ? await formsByKeys(db, keys, lang) : [];
            this.forms = forms.sort(function (a, b) { return b.n - a.n; });
            return { kind: 'form', ids: forms.map(function (f) { return f.form_id; }) };
        },

        async toggleCandidate() {
            this.searching = true;
            this.error = '';
            try {
                match = await this.resolveMorpheusForms(this.effectiveLang());
                await this.loadWorks();
            } catch (err) {
                console.error(err);
                this.error = `Search failed: ${err.message || err}`;
            } finally {
                this.searching = false;
                this.updateBytes();
            }
        },

        async loadWorks() {
            this.works = match.ids.length ? await countsByWork(db, match.kind, match.ids) : [];
            this.total = this.works.reduce(function (sum, w) { return sum + w.n; }, 0);
            const selected = this.selectedWork;
            if (selected && !this.works.some(function (w) { return w.doc_id === selected; })) {
                this.selectedWork = null;
            }
            await this.resetHits();
        },

        async selectWork(docId) {
            this.selectedWork = docId;
            this.syncUrl();
            await this.resetHits();
            this.updateBytes();
        },

        selectedWorks() {
            const selected = this.selectedWork;
            return selected ? this.works.filter(function (w) { return w.doc_id === selected; }) : this.works;
        },

        async resetHits() {
            this.hits = [];
            cursor = { workIndex: 0, after: [0, -1] };
            this.done = !this.works.length;
            await this.loadMore();
        },

        async loadMore() {
            if (this.done || this.loadingMore) return;
            this.loadingMore = true;
            try {
                const works = this.selectedWorks();
                const page = [];
                let visited = 0;
                while (page.length < PAGE && cursor.workIndex < works.length && visited < MAX_WORKS_PER_PAGE) {
                    const work = works[cursor.workIndex];
                    const wanted = PAGE - page.length;
                    const rows = await hitsInWork(db, match.kind, work, cursor.after, wanted);
                    if (rows.length) {
                        const described = await describeHits(db, work, rows, CONTEXT_WORDS);
                        described.forEach(function (hit) { hit.work = work; });
                        page.push(...described);
                        const last = rows[rows.length - 1];
                        cursor.after = [last.chunk_id, last.seq];
                    }
                    if (rows.length < wanted) {
                        cursor.workIndex += 1;
                        cursor.after = [0, -1];
                    }
                    visited += 1;
                }
                this.hits.push(...page);
                this.done = cursor.workIndex >= works.length;
            } catch (err) {
                console.error(err);
                this.error = `Loading results failed: ${err.message || err}`;
            } finally {
                this.loadingMore = false;
                this.updateBytes();
            }
        },

        workLabel(work) {
            return work.author ? `${work.author}, ${work.title || work.base_urn}` : (work.title || work.base_urn);
        },

        candidateLabel(c) {
            return c.sequence_number > 0 ? `${c.headword} (${c.sequence_number})` : c.headword;
        },
    };
}
