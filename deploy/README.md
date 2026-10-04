# VM Deployment Setup

This directory contains the scripts and configuration for serving the
MinimumViablePerseus static site on your own server. No build ever runs on
this host: `build-corpus.yml`/`build-global.yml` (GitHub Actions) freeze the
site's pages in CI and push them to GHCR as OCI artifacts, tagged by branch
(`main` → `latest`, `dev` → `staging`). `cron-deploy.sh` only pulls whichever
artifacts changed and swaps them live. It also keeps the corpus search index
(`mvp-search-index`, built by mvp-tokenization's `build-search-index.yml`)
current in `SEARCH_DIR`, which nginx serves at `/search-index/` for the
`/search` page.

## Prerequisites

- Podman (on the VM) or Docker (locally), both with the `compose` subcommand
  — only used here to run the `serve` (nginx) container, never to build
  anything
- [`oras`](https://oras.land) CLI, for pulling artifacts from GHCR
- `zstd` on `PATH` (GNU tar's `--zstd` shells out to it)
- `python3`, used to parse `oras manifest fetch`'s JSON output
- Public GHCR packages (or `GHCR_USER`/`GHCR_TOKEN` for private ones)

## Environment variables

| Variable          | Default                    | Description                                                              |
|--------------------|-----------------------------|----------------------------------------------------------------------------|
| `REGISTRY`         | `ghcr.io/perseusdlcode`     | GHCR namespace holding the artifacts                                       |
| `SHARDS`           | `0 1 2 3 4`                 | Space-separated shard indices to pull — must match build-corpus.yml's `SHARD_COUNT` (0-indexed) |
| `TAG`              | `latest`                    | Which branch's alias to pull (`latest` = main/production, `staging` = dev) |
| `ORAS_BIN`         | `oras`                      | Path to the `oras` CLI                                                     |
| `BUILD_DIR`        | `./build`                   | Directory `serve` mounts as the site root; holds the live pages            |
| `STATE_DIR`        | `./state`                   | Directory holding one last-deployed-digest file per artifact               |
| `SEARCH_DIR`       | `./search-index`            | Directory `serve` mounts at `/search-index/`; holds the corpus search index |
| `SEARCH_TAG`       | `latest`                    | Which alias of `mvp-search-index` to pull                                  |
| `CONTAINER_CMD`    | `podman`                    | Container runtime (set to `docker` for local testing)                      |
| `COMPOSE_PROJECT`  | `perseus`                   | podman/docker compose project name — set explicitly if running alongside other compose projects on the same host |
| `ENV_FILE`         | `<script dir>/.env`         | Optional file to source for the above                                      |
| `GHCR_USER` / `GHCR_TOKEN` | *(unset)*            | Optional; if set, logs in to GHCR for private pulls                        |
| `SERVE_CTR`        | `mvp-serve`                 | (compose.yaml) nginx container name                                        |
| `SERVE_PORT`       | `8000`                      | (compose.yaml) host port for nginx                                         |

`BUILD_DIR`, `STATE_DIR` and `SEARCH_DIR` default to paths relative to
wherever the script is invoked from (cron's default working directory is the
user's home), not to the script's own location — set them to absolute paths
in `.env` if that's not what you want.

## One-time setup

```bash
# Clone the repo (cron-deploy.sh expects compose.yaml alongside it)
git clone https://github.com/PerseusDLCode/MinimumViablePerseus /home/perseus/MinimumViablePerseus

# Create the env file
cat > /home/perseus/MinimumViablePerseus/deploy/.env << 'EOF'
CONTAINER_CMD=podman
BUILD_DIR=/home/perseus/build
STATE_DIR=/home/perseus/state
SEARCH_DIR=/home/perseus/search-index
EOF
```

## Cron

Add this line to your crontab (`crontab -e`):

```
*/10 * * * * /usr/bin/flock -n /home/perseus/deploy.lock /home/perseus/MinimumViablePerseus/deploy/cron-deploy.sh >> /home/perseus/deploy.log 2>&1
```

## How it works

1. The nginx serve container is defined declaratively in `compose.yaml`
   and managed via `$CONTAINER_CMD compose`. `nginx.conf` replaces the
   image's stock server config, adding only the `/search-index/` location.
2. Before anything else, the script checks that `SHARDS` has as many entries
   as CI actually published (see "Making the GHCR packages public" below,
   `mvp-shard-count`) and refuses to deploy — loudly, exit 1 — on a
   mismatch, rather than silently serving a site missing whichever shards
   this host never fetches.
3. **Search index.** It resolves `mvp-search-index:$SEARCH_TAG` and, if the
   digest changed, pulls it into `SEARCH_DIR`: the content-addressed
   `search-<sha12>.db` is moved in under its own name, its size is checked
   against `manifest.json`, and then `manifest.json` (the only file the
   browser resolves the database through) is replaced atomically. The
   database it replaced is kept for one more update, so readers mid-session
   aren't cut off; older ones are deleted. This step is independent of the
   pages: a failure here is logged and retried next tick without blocking a
   page deploy, and an index update never redeploys the pages.
4. **Pages.** It resolves the current digest of every shard artifact
   (`mvp-shard-0` … `mvp-shard-N`) and the global-pages artifact
   (`mvp-global`) at `$TAG`, and compares each to what's recorded in
   `STATE_DIR`.
5. If any page digest changed, it repopulates a staging directory
   (`BUILD_DIR.new`) from scratch — never touching the live directory —
   pulling every shard and the global artifact pinned to the digest resolved
   in step 4 (not the mutable tag again, which can move in between).
6. The staging directory is sanity-checked: `index.html` must exist, and its
   file count must not have dropped below half of what's currently live (a
   from-scratch rebuild landing far below that almost always means a
   corrupt/partial pull, not a real shrink of the corpus).
7. On success it's swapped in with two renames (`BUILD_DIR` → `BUILD_DIR.old`,
   `BUILD_DIR.new` → `BUILD_DIR`), the old content is deleted, `serve` is
   force-recreated so its bind mount picks up the new directory, and the new
   digests are recorded. On failure nothing live is touched and the state
   files are left unchanged, so the next tick retries.

Only one copy of the site exists at rest; there's no previous version kept
around to roll back to — fix the artifacts and let the next tick redeploy.

### Reverse proxy

Whatever proxies this host's port must pass `Range` requests through to
`/search-index/` and must not compress those responses (sql.js-httpvfs reads
the database by byte offset). It should route `/morph/` to pdl-morph-server as
before: `/search` also reads `/morph/morph.db` to expand a dictionary headword
into all of its forms.

## Making the GHCR packages public

There's one package per shard (`mvp-shard-0` … `mvp-shard-N`), one manifest
package per shard (`mvp-shard-N-manifest`), `mvp-global`, `mvp-search-index`,
and `mvp-shard-count` (a one-line text artifact recording `SHARD_COUNT`, used to
sanity-check `SHARDS` before every deploy — see "How it works" above). After
the first push of each, go to:

```
https://github.com/orgs/perseusdlcode/packages/container/<package-name>/settings
```

and set visibility to **public** so the VM can pull without authentication.
