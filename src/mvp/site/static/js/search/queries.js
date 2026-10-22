// Queries against the corpus search index (built by mvp-tokenization's
// mvp-index; see build_index.py there for the schema). Every query is shaped to hit a clustered
// primary key or an index, so each one reads a handful of contiguous pages
// over HTTP rather than scanning.

import { looseKey, matchKey } from './normalize.js';

// chunk_context holds each chunk's tokens in windows of CONTEXT_PART,
// separated by TOKEN_SEP (build_index.CONTEXT_PART/TOKEN_SEP).
const TOKEN_SEP = '\x1f';
const CONTEXT_PART = 32;

// Keeps IN (...) lists well under SQLite's bound-parameter limit.
const BATCH = 250;

function batches(items) {
    const out = [];
    for (let i = 0; i < items.length; i += BATCH) out.push(items.slice(i, i + BATCH));
    return out;
}

function marks(n) {
    return new Array(n).fill('?').join(',');
}

async function allIn(db, sqlBefore, ids, sqlAfter, extra) {
    const rows = [];
    for (const batch of batches(ids)) {
        rows.push(...await db.all(
            `${sqlBefore} (${marks(batch.length)}) ${sqlAfter || ''}`,
            [...batch, ...(extra || [])],
        ));
    }
    return rows;
}

function byId(rows, key) {
    const map = new Map();
    rows.forEach(function (row) { map.set(row[key], row); });
    return map;
}

// --- Resolving what the user asked for -----------------------------------

export async function formsByText(db, text, lang, loose) {
    const column = loose ? 'loose' : 'key';
    const key = loose ? looseKey(text, lang) : matchKey(text, lang);
    return db.all(`SELECT form_id, form, n FROM forms WHERE ${column} = ? AND lang = ?`, [key, lang]);
}

export async function lemmasByText(db, text, lang, loose) {
    const column = loose ? 'loose' : 'key';
    const key = loose ? looseKey(text, lang) : matchKey(text, lang);
    return db.all(`SELECT lemma_id, lemma, n FROM lemmas WHERE ${column} = ? AND lang = ?`, [key, lang]);
}

// Morpheus headwords that have forms in the corpus (mvp-index precomputes
// them from pdl-morph-server's morph.db). An exact headword, and maybe a
// sequence number, arrives in links from pdl-morph-server; typed text
// matches headwords ignoring accents.
export async function morphLemmas(db, { text, headword, seq, lang }) {
    const columns = 'morph_id AS id, headword, sequence_number, n';
    if (headword) {
        const params = [headword, lang];
        let sql = `SELECT ${columns} FROM morph_lemmas WHERE headword = ? AND lang = ?`;
        if (seq !== null && seq !== undefined && seq !== '') {
            sql += ' AND sequence_number = ?';
            params.push(Number(seq));
        }
        return db.all(sql, params);
    }
    return db.all(
        `SELECT ${columns} FROM morph_lemmas WHERE loose = ? AND lang = ?
         ORDER BY n DESC, headword, sequence_number LIMIT 25`,
        [looseKey(text, lang), lang],
    );
}

// Every corpus form Morpheus generates for these headwords.
export async function formsByMorphLemmas(db, morphIds) {
    const rows = await allIn(
        db,
        'SELECT form_id, form, n FROM forms WHERE form_id IN (SELECT form_id FROM morph_lemma_forms WHERE morph_id IN',
        morphIds,
        ')',
    );
    return Array.from(byId(rows, 'form_id').values());
}

// Whether the index records which Morpheus headword the tagger chose for
// each word of an ambiguous form (form_postings.morph_id and
// form_doc_counts.morph_id; 0 where it didn't settle it), and Morpheus's
// analyses of each form (morph_analyses). Indexes before schema 3 don't.
export function hasTaggedHeadwords(db) {
    return (db.manifest.schema_version || 0) >= 3 && db.manifest.morph_lemmas > 0;
}

