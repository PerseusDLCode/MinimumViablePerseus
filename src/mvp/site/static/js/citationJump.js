// "Jump to a citation" box (Perseus/MinimumViablePerseus#169): parses input
// like "Thuc. 5.4" or "Soph. Aj. 100" against /citation-index.json (a
// filtered view of the citation_resolution gazetteer -- see
// mvp.site.abbreviations) and redirects to the passage, preferring a
// source-language edition per the issue's default-behavior request. When
// the leading abbreviation names more than one author/work, or a
// multi-work author is cited without a specific work, it lists the
// candidates instead of guessing.
//
// The matching step (mirrors, in a deliberately simplified single-shot
// form, citation_resolution.tei_cts_linker's segment()/match()/
// ScopeParser) only ever produces a *target* -- a work URN plus the
// passage as typed. Turning a target into a URL is a separate, async
// step: this site is frozen to static files, so a URL only resolves if
// some chunk's own citation exactly matches it, and chunking granularity
// varies per work (Thucydides chunks at book.chapter.section; a typed
// "Thuc. 5.4" names only the chapter). /urn:cts:.../chunks.json ships
// that version's real chunk boundaries so the browser can find the same
// "floor" chunk mvp.site.toc._find_chunk_for_line would server-side,
// instead of ever linking to a passage that was never actually built.

const LANGUAGE_PREFERENCE = ['grc', 'lat'];
const MAX_LEADING_TOKENS = 3;
const SCOPE_RE = /^([0-9]+(?:\.[0-9]+)*[a-z]?)(?:[-–—]([0-9]+(?:\.[0-9]+)*[a-z]?))?\.?$/;

function pickLanguage(versions) {
    for (const lang of LANGUAGE_PREFERENCE) {
        if (versions[lang]) return lang;
    }
    const nonEng = Object.keys(versions).filter((l) => l !== 'eng');
    if (nonEng.length) return nonEng.sort()[0];
    const langs = Object.keys(versions);
    return langs.length ? langs.sort()[0] : null;
}

function normalizeScope(raw) {
    const trimmed = raw.trim().replace(/[.,;]+$/, '');
    if (!trimmed) return null;
    const m = SCOPE_RE.exec(trimmed);
    if (!m) return null;
    return m[1]; // land on the range's start
}

function findWorkAbbrev(rec, piece) {
    for (const [workUrn, work] of Object.entries(rec.works)) {
        if (work.title_abbrevs.includes(piece)) return workUrn;
    }
    return null;
}

// Returns { n, tgUrns } for the longest leading-token span that matches at
// least one textgroup's name_abbrevs, or null if nothing matches.
function findAuthorCandidates(tokens, index) {
    const max = Math.min(MAX_LEADING_TOKENS, tokens.length);
    for (let n = max; n >= 1; n--) {
        const piece = tokens.slice(0, n).join(' ');
        const tgUrns = Object.keys(index).filter((tg) =>
            index[tg].name_abbrevs.includes(piece)
        );
        if (tgUrns.length) return { n, tgUrns };
    }
    return null;
}

/**
 * Resolve one citation string against the citation index into targets
 * ({ workUrn, passage }, passage possibly null) -- no I/O, no URL-building.
 *
 * Returns one of:
 *   { kind: 'resolved', target }
 *   { kind: 'choose-work', name, options: [{ label, target }] }
 *   { kind: 'ambiguous', options: [{ label, target }] }
 *   { kind: 'not-found' }
 */
