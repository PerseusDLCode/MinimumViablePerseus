// Opens SQLite databases over HTTP range requests with sql.js-httpvfs
// (vendored; its UMD bundle must already be loaded, defining
// window.createDbWorker). Only the pages a query touches are fetched, never
// the whole file -- the same technique pdl-morph-server uses for morph.db.

const VENDOR = new URL('../vendor/sql-httpvfs/', import.meta.url);

// Both databases use 4096-byte pages; requestChunkSize must match.
const PAGE_SIZE = 4096;

// A runaway query (say, an unanticipated full scan) fails instead of
// quietly downloading a gigabyte.
const MAX_BYTES_TO_READ = 64 * 1024 * 1024;

function toObjects(results) {
    if (!results.length) return [];
    const { columns, values } = results[0];
    return values.map(function (row) {
        const obj = {};
        columns.forEach(function (col, i) { obj[col] = row[i]; });
        return obj;
    });
}

async function open(url) {
    const worker = await window.createDbWorker(
        [{ from: 'inline', config: { serverMode: 'full', requestChunkSize: PAGE_SIZE, url: url } }],
        new URL('sqlite.worker.js', VENDOR).toString(),
        new URL('sql-wasm.wasm', VENDOR).toString(),
        MAX_BYTES_TO_READ,
    );
    return {
        async all(sql, params) {
            return toObjects(await worker.db.exec(sql, params || []));
        },
        async bytesRead() {
            const stats = await worker.worker.getStats();
            return stats ? stats.totalFetchedBytes : 0;
        },
    };
}

let searchDb = null;

// /search-index/manifest.json names the current content-hashed database
// file. The manifest is always revalidated; the database file itself never
// changes once published, so it can be cached indefinitely.
export function openSearchDb(baseUrl) {
    if (!searchDb) {
        searchDb = (async function () {
            const base = new URL(baseUrl, window.location.href);
            const response = await fetch(new URL('manifest.json', base), { cache: 'no-cache' });
            if (response.status === 404) {
                throw new Error(
                    `the search index isn't available on this server (no ${base.pathname}manifest.json). ` +
                    'For local development, build one into ./search-index/ or set SEARCH_INDEX_DIR, then restart mvp-dev.',
                );
            }
            if (!response.ok) throw new Error(`search index manifest: HTTP ${response.status}`);
            const manifest = await response.json();
            const db = await open(new URL(manifest.db, base).toString());
            db.manifest = manifest;
            return db;
        }());
        searchDb.catch(function () { searchDb = null; });
    }
    return searchDb;
}

let morphDb = null;

export function openMorphDb(morphUrl) {
    if (!morphDb) {
        morphDb = open(morphUrl.replace(/\/$/, '') + '/morph.db');
        morphDb.catch(function () { morphDb = null; });
    }
    return morphDb;
}