// Every Morpheus headword of each of these forms, with its analyses of the
// form: [{ form_id, morph_id, headword, sequence_number, analyses }].
export async function formAnalyses(db, formIds) {
    return allIn(
        db,
        `SELECT a.form_id, a.morph_id, m.headword, m.sequence_number, a.analyses
         FROM morph_analyses a JOIN morph_lemmas m ON m.morph_id = a.morph_id
         WHERE a.form_id IN`,
        formIds,
    );
}

// A headword search's view of the tagger's choices (null for any other
// search): `ids`, the Morpheus headwords searched for, and `hide`, whether
// to leave out words the tagger assigned to some other headword.
function isOther(headwords, morphId) {
    return Boolean(headwords && morphId && !headwords.ids.includes(morphId));
}

// --- Per-work counts -------------------------------------------------------

// `kind` is 'form' or 'lemma', saying which kind of ids `ids` holds. Each
// work comes back with the subset of `ids` that occur in it, so fetching its
// hits seeks only those (a headword can have hundreds of forms, most of
// which any one work never uses), and with its n_words (every word in it,
// counted like the hits), for relative frequency.
//
// With `headwords` (see isOther), each work's `other` counts the words the
// tagger assigned to another headword; when hiding them, they're left out
// of `n`, and a work with only those drops out. `otherByForm` maps form ids
// to the same count across all works.
export async function countsByWork(db, kind, ids, headwords) {
    const rows = await allIn(
        db,
        `SELECT ${kind}_id AS id, doc_id, ${headwords ? 'morph_id' : '0 AS morph_id'}, n
         FROM ${kind}_doc_counts WHERE ${kind}_id IN`,
        ids,
    );
    const byDoc = new Map();
    const otherByForm = new Map();
    rows.forEach(function (r) {
        const entry = byDoc.get(r.doc_id) || { n: 0, other: 0, ids: [] };
        const other = isOther(headwords, r.morph_id);
        if (other) {
            entry.other += r.n;
            otherByForm.set(r.id, (otherByForm.get(r.id) || 0) + r.n);
        }
        if (!other || !headwords.hide) {
            entry.n += r.n;
            // A form can have several rows per work, one per tagged headword.
            if (!entry.ids.includes(r.id)) entry.ids.push(r.id);
        }
        byDoc.set(r.doc_id, entry);
    });
    const listed = Array.from(byDoc.keys()).filter(function (docId) { return byDoc.get(docId).n > 0; });
    const docs = await allIn(
        db,
        'SELECT doc_id, base_urn, title, author, corpus, first_chunk, last_chunk, n_words FROM documents WHERE doc_id IN',
        listed,
    );
    const works = docs
        .map(function (doc) { return { ...doc, ...byDoc.get(doc.doc_id) }; })
        .sort(function (a, b) { return b.n - a.n || a.doc_id - b.doc_id; });
    let other = 0;
    byDoc.forEach(function (entry) { other += entry.other; });
    return { works: works, other: other, otherByForm: otherByForm };
}

// --- Hits ------------------------------------------------------------------

// One page of hits within one work (as returned by countsByWork), in
// reading order, after `after` ([chunk_id, seq], exclusive). Keyset
// pagination over the clustered primary key: never OFFSET, which would read
// every skipped row. `headwords` is as for countsByWork; each row then has
// `other`, true if the tagger assigned it to another headword.
export async function hitsInWork(db, kind, doc, after, limit, headwords) {
    let only = '';
    const params = [doc.first_chunk, doc.last_chunk, after[0], after[1]];
    if (headwords && headwords.hide) {
        only = `AND morph_id IN (0, ${marks(headwords.ids.length)})`;
        params.push(...headwords.ids);
    }
    const rows = await allIn(
        db,
        `SELECT chunk_id, seq, occ, form_id, lemma_id, feat_id, ${headwords ? 'morph_id' : '0 AS morph_id'}
         FROM ${kind}_postings WHERE ${kind}_id IN`,
        doc.ids,
        `AND chunk_id BETWEEN ? AND ? AND (chunk_id, seq) > (?, ?) ${only} ORDER BY chunk_id, seq LIMIT ?`,
        [...params, limit],
    );
    rows.forEach(function (row) { row.other = isOther(headwords, row.morph_id); });
    // Batched IN lists each return their own sorted page; merge them.
    rows.sort(function (a, b) { return a.chunk_id - b.chunk_id || a.seq - b.seq; });
    return rows.slice(0, limit);
}