function matchCitation(text, index) {
    const tokens = text.trim().split(/\s+/).filter(Boolean);
    if (!tokens.length) return { kind: 'not-found' };

    const authorMatch = findAuthorCandidates(tokens, index);
    if (!authorMatch) return { kind: 'not-found' };

    const remaining = tokens.slice(authorMatch.n);
    const workMatches = [];
    for (const tg of authorMatch.tgUrns) {
        const rec = index[tg];
        const maxN = Math.min(MAX_LEADING_TOKENS, remaining.length);
        for (let n = maxN; n >= 1; n--) {
            const piece = remaining.slice(0, n).join(' ');
            const workUrn = findWorkAbbrev(rec, piece);
            if (workUrn) {
                workMatches.push({ tg, workUrn, scopeTokens: remaining.slice(n) });
                break;
            }
        }
    }

    const distinctWorks = new Set(workMatches.map((m) => m.workUrn));
    if (distinctWorks.size === 1) {
        const m = workMatches[0];
        const passage = normalizeScope(m.scopeTokens.join(' '));
        return { kind: 'resolved', target: { workUrn: m.workUrn, passage } };
    } else if (distinctWorks.size > 1) {
        return {
            kind: 'ambiguous',
            options: workMatches.map((m) => ({
                label: index[m.tg].name + ', ' + index[m.tg].works[m.workUrn].title,
                target: {
                    workUrn: m.workUrn,
                    passage: normalizeScope(m.scopeTokens.join(' ')),
                },
            })),
        };
    }

    // No work token consumed: fall back to each candidate author's default
    // work (a bare "Thuc. 5.4"-style citation), or list choices.
    const withDefault = authorMatch.tgUrns.filter((tg) => index[tg].default_work_urn);
    if (withDefault.length === 1) {
        const tg = withDefault[0];
        const passage = normalizeScope(remaining.join(' '));
        return {
            kind: 'resolved',
            target: { workUrn: index[tg].default_work_urn, passage },
        };
    }

    if (authorMatch.tgUrns.length === 1) {
        // Single author, multiple works, nothing in the input picked one:
        // let the reader choose, carrying the typed scope onto each work.
        const rec = index[authorMatch.tgUrns[0]];
        const passage = normalizeScope(remaining.join(' '));
        const options = Object.entries(rec.works).map(([workUrn, work]) => ({
            label:
                work.title + (work.title_abbrevs.length ? ' (' + work.title_abbrevs[0] + ')' : ''),
            target: { workUrn, passage },
        }));
        if (options.length) return { kind: 'choose-work', name: rec.name, options };
    }

    // Multiple candidate authors and no way to narrow further.
    const options = authorMatch.tgUrns.map((tg) => {
        const rec = index[tg];
        const workUrn = rec.default_work_urn || Object.keys(rec.works)[0];
        return { label: rec.name, target: { workUrn, passage: null } };
    });
    if (options.length) return { kind: 'ambiguous', options };

    return { kind: 'not-found' };
}

function startKey(passage) {
    return passage
        .split('-', 1)[0]
        .split('.')
        .map((part) => {
            const m = /\d+/.exec(part);
            return m ? parseInt(m[0], 10) : 0;
        });
}

function compareKeys(a, b) {
    const len = Math.min(a.length, b.length);
    for (let i = 0; i < len; i++) {
        if (a[i] !== b[i]) return a[i] - b[i];
    }
    return a.length - b.length;
}

// Given a version's chunk passages, find the chunk a typed citation should
// land on. Two cases, since the typed citation's depth need not match this
// version's chunking depth:
//
// 1. The typed citation is a *prefix* of some chunk's own citation (e.g.
//    "5.4" typed against section-level chunks "5.4.1", "5.4.2", ...): land
//    on the first (lowest-keyed) such chunk -- the start of that chapter,
//    not (as a plain "greatest start <= target" floor would give) the last
//    section of the *previous* chapter.
// 2. No chunk is that fine (e.g. "5.4" typed against book-level chunks
//    "5", "6", ...): fall back to the plain floor -- the greatest chunk
//    start at or before the target, mirroring
//    mvp.site.toc._find_chunk_for_line -- and if even that finds nothing
//    (target precedes every chunk), the first chunk overall (toc.py's own
//    `or chunks[0]` fallback).
function floorChunk(passages, targetPassage) {
    if (!passages.length) return null;
    const targetKey = startKey(targetPassage);

    let prefixBest = null;
    let prefixBestKey = null;
    let floorBest = null;
    let floorBestKey = null;
    for (const p of passages) {
        const key = startKey(p);
        const isPrefixMatch =
            key.length >= targetKey.length &&
            targetKey.every((v, i) => key[i] === v);
        if (isPrefixMatch && (!prefixBestKey || compareKeys(key, prefixBestKey) < 0)) {
            prefixBest = p;
            prefixBestKey = key;
        }
        if (compareKeys(key, targetKey) <= 0 && (!floorBestKey || compareKeys(key, floorBestKey) > 0)) {
            floorBest = p;
            floorBestKey = key;
        }
    }
    return prefixBest || floorBest || passages[0];
}

