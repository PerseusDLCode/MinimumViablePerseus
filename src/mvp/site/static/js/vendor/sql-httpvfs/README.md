# sql.js-httpvfs 0.8.12

Vendored from the npm package's `dist/` (https://github.com/phiresky/sql.js-httpvfs,
Apache-2.0), the same version pdl-morph-server uses. MinimumViablePerseus has no
JavaScript build step, so these are served as-is:

- `index.js` — UMD bundle; loaded with a classic `<script>` tag, it defines
  `window.createDbWorker`.
- `sqlite.worker.js`, `sql-wasm.wasm` — passed to `createDbWorker` by URL.

Used by `/search` (see `../../search/db.js`). To upgrade, copy the same three
files from a newer release and update the version above.