function unique(values) {
    return Array.from(new Set(values.filter(function (v) { return v !== null && v !== undefined; })));
}

// The tokens around `seq` in a chunk: { tokens, offset }, where tokens[0]
// is the chunk's token number `offset`.
async function context(db, chunkId, seq, width) {
    const first = Math.floor(Math.max(0, seq - width) / CONTEXT_PART);
    const last = Math.floor((seq + width) / CONTEXT_PART);
    const parts = await db.all(
        'SELECT tokens FROM chunk_context WHERE chunk_id = ? AND part BETWEEN ? AND ? ORDER BY part',
        [chunkId, first, last],
    );
    return {
        tokens: parts.flatMap(function (p) { return p.tokens.split(TOKEN_SEP); }),
        offset: first * CONTEXT_PART,
    };
}

// Context for each of `rows`, in order. Fetched last row first:
// sql.js-httpvfs reads ahead -- up to megabytes at a time -- whenever
// requests walk forward through consecutive pages, which a page of hits in
// reading order otherwise does, though it needs only a page or two per hit.
async function contexts(db, rows, width) {
    const results = new Array(rows.length);
    for (let i = rows.length - 1; i >= 0; i--) {
        results[i] = await context(db, rows[i].chunk_id, rows[i].seq, width);
    }
    return results;
}

// Fill in everything needed to display and cite a page of hits.
export async function describeHits(db, doc, rows, contextWidth) {
    const chunkIds = unique(rows.map(function (r) { return r.chunk_id; }));
    const [chunks, windows, forms, lemmas, feats] = await Promise.all([
        allIn(db, 'SELECT chunk_id, ref FROM chunks WHERE chunk_id IN', chunkIds),
        contexts(db, rows, contextWidth),
        allIn(db, 'SELECT form_id, form FROM forms WHERE form_id IN', unique(rows.map(function (r) { return r.form_id; }))),
        allIn(db, 'SELECT lemma_id, lemma FROM lemmas WHERE lemma_id IN', unique(rows.map(function (r) { return r.lemma_id; }))),
        allIn(db, 'SELECT feat_id, upos, feats FROM feats WHERE feat_id IN', unique(rows.map(function (r) { return r.feat_id; }))),
    ]);
    const chunkById = byId(chunks, 'chunk_id');
    const formById = byId(forms, 'form_id');
    const lemmaById = byId(lemmas, 'lemma_id');
    const featById = byId(feats, 'feat_id');

    return rows.map(function (row, i) {
        const ref = chunkById.get(row.chunk_id).ref;
        const form = formById.get(row.form_id).form;
        const urn = `${doc.base_urn}:${ref}@${form}[${row.occ}]`;
        const { tokens, offset } = windows[i];
        const at = row.seq - offset;
        const hitToken = tokens[at] || form;
        const feat = featById.get(row.feat_id);
        return {
            key: `${row.chunk_id}:${row.seq}`,
            ref: ref,
            urn: urn,
            href: `/${doc.base_urn}:${ref}/?token=${encodeURIComponent(urn)}`,
            before: tokens.slice(Math.max(0, at - contextWidth), at).join(''),
            hit: hitToken.trimEnd(),
            after: (hitToken.endsWith(' ') ? ' ' : '') + tokens.slice(at + 1, at + 1 + contextWidth).join(''),
            lemma: row.lemma_id ? lemmaById.get(row.lemma_id).lemma : null,
            upos: feat ? feat.upos : null,
            feats: feat ? feat.feats : null,
            morph_id: row.morph_id,
            other: row.other,
        };
    });
}
