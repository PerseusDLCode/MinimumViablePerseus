import Fuse from './vendor/fuse.js';

// Checkbox facets, each named for the URL query parameter that stores it
// and the record field it filters on. Values within one facet are OR'd;
// facets (and the author filter) are AND'd with each other.
const FACETS = ['kind', 'lang', 'corpus'];

const KIND_LABELS = {
    edition: 'Editions',
    translation: 'Translations',
    commentary: 'Commentaries',
};

// Case- and diacritic-insensitive, so "platon" finds "Platón".
function fold(text) {
    return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

function sortedOptions(labels) {
    return Object.entries(labels)
        .map(function ([value, label]) { return { value: value, label: label }; })
        .sort(function (a, b) { return a.label.localeCompare(b.label); });
}

// Alpine component for /collections: the typeahead search plus the facets
// that filter both it and the browsable tree. The tree is rendered by
// Jinja; each version carries data-kind/data-lang, each textgroup
// data-author, each corpus data-corpus, and every level that should
// disappear once it has no matching versions is marked data-facet-group.
export default function collectionsSearch() {
    // Kept out of the returned object so Alpine doesn't wrap thousands of
    // DOM nodes in reactive proxies.
    let records = [];
    let groups = [];
    let fuse = null;

    return {
        selected: { kind: [], lang: [], corpus: [] },
        author: '',
        options: { kind: [], lang: [], corpus: [] },
        counts: { kind: {}, lang: {}, corpus: {} },
        shown: 0,
        total: 0,
        query: '',
        results: [],
        open: false,
        loading: false,
        // Below the lg breakpoint only; the sidebar always shows them.
        filtersOpen: false,

        init() {
            const root = this.$root;
            groups = Array.from(root.querySelectorAll('[data-facet-group]'));
            const langLabels = {};
            const corpusLabels = {};

            records = Array.from(root.querySelectorAll('[data-version]')).map(function (el) {
                const corpus = el.closest('[data-corpus]');
                const ancestors = [];
                for (let node = el.parentElement; node && node !== root; node = node.parentElement) {
                    if (node.hasAttribute('data-facet-group')) ancestors.push(node);
                }
                const lang = el.dataset.lang;
                langLabels[lang] = el.dataset.langLabel || lang || 'Unspecified';
                corpusLabels[corpus.dataset.corpus] = corpus.dataset.corpusLabel;
                return {
                    el: el,
                    groups: ancestors,
                    // A commentary is listed under its own work and under the
                    // work it comments on; its href identifies it in both.
                    key: (el.getAttribute('href') || el.querySelector('a').getAttribute('href')),
                    kind: el.dataset.kind,
                    lang: lang,
                    corpus: corpus.dataset.corpus,
                    author: fold(el.closest('[data-author]').dataset.author),
                };
            });

            this.total = new Set(records.map(function (r) { return r.key; })).size;
            this.options = {
                kind: Object.keys(KIND_LABELS)
                    .filter(function (kind) { return records.some(function (r) { return r.kind === kind; }); })
                    .map(function (kind) { return { value: kind, label: KIND_LABELS[kind] }; }),
                lang: sortedOptions(langLabels),
                // Already in display order, as the tree lists them.
                corpus: Object.entries(corpusLabels).map(function ([value, label]) {
                    return { value: value, label: label };
                }),
            };

            const params = new URLSearchParams(location.search);
            FACETS.forEach(function (facet) { this.selected[facet] = params.getAll(facet); }, this);
            this.author = params.get('author') || '';
            // Don't hide filters that a shared link arrived with.
            this.filtersOpen = this.active();

            this.$watch('selected', () => this.apply());
            this.$watch('author', () => this.apply());
            this.apply();
        },

        // Returns match(record, except), true when a record passes every
        // filter except the facet named by `except` (if any). Facet counts
        // leave out their own facet so that, e.g., ticking "Latin" doesn't
        // zero out every other language's count.
        matcher() {
            const selected = {};
            FACETS.forEach(function (facet) {
                selected[facet] = new Set(this.selected[facet]);
            }, this);
            const author = fold(this.author.trim());
            return function (record, except) {
                return FACETS.every(function (facet) {
                    return facet === except || !selected[facet].size || selected[facet].has(record[facet]);
                }) && (!author || record.author.includes(author));
            };
        },

        apply() {
            const match = this.matcher();
            const visibleGroups = new Set();
            const shownKeys = new Set();
            const keysByFacet = { kind: {}, lang: {}, corpus: {} };

            records.forEach(function (record) {
                const matched = match(record);
                record.el.classList.toggle('hidden', !matched);
                if (matched) {
                    shownKeys.add(record.key);
                    record.groups.forEach(function (group) { visibleGroups.add(group); });
                }
                FACETS.forEach(function (facet) {
                    if (!match(record, facet)) return;
                    const keys = keysByFacet[facet];
                    (keys[record[facet]] = keys[record[facet]] || new Set()).add(record.key);
                });
            });
            groups.forEach(function (group) {
                group.classList.toggle('hidden', !visibleGroups.has(group));
            });

            const counts = {};
            FACETS.forEach(function (facet) {
                counts[facet] = {};
                Object.entries(keysByFacet[facet]).forEach(function ([value, keys]) {
                    counts[facet][value] = keys.size;
                });
            });
            this.counts = counts;
            this.shown = shownKeys.size;
            this.writeUrl();
            this.search();
        },

        writeUrl() {
            const params = new URLSearchParams();
            FACETS.forEach(function (facet) {
                this.selected[facet].forEach(function (value) { params.append(facet, value); });
            }, this);
            if (this.author.trim()) params.set('author', this.author.trim());
            const query = params.toString();
            history.replaceState(null, '', (query ? '?' + query : location.pathname) + location.hash);
        },

        // How many filter values are applied, for the "Show filters" badge.
        activeCount() {
            return (this.author.trim() ? 1 : 0) + FACETS.reduce(function (sum, facet) {
                return sum + this.selected[facet].length;
            }.bind(this), 0);
        },

        active() {
            return this.activeCount() > 0;
        },

        clear() {
            this.selected = { kind: [], lang: [], corpus: [] };
            this.author = '';
        },

        // Loads the search index on first use, then searches.
        onQuery() {
            if (fuse) {
                this.search();
                return;
            }
            if (this.loading) return;
            this.loading = true;
            fetch('/collections/search-index.json')
                .then(function (r) { return r.json(); })
                .then((data) => {
                    data.forEach(function (entry) {
                        entry.facets = {
                            kind: entry.kind,
                            lang: entry.lang,
                            corpus: entry.corpus_id,
                            author: fold(entry.author),
                        };
                    });
                    fuse = new Fuse(data, {
                        keys: ['title', 'author', 'editors'],
                        threshold: 0.3,
                    });
                    this.search();
                })
                .finally(() => {
                    this.loading = false;
                });
        },

        search() {
            const query = this.query.trim();
            if (!fuse || !query) {
                this.results = [];
                return;
            }
            const match = this.matcher();
            this.results = fuse.search(query)
                .map(function (result) { return result.item; })
                .filter(function (entry) { return match(entry.facets); })
                .slice(0, 50);
        },

        resultLabel(entry) {
            let label = entry.title + ' (' + entry.language + ')';
            if (entry.author) label += ' — ' + entry.author;
            if (entry.editors) label += ' — ' + entry.editors;
            return label;
        },
    };
}
