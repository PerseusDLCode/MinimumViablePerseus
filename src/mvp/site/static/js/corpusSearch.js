import { loadManifest, openSearchDb } from './search/db.js';
import { guessLang } from './search/normalize.js';
import {
    countsByWork,
    describeHits,
    formsByText,
    hitsInWork,
    lemmasByText,
} from './search/queries.js';

const PAGE = 50;
const CONTEXT_WORDS = 10;
// "All works" walks works in list order to fill a page; stop after this
// many works per click so a rare form scattered across hundreds of works
// doesn't turn one click into hundreds of queries.
const MAX_WORKS_PER_PAGE = 25;

const MODES = ['tagged', 'form'];
const LANGS = ['auto', 'grc', 'la'];
const LANG_ALIASES = { lat: 'la' };
const SORTS = ['count', 'rate'];
// Relative frequency is shown per this many words of the work.
const RATE_PER = 10000;

function rate(work) {
    return work.n_words ? work.n / work.n_words * RATE_PER : 0;
}

// Most occurrences first, or highest relative frequency first; ties go to
// the other measure, then to document order.
function compareWorks(sort) {
    return function (a, b) {
        const byCount = b.n - a.n;
        const byRate = rate(b) - rate(a);
        return (sort === 'rate' ? byRate || byCount : byCount || byRate) || a.doc_id - b.doc_id;
    };
}

// Alpine component for /search: corpus-wide search of the Greek and Latin
// texts by lemma, as tagged by the lemmatizer, or by exact form. Everything
// runs in the browser against the search index (/search-index/), a SQLite
// file read over HTTP range requests; see search/db.js.
export default function corpusSearch(config) {
    // Query state that doesn't need to be reactive.
    let db = null;
    let match = null; // { kind: 'form'|'lemma', ids: [...] }
    let cursor = null; // { workIndex, after: [chunk_id, seq] }

    return {
        q: '',
        mode: 'tagged',
        lang: 'auto',
        loose: true,

        forms: [], // matched corpus forms, most frequent first (exact-form search)
        works: [],
        sort: 'count', // works order: 'count' (occurrences) or 'rate' (per RATE_PER words)
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
        // Description of the search index, from its manifest; empty until
        // (and unless) the manifest loads.
        indexInfo: '',

        init() {
            this.loadIndexInfo();
            const params = new URLSearchParams(window.location.search);
            // pdl-morph-server links here with ?lemma=<headword>.
            this.q = params.get('q') || params.get('lemma') || '';
            if (MODES.includes(params.get('mode'))) this.mode = params.get('mode');
            const lang = LANG_ALIASES[params.get('lang')] || params.get('lang');
            if (LANGS.includes(lang)) this.lang = lang;
            this.loose = params.get('loose') !== '0';
            if (SORTS.includes(params.get('sort'))) this.sort = params.get('sort');
            const doc = Number(params.get('doc'));
            this.selectedWork = doc || null;
            if (this.q) this.search({ keepWork: true });
        },

        async loadIndexInfo() {
            try {
                const m = await loadManifest(config.indexUrl);
                const parts = [];
                if (m.built_at) {
                    const built = new Date(m.built_at).toLocaleDateString(undefined, { dateStyle: 'medium' });
                    parts.push(`Index built ${built}`);
                }
                if (m.documents) parts.push(`${m.documents.toLocaleString()} works`);
                if (m.words) {
                    const words = m.words.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 1 });
                    parts.push(`${words} words`);
                }
                this.indexInfo = parts.join(' · ');
            } catch (err) {
                // A search reports a missing index; nothing to show here.
            }
        },

        effectiveLang() {
            return this.lang === 'auto' ? guessLang(this.q) : this.lang;
        },

        submit() {
            this.search({ keepWork: false });
        },

        syncUrl() {
            const params = new URLSearchParams();
            params.set('q', this.q);
            if (this.mode !== 'tagged') params.set('mode', this.mode);
            if (this.lang !== 'auto') params.set('lang', this.lang);
            if (!this.loose) params.set('loose', '0');
            if (this.sort !== 'count') params.set('sort', this.sort);
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
            this.forms = [];
            this.works = [];
            this.hits = [];
            this.total = 0;
            if (!keepWork) this.selectedWork = null;
            this.syncUrl();
            try {
                db = await openSearchDb(config.indexUrl);
                const lang = this.effectiveLang();
                if (this.mode === 'tagged') {
                    const lemmas = await lemmasByText(db, q, lang, this.loose);
                    match = { kind: 'lemma', ids: lemmas.map(function (l) { return l.lemma_id; }) };
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

        async loadWorks() {
            const works = match.ids.length ? await countsByWork(db, match.kind, match.ids) : [];
            this.works = works.sort(compareWorks(this.sort));
            this.total = this.works.reduce(function (sum, w) { return sum + w.n; }, 0);
            const selected = this.selectedWork;
            if (selected && !this.works.some(function (w) { return w.doc_id === selected; })) {
                this.selectedWork = null;
            }
            await this.resetHits();
        },

        async setSort(sort) {
            if (sort === this.sort) return;
            this.sort = sort;
            this.syncUrl();
            this.works = [...this.works].sort(compareWorks(sort));
            // "All works" lists hits in works order, so it starts over; a
            // single work's hits don't change.
            if (!this.selectedWork) {
                await this.resetHits();
                this.updateBytes();
            }
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

        // Occurrences per RATE_PER words, to two significant digits below
        // 10 so that rare words don't all round to 0.
        rateLabel(work) {
            const r = rate(work);
            return r >= 10
                ? r.toLocaleString(undefined, { maximumFractionDigits: 0 })
                : r.toLocaleString(undefined, { maximumSignificantDigits: 2 });
        },
    };
}
