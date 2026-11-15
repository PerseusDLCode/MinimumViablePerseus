# Legacy Perseus redirect server: implementation plan

A small service that takes the place of the old Perseus (Perseus 4 /
"hopper") on its hostnames and answers old reading-view URLs with a redirect
to the **first page** of the matching edition or translation on the new,
statically generated site (MinimumViablePerseus, "MVP").

Landing on the cited passage is explicitly out of scope: MVP pre-paginates
every text, so the redirect server only needs to identify the right
*version* (or work) and send the reader to its first page.

## Goals and non-goals

**Goals**

- Old links to a text (CTS URN or `Perseus:text:` id, with or without a
  passage) land on the right work, in the right language/tradition, on MVP.
- A renumbered version (`perseus-grc1` → `perseus-grc2`, `perseus-eng3` →
  `perseus-eng4`) still resolves, and never crosses languages.
- No hard-coded knowledge of MVP's URL scheme: every target URL comes from
  MVP's published manifest.
- Measurable coverage: we can say what fraction of real legacy traffic
  resolves.

**Non-goals**

- Deep-linking to the cited passage.
- Hopper's tools: `morph`, `nebrowser`, `entityvote`/`recordentityvote`,
  `wordfreq`, `searchresults`, `definitionlookup`, `resolveform`, etc. These
  make up most raw requests (see "Observed traffic"). The morphology URLs
  are already routed to a separate morph service at the load balancer
  (`/morph/` → morph-serve). Everything else is a plain 404/410 here unless
  decided otherwise.
- Serving any content itself, beyond a small "not found" page.

## Inputs

### 1. `cts-urns.json` (published by MVP)

Served at `<MVP_ORIGIN>/cts-urns.json`. It's regenerated on every MVP deploy
and served with `Cache-Control: no-cache` and
`Access-Control-Allow-Origin: *`. It's built by `_build_cts_urns` in
`src/mvp/site/catalog_tree.py` of the MinimumViablePerseus repo; that
docstring is the authoritative contract.

```json
{
  "schema_version": 1,
  "versions": {
    "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2": {
      "href": "/urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1-1.32/",
      "kind": "edition",
      "language": "grc",
      "experimental": false
    }
  },
  "families": {
    "urn:cts:greekLit:tlg0012.tlg001.perseus-grc": "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2",
    "urn:cts:greekLit:tlg0012.tlg001.perseus-eng": "urn:cts:greekLit:tlg0012.tlg001.perseus-eng3"
  },
  "works": {
    "urn:cts:greekLit:tlg0012.tlg001": [
      "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2",
      "urn:cts:greekLit:tlg0012.tlg001.perseus-grc1",
      "urn:cts:greekLit:tlg0012.tlg001.perseus-eng3"
    ]
  }
}
```

- `versions`: every deployed version URN (including superseded ones that
  are still deployed) → its first page. `href` is root-relative; prefix it
  with `MVP_ORIGIN`.
- `families`: the version URN with its trailing digits stripped → the
  family's newest curated version. Families are split by id prefix, so
  `perseus-eng` and `perseus-grc` are distinct families.
- `works`: work URN → all of its versions, best first (curated before
  experimental, then editions, translations, commentaries, newest first
  within each family).
- `schema_version`: refuse to load a manifest whose version you don't know.
  Keep serving the last good copy and alert.

Every value in `families` and `works` is guaranteed to be a key of
`versions`.

### 2. Perseus-to-CTS mapping spreadsheet

There's an existing spreadsheet mapping Perseus 4 text ids
(`Perseus:text:1999.01.0133`) to CTS URNs. It covers the large majority of
legacy traffic, so it's the most important input after the manifest.

- First, inspect its columns and decide the canonical one-row shape, ideally
  `perseus_id` (`1999.01.0133`), `cts_urn` (version-level if available,
  else work-level), and optionally a language/notes column.
- Check it into the redirect server repo as CSV (converted from the
  spreadsheet with a script, so it can be re-exported). Load it at startup.
  Don't fetch a live spreadsheet at runtime.