function citationJump(inputId, buttonId, resultsId) {
    const input = document.getElementById(inputId);
    const button = document.getElementById(buttonId);
    const results = document.getElementById(resultsId);
    if (!input || !button || !results) return;

    let indexPromise = null;
    let urnIndexPromise = null;
    const chunkPromises = new Map(); // base url -> Promise<string[]>

    function loadData() {
        if (!indexPromise) {
            indexPromise = fetch('/citation-index.json').then((r) => r.json());
        }
        if (!urnIndexPromise) {
            urnIndexPromise = fetch('/urn-index.json').then((r) => r.json());
        }
        return Promise.all([indexPromise, urnIndexPromise]);
    }

    function fetchChunkPassages(base) {
        if (!chunkPromises.has(base)) {
            chunkPromises.set(
                base,
                fetch(base + '/chunks.json')
                    .then((r) => (r.ok ? r.json() : []))
                    .catch(() => [])
            );
        }
        return chunkPromises.get(base);
    }

    // { workUrn, passage } -> Promise<string|null>
    function resolveHref(target, urnIndex) {
        const versions = urnIndex[target.workUrn];
        if (!versions) return Promise.resolve(null);
        const lang = pickLanguage(versions);
        if (!lang) return Promise.resolve(null);
        const base = '/urn:cts:' + versions[lang].slice(1); // no trailing slash
        if (!target.passage) return Promise.resolve(base + '/');
        return fetchChunkPassages(base).then((passages) => {
            const chunk = floorChunk(passages, target.passage);
            return base + ':' + (chunk || target.passage) + '/';
        });
    }

    function renderOptions(options, introText) {
        results.innerHTML = '';
        if (introText) {
            const p = document.createElement('p');
            p.className = 'text-sm text-neutral-600 mb-1';
            p.textContent = introText;
            results.appendChild(p);
        }
        const ul = document.createElement('ul');
        ul.className = 'space-y-1';
        options.forEach((opt) => {
            const li = document.createElement('li');
            const a = document.createElement('a');
            a.href = opt.href;
            a.className = 'link text-sm';
            a.textContent = opt.label;
            li.appendChild(a);
            ul.appendChild(li);
        });
        results.appendChild(ul);
    }

    function renderMessage(text) {
        results.innerHTML = '';
        const p = document.createElement('p');
        p.className = 'text-sm text-neutral-600';
        p.textContent = text;
        results.appendChild(p);
    }

    function go() {
        const text = input.value.trim();
        if (!text) return;
        loadData().then(([index, urnIndex]) => {
            const result = matchCitation(text, index);

            if (result.kind === 'resolved') {
                resolveHref(result.target, urnIndex).then((href) => {
                    if (href) {
                        window.location.href = href;
                    } else {
                        renderMessage('No available edition for "' + text + '".');
                    }
                });
                return;
            }

            if (result.kind === 'ambiguous' || result.kind === 'choose-work') {
                Promise.all(
                    result.options.map((opt) =>
                        resolveHref(opt.target, urnIndex).then((href) =>
                            href ? { label: opt.label, href } : null
                        )
                    )
                ).then((resolved) => {
                    const options = resolved.filter(Boolean);
                    if (!options.length) {
                        renderMessage('"' + text + '" is ambiguous, and none of the candidates have an available edition.');
                    } else if (result.kind === 'choose-work') {
                        renderOptions(options, 'Which work by ' + result.name + '?');
                    } else {
                        renderOptions(options, '"' + text + '" could mean:');
                    }
                });
                return;
            }

            renderMessage('No match for "' + text + '".');
        });
    }

    button.addEventListener('click', go);
    input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') go();
    });
}

window.citationJump = citationJump;