- Validate on load: no duplicate `perseus_id`s; every `cts_urn` parses as a
  CTS URN. Report (don't crash on) rows whose URN doesn't resolve against
  the current manifest. That report is the to-do list for fixing the
  spreadsheet or MVP's corpus.
- One Perseus text id is one *version* (e.g. a Greek edition and its
  English translation have different ids). If the spreadsheet only gives
  work URNs, an English-translation id must not resolve to the Greek
  edition. Use the language column if there is one, and treat this as an
  open question otherwise.

### 3. `Perseus:abo:` ids (no table needed)

"Abstract bibliographic object" ids name a *work* and convert mechanically:
`Perseus:abo:tlg,0012,001` → `urn:cts:greekLit:tlg0012.tlg001`. The
namespace comes from the prefix: `tlg` → `greekLit`, `phi` → `latinLit`.
Treat any other prefix as unknown until checked against the manifest. They
resolve through `works[...]`.

## Observed traffic

These counts come from one day of perseus.tufts.edu access logs (24 Aug
2026, about 337k requests; `p4-logs.log` / `p4-logs_requests.log` in the MVP
checkout, which aren't committed). Re-run the analysis on a longer window
before relying on the proportions.

| Shape | Approx. requests | Notes |
|---|---|---|
| Anything containing `Perseus:text:` | ~200k | Mostly tools (`entityvote`, `nebrowser`, …) carrying a `doc=` param; reading views are a small part |
| `/hopper/morph`, `/cgi-bin/morph`, `/texts/morph`, … | ~95k | Out of scope (morph service) |
| `/hopper/text?doc=…` (and `/hopper//text`) | ~4.9k | **Primary target** |
| `/hopper/xmlchunk`, `/hopper/xmltoc`, `/cgi-bin/text`, `/cgi-bin/xmlchunk`, `/cgi-bin/xmltoc` | ~28k | Reading-view fragments/TOCs keyed by `doc=`; worth redirecting the same way |
| `Perseus:abo:` | ~900 | Work-level |
| Anything containing `urn:cts:` | 74 | Small, but the most-cited stable form |

Distinct URL forms to support (examples from the logs):

- `/hopper/text?doc=Perseus:text:1999.01.0133:book=1:card=1`
- `/hopper/text?doc=Perseus%3Atext%3A2001.05.0138%3Achapter%3D4` (encoded;
  the passage part is `key=value` pairs separated by `:`)
- `/hopper/text?doc=urn:cts:greekLit:tlg0003.tlg001.perseus-grc1:4.43.4`
- `/hopper/text?doc=urn:cts:greekLit:tlg0031.tlg003` (work-level)
- `/hopper/text?doc=Perseus:abo:tlg,0012,001`
- `/texts/urn:cts:latinLit:phi1351.phi005.perseus-lat1` and
  `/citations/urn:cts:…` (data.perseus.org-style resolver paths)
- `/hopper/CTS?request=GetPassage&urn=urn:cts:greekLit:tlg0004.tlg001:7.1`
- `/hopper/query?doc=urn:cts:…&search=…` (a search *within* a text; redirect
  to the text and drop the search)
- Malformed but real, so be tolerant:
  `/citations/urn:cts:greekLit:urn:cts:greekLit:tlg0006.tlg002.perseus-eng1`
  (duplicated prefix: use the *last* `urn:cts:`),
  `doc=urn:cts:…perseus-eng1:Perseus:text:1999.01.0160:4:21:4` (CTS URN with
  a Perseus id glued on: prefer the CTS URN), `/hopper%20/text`,
  `/hopper//text`, and absolute URLs in the request line
  (`GET http://www.perseus.tufts.edu/hopper/text?doc=…`).
- `doc=Verg. Ecl. 8.34`: an abbreviated citation. Out of scope for v1, but
  MVP's abbreviation gazetteer (`/citation-index.json`) could resolve these
  later.

## Resolution algorithm

```
resolve(request) -> target URL | None

1. Extract an identifier:
   - normalise the path: percent-decode once, collapse repeated "/",
     strip stray spaces ("/hopper%20/text"), drop scheme+host if present
   - look in, in order: query params doc, urn; then the path itself
     (/texts/<id>, /citations/<id>, /hopper/text/<id>)
   - if the value contains "urn:cts:", take the substring from its LAST
     occurrence → CTS URN candidate; else if it starts with
     "Perseus:text:" or "Perseus:abo:" → Perseus candidate; else → None

2. Perseus:text:<id>[:passage...]
   - perseus_id = the first token after "Perseus:text:" (e.g. 1999.01.0133)
   - cts = spreadsheet[perseus_id]; if missing → None
   - continue at step 3 with cts (it has no passage)

   Perseus:abo:<prefix>,<tg>,<work>
   - cts = urn:cts:<ns(prefix)>:<prefix><tg>.<prefix><work>; step 3

3. CTS URN: split on ":" → ["urn","cts",ns,work_part,(passage...)]
   - version_urn = "urn:cts:{ns}:{work_part}"  (passage dropped)
   - work_part has 3 dot-separated segments (tg.work.version):
       a. versions[version_urn]                          → href
       b. families[re.sub(r"\d+$", "", version_urn)]    → versions[..].href
       c. otherwise → None   (do NOT fall back to works[]: wrong language)
   - work_part has 2 segments (tg.work):
       works[version_urn][0]                              → href
   - otherwise → None

4. Return MVP_ORIGIN + href.
```

Notes:

- Step 3c is deliberate. If a version family doesn't exist (e.g.
  `perseus-ger1` with no German version deployed), sending the reader to the
  Greek edition is worse than a clear "not found". If that turns out to be
  too strict in practice, a later refinement is to match on the language
  token of the version id (`-eng`, `-grc`, `-lat`) among `works[...]`,
  comparing with `versions[...].language`. That's a product decision, not a
  default.
- Prefer non-experimental targets: `families` already does, and `works[…][0]`
  is curated whenever the work has a curated version.
- Keep the resolver a pure function of `(request, manifest, mapping)` so it
  can be unit-tested and replayed against logs without a running server.

## HTTP behaviour

- Resolved: **302** to start with. Switch to 301 once the coverage and
  correctness reports are stable. 301s are cached indefinitely by browsers
  and crawlers, and the manifest changes as texts are added or renumbered.
- Unresolved reading-view URL (one that carried an identifier that didn't
  resolve): 404 with a small HTML page explaining that Perseus has moved,
  with links to `<MVP_ORIGIN>/collections/` and `<MVP_ORIGIN>/search/`. Log
  the identifier (see Observability).
- Out-of-scope hopper tools: 410 Gone (or 404), the same small page. Make
  sure the load balancer keeps routing morphology paths to the morph
  service before this server's catch-all.
- `/` and `/hopper` (no params): 302 to `MVP_ORIGIN/`.
- Drop the original query string from the target; only the identifier
  matters.

## Manifest loading

- Fetch `cts-urns.json` at startup; fail to start if it can't be fetched and
  there's no cached copy on disk.
- Refresh on a timer (MVP's deploy cron runs every 10 minutes, so every 10
  minutes is enough), using `ETag`/`If-Modified-Since` (nginx sends both for
  static files).
- Validate before swapping: parse, check `schema_version`, sanity-check size
  (e.g. refuse a manifest with less than 90% of the previous version count).
  On any failure, keep the previous manifest and log loudly.
- Persist the last good copy to disk, so a restart during an MVP outage
  still works.
- Swap atomically (build the new lookup dicts, then replace a single
  reference).
- `MVP_ORIGIN` comes from config, so the same build can point at staging (the
  `dev` branch, artifacts tagged `staging`) or production (`main`, tagged
  `latest`).

## Implementation suggestions

- Any small web framework is fine. The whole hot path is three dict lookups.
  A single process with in-memory dicts handles this traffic easily. No
  database.
- Layout:
  - `resolver.py` (pure): identifier extraction, Perseus-id/abo conversion,
    CTS resolution.
  - `manifest.py`: fetch, validate, cache, refresh.
  - `mapping.py`: load and validate the spreadsheet CSV.
  - `app.py`: routes and status codes.
  - `tools/replay_logs.py`: see Testing.
- Config: `MVP_ORIGIN`, `MANIFEST_URL` (default
  `MVP_ORIGIN + "/cts-urns.json"`), `MANIFEST_CACHE_PATH`,
  `REFRESH_SECONDS`, `MAPPING_CSV`.
- Health endpoint that reports the manifest's age and version count, and the
  mapping's row count and unresolved-row count.

## Testing

- **Unit tests for the resolver**, driven by a small fixture manifest and
  mapping. Cover every URL form in "Observed traffic", including the
  malformed ones, plus:
  - exact version match wins even when a newer family member exists;
  - `eng3` → `eng4` and `grc3` → `grc2` both resolve within the family;
  - unknown family → None (never another language);
  - work-only URN → first entry of `works`;
  - Perseus id with a passage suffix, encoded and unencoded;
  - Perseus id missing from the mapping → None.
- **Log replay**: a script that reads access logs (Combined Log Format, as in
  `p4-logs.log`), runs every GET through the resolver against the real
  manifest and mapping, and prints:
  - counts by outcome (resolved exact / family / work / unresolved /
    out-of-scope);
  - the top unresolved identifiers, which feed back into fixing the
    spreadsheet or MVP's corpus coverage.

  This is the acceptance test. Agree on a target with the project before
  launch (for example, a minimum share of in-scope reading-view requests
  that resolve).
- **Manifest contract test**: fetch the real staging manifest in CI and
  assert the invariants above (schema version; every `families`/`works`
  value is a `versions` key; every `href` starts with `/`).

## Observability

- Log each request's outcome category and identifier. Don't log query
  strings beyond the identifier, since some legacy URLs carry search terms.
- Keep a periodic count of unresolved identifiers (in-process top-N plus a
  log line is enough), so missing texts surface after launch.

## Open questions

1. What columns does the Perseus-to-CTS spreadsheet have? Are its CTS URNs
   version-level? Does it distinguish an edition from its translation?
2. Which hostnames will this replace (`www.perseus.tufts.edu`,
   `data.perseus.org`, `catalog.perseus.org`?), and does the load balancer
   route morphology paths away before this server sees them?
3. What should unresolved reading-view URLs do: a 404 page, or redirect to
   MVP's collections page or a search for the work?
4. Should `Perseus:text:` ids for non-CTS material (e.g. the 2001.05 and
   2002.02 reference and lexicon collections seen in the logs) map anywhere,
   or count as out of scope?
5. When should redirects move from 302 to 301?
