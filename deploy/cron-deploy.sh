#!/usr/bin/env bash
#
# cron-deploy.sh — Pull pre-built static pages from GHCR, swap them live
#
# Unlike the old flow, no build ever runs on this host: MinimumViablePerseus's
# build-corpus.yml/build-global.yml (GitHub Actions) freeze the site's pages
# in N parallel URL-hashed shards (each shard covering every corpus, not
# one corpus each — see build-corpus.yml's header comment) plus the four
# corpus-independent pages, and push each as its own OCI artifact to GHCR.
# This script only pulls whichever artifacts have changed and extracts them
# into a staging directory, then swaps it into place as the single BUILD_DIR
# — no CPU-heavy work happens here at all. Shards are disjoint (each page is
# written by exactly one shard), so the extraction order below no longer
# matters the way an overlapping per-corpus split once did.
#
# Environment variables (set these in ENV_FILE or crontab):
#   REGISTRY        GHCR namespace holding the artifacts
#                    (default: ghcr.io/perseusdlcode)
#   SHARDS          space-separated list of shard indices to pull — must
#                   match build-corpus.yml's SHARD_COUNT (0-indexed)
#                   (default: 0 1 2 3 4)
#   ORAS_BIN        path to the oras CLI (default: oras, i.e. on PATH)
#   BUILD_DIR       Directory `serve` bind-mounts; holds the live pages
#                   (default: ./build)
#   STATE_DIR       Directory holding one last-deployed-digest file per
#                   artifact (default: ./state)
#   SEARCH_DIR      Directory `serve` mounts at /search-index/; holds the
#                   corpus search index (default: ./search-index)
#   SEARCH_TAG      Which alias of mvp-search-index to pull (default: latest)
#   CONTAINER_CMD   Container runtime (default: podman; set to docker locally)
#   COMPOSE_PROJECT podman/docker compose project name (default: perseus) —
#                   set this explicitly when running alongside other compose
#                   projects on the same host, so container names don't collide.
#   ENV_FILE        optional file to source for the above
#                   (default: <script dir>/.env)
#   GHCR_USER / GHCR_TOKEN  optional; if set, logs in for private pulls
#
# Single-directory deploy: only one directory (BUILD_DIR) exists at rest —
# no permanent second blue-green copy sitting on disk. Each run that detects
# a changed artifact fully repopulates a throwaway staging directory
# (BUILD_DIR.new) from scratch (not an in-place patch — simpler and safer
# than reconciling per-corpus deletions), validates it, then swaps it in with
# two directory renames and deletes the old content immediately. This trades
# away the old rollback story (there is no previous version kept around to
# flip back to — if the swap-in fails, fix the artifacts and let the next
# tick retry) for not doubling disk usage. There is a brief window between
# the two renames where BUILD_DIR doesn't exist; `serve` is force-recreated
# right after so it picks up the new directory's inode either way.
#
# Intended to run under `flock` every 10 minutes:
#   */10 * * * * /usr/bin/flock -n /home/perseus/deploy.lock /home/perseus/MinimumViablePerseus/deploy/cron-deploy.sh >> /home/perseus/deploy.log 2>&1

set -euo pipefail

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }

# ----- Config -------------------------------------------------------------
ENV_FILE="${ENV_FILE:-$(dirname "$0")/.env}"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

REGISTRY="${REGISTRY:-ghcr.io/perseusdlcode}"
SHARDS="${SHARDS:-0 1 2 3 4 5 6 7 8 9}"
# Which alias of the corpus/global artifacts to pull — main's builds tag
# `latest` (production), dev's tag `staging` (see build-corpus.yml /
# build-global.yml). Staging hosts set TAG=staging.
TAG="${TAG:-latest}"
ORAS_BIN="${ORAS_BIN:-oras}"
STATE_DIR="${STATE_DIR:-./state}"
SEARCH_TAG="${SEARCH_TAG:-latest}"

# Everything compose bind-mounts is passed to it as an absolute path:
# compose resolves a relative one against the compose file's directory (or,
# depending on the podman-compose version, its own working directory), not
# against this script's working directory, where these are created and
# filled -- and a missing mount source stops podman from creating `serve`
# at all.
abspath() {
  local parent
  parent="$(dirname "$1")"
  mkdir -p "$parent"
  echo "$(cd "$parent" && pwd)/$(basename "$1")"
}
export BUILD_DIR="$(abspath "${BUILD_DIR:-./build}")"
export SEARCH_DIR="$(abspath "${SEARCH_DIR:-./search-index}")"
export DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER_CMD="${CONTAINER_CMD:-podman}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-perseus}"

STAGING_DIR="${BUILD_DIR}.new"
OLD_DIR="${BUILD_DIR}.old"

COMPOSE_FILE="${DEPLOY_DIR}/compose.yaml"
COMPOSE="${CONTAINER_CMD} compose -f ${COMPOSE_FILE} -p ${COMPOSE_PROJECT}"

command -v "$ORAS_BIN" >/dev/null 2>&1 || {
  echo "ERROR: oras CLI not found (looked for '${ORAS_BIN}'); see setup-server.sh" >&2
  exit 1
}

# GNU tar's --zstd shells out to an external zstd binary rather than linking
# it in (unlike gzip) — without this check, a missing zstd only surfaces
# deep inside tar's own error output during extraction, well after the
# (large, slow) artifact pull has already completed.
command -v zstd >/dev/null 2>&1 || {
  echo "ERROR: zstd not found on PATH — install it once as root/admin" \
       "(e.g. 'dnf install -y zstd' or 'yum install -y zstd')." >&2
  exit 1
}

mkdir -p "$STATE_DIR" "$SEARCH_DIR"

# ----- Optional registry login (needed only if packages are private) ------
if [ -n "${GHCR_TOKEN:-}" ] && [ -n "${GHCR_USER:-}" ]; then
  echo "$GHCR_TOKEN" | "$ORAS_BIN" login ghcr.io -u "$GHCR_USER" --password-stdin >/dev/null
fi

# ----- Sanity-check SHARDS against what CI actually published --------------
# SHARDS must equal build-corpus.yml's SHARD_COUNT (0..SHARD_COUNT-1) — CI
# publishes that count as its own tiny artifact precisely so a mismatch
# (e.g. SHARD_COUNT bumped in CI without updating every deploy host's
# SHARDS) is caught loudly here, instead of this host silently serving a
# site that's missing whichever shards it never fetches.
COUNT_TMP="$(mktemp -d)"
if "$ORAS_BIN" pull "${REGISTRY}/mvp-shard-count:${TAG}" -o "$COUNT_TMP" >/dev/null 2>&1; then
  EXPECTED_SHARD_COUNT="$(cat "${COUNT_TMP}/shard-count.txt")"
  # Not `wc -w`: it pads its output with leading whitespace (e.g. "   5"),
  # which would never string-match EXPECTED_SHARD_COUNT's unpadded digits.
  read -ra SHARD_ARR <<< "$SHARDS"
  ACTUAL_SHARD_COUNT="${#SHARD_ARR[@]}"
  if [ "$EXPECTED_SHARD_COUNT" != "$ACTUAL_SHARD_COUNT" ]; then
    rm -rf "$COUNT_TMP"
    echo "ERROR: SHARDS lists ${ACTUAL_SHARD_COUNT} shard(s) but CI published" \
         "${EXPECTED_SHARD_COUNT} for :${TAG} — update SHARDS (this host's" \
         ".env) to match build-corpus.yml's SHARD_COUNT before deploying." >&2
    exit 1
  fi
else
  log "WARN: could not resolve mvp-shard-count:${TAG}; skipping SHARDS sanity check."
fi
rm -rf "$COUNT_TMP"

# ----- Clear out any leftover staging/old dir from a prior failed run -----
rm -rf "${STAGING_DIR:?}" "${OLD_DIR:?}"

# ----- 1. Resolve every artifact's remote digest ---------------------------
remote_digest() {
  "$ORAS_BIN" manifest fetch --descriptor "$1" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['digest'])" 2>/dev/null || echo ""
}

# ----- Corpus search index -------------------------------------------------
# Independent of the page artifacts: mvp-tokenization's build-search-index.yml
# publishes mvp-search-index (search-<sha12>.db + manifest.json) on its own
# schedule, and nginx serves SEARCH_DIR at /search-index/ (deploy/nginx.conf),
# where /search reads it over HTTP range requests. Updated in place rather
# than swapped like BUILD_DIR, because the database file is content-
# addressed: the new one is moved in under its own name, then manifest.json
# -- the only file clients resolve it through -- is replaced atomically. The
# database it replaced stays one more round, so a page that loaded the old
# manifest a moment ago can finish its queries; anything older is pruned.
#
# set -e doesn't apply inside a function called from `||`, hence the
# explicit `|| return 1`s.
sync_search_index() {
  local ref="${REGISTRY}/mvp-search-index:${SEARCH_TAG}"
  local digest last incoming db expected actual previous name
  digest="$(remote_digest "$ref")"
  if [ -z "$digest" ]; then
    log "WARN: could not resolve ${ref}; leaving the search index as is."
    return 0
  fi
  last="$(cat "${STATE_DIR}/search-index.digest" 2>/dev/null || echo "")"
  [ "$digest" = "$last" ] && return 0

  log "New search index: ${ref} (${digest:0:19}...)"
  # Inside SEARCH_DIR so the final mv is a rename on the same filesystem.
  incoming="$(mktemp -d "${SEARCH_DIR}/.incoming.XXXXXX")" || return 1
  "$ORAS_BIN" pull "${REGISTRY}/mvp-search-index@${digest}" -o "$incoming" || { rm -rf "$incoming"; return 1; }
  read -r db expected < <(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["db"], m["size"])' "${incoming}/manifest.json") \
    || { rm -rf "$incoming"; return 1; }
  if ! [[ "$db" =~ ^search-[0-9a-f]{12}\.db$ ]] || [ ! -f "${incoming}/${db}" ]; then
    log "ERROR: search index artifact has no database matching its manifest (${db}); not installing it."
    rm -rf "$incoming"
    return 1
  fi
  actual="$(wc -c < "${incoming}/${db}" | tr -d ' ')"
  if [ "$actual" != "$expected" ]; then
    log "ERROR: ${db} is ${actual} bytes, manifest says ${expected}; not installing it."
    rm -rf "$incoming"
    return 1
  fi

  previous="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["db"])' "${SEARCH_DIR}/manifest.json" 2>/dev/null || echo "")"
  mv "${incoming}/${db}" "${SEARCH_DIR}/${db}" || return 1
  mv "${incoming}/manifest.json" "${SEARCH_DIR}/manifest.json" || return 1
  rm -rf "$incoming"
  for f in "${SEARCH_DIR}"/search-*.db; do
    name="$(basename "$f")"
    if [ "$name" != "$db" ] && [ "$name" != "$previous" ]; then
      rm -f "$f"
    fi
  done
  echo "$digest" > "${STATE_DIR}/search-index.digest"
  log "Search index now ${db}."
}

# serve's /search-index/ mount (and nginx.conf) arrived with this feature, so
# a container created before it has neither: recreate it once. Tracked apart
# from the index digest, so a failed recreate is retried on the next tick
# (without pulling the index again) instead of leaving serve down until the
# next page deploy.
ensure_search_mount() {
  [ -f "${STATE_DIR}/serve-search-mount" ] && return 0
  log "Recreating serve to add the /search-index/ mount..."
  ${COMPOSE} up -d --force-recreate serve || return 1
  touch "${STATE_DIR}/serve-search-mount"
}

rm -rf "${SEARCH_DIR:?}"/.incoming.*
sync_search_index || log "WARN: search index update failed; will retry next tick."
ensure_search_mount || log "ERROR: could not recreate serve with the /search-index/ mount; will retry next tick."

# ----- Static pages ---------------------------------------------------------
ARTIFACT_NAMES=()
ARTIFACT_REFS=()
for shard in $SHARDS; do
  ARTIFACT_NAMES+=("shard-${shard}")
  ARTIFACT_REFS+=("${REGISTRY}/mvp-shard-${shard}:${TAG}")
done
ARTIFACT_NAMES+=("global")
ARTIFACT_REFS+=("${REGISTRY}/mvp-global:${TAG}")

CHANGED=0
declare -A NEW_DIGEST
for i in "${!ARTIFACT_NAMES[@]}"; do
  name="${ARTIFACT_NAMES[$i]}"
  ref="${ARTIFACT_REFS[$i]}"
  digest="$(remote_digest "$ref")"
  if [ -z "$digest" ]; then
    log "WARN: could not resolve digest for ${ref}; will retry next tick."
    exit 0
  fi
  NEW_DIGEST[$name]="$digest"
  last="$(cat "${STATE_DIR}/${name}.digest" 2>/dev/null || echo "")"
  if [ "$digest" != "$last" ]; then
    log "New artifact: ${ref} (${digest:0:19}...)"
    CHANGED=1
  fi
done

if [ "$CHANGED" -eq 0 ]; then
  log "No new artifacts (all digests unchanged)."
  exit 0
fi

# ----- 2. Fully populate a staging directory --------------------------------
# A clean build from scratch, not an in-place patch: every artifact is
# re-extracted every time anything changed, not just the changed one(s).
# Simpler and safer than reconciling per-corpus deletions (e.g. a text
# removed from a corpus leaving an orphaned page behind), and cheap even for
# unchanged artifacts — GHCR's own digest-addressed storage means an
# unchanged pull transfers no new bytes, just re-extracts what's already
# local to the registry cache.
log "Populating staging directory ${STAGING_DIR}..."
mkdir -p "${STAGING_DIR}"

PULL_TMP="$(mktemp -d)"
trap 'rm -rf "$PULL_TMP"' EXIT

for shard in $SHARDS; do
  name="shard-${shard}"
  # Pull by the digest resolved in step 1, not by "$TAG" again: the mutable
  # tag can move between that resolution and this pull (CI can push at any
  # time), which would otherwise extract content newer than what gets
  # recorded to STATE_DIR — silently desyncing "what's live" from "what we
  # think is live" until the next unrelated change papers over it.
  ref="${REGISTRY}/mvp-shard-${shard}@${NEW_DIGEST[$name]}"
  log "Pulling ${ref}..."
  "$ORAS_BIN" pull "$ref" -o "${PULL_TMP}/shard-${shard}"
  tar --zstd -xf "${PULL_TMP}/shard-${shard}/pages.tar.zst" -C "$STAGING_DIR"
  # Free this shard's compressed artifact immediately rather than waiting
  # for the EXIT trap — otherwise every shard pulled so far sits fully
  # resident in PULL_TMP for the rest of the run, on top of the still-live
  # BUILD_DIR and the staging directory's own growing content, which can
  # exhaust disk well before either alone would.
  rm -rf "${PULL_TMP:?}/shard-${shard}"
done

GLOBAL_REF="${REGISTRY}/mvp-global@${NEW_DIGEST[global]}"
log "Pulling ${GLOBAL_REF}..."
"$ORAS_BIN" pull "$GLOBAL_REF" -o "${PULL_TMP}/global"
tar --zstd -xf "${PULL_TMP}/global/global.tar.zst" -C "$STAGING_DIR"
rm -rf "${PULL_TMP:?}/global"

# ----- 3. Validate before swapping it in ------------------------------------
# A best-effort content sanity check, not a full smoke test (the staging
# directory isn't served yet, so it can't be curl'd) — catches an obviously
# corrupt/partial pull (missing global index, or a shard silently truncated)
# before it goes live, rather than only after users notice.
log "Validating ${STAGING_DIR} before swapping it in..."
if [ ! -f "${STAGING_DIR}/index.html" ]; then
  log "ERROR: ${STAGING_DIR}/index.html missing after extraction — refusing to swap it in."
  exit 1
fi

NEW_FILE_COUNT="$(find "$STAGING_DIR" -type f | wc -l)"
OLD_FILE_COUNT=0
[ -d "$BUILD_DIR" ] && OLD_FILE_COUNT="$(find "$BUILD_DIR" -type f | wc -l)"
# A from-scratch build landing at less than half the currently-live file
# count almost certainly means a corrupt/partial pull, not a real shrink of
# the corpus — refuse to serve it rather than regressing the live site.
if [ "$OLD_FILE_COUNT" -gt 0 ] && [ "$NEW_FILE_COUNT" -lt $((OLD_FILE_COUNT / 2)) ]; then
  log "ERROR: ${STAGING_DIR} has ${NEW_FILE_COUNT} files, well below the" \
      "${OLD_FILE_COUNT} currently live — refusing to swap it in."
  exit 1
fi

# ----- 4. Swap staging directory into place, restart serve, write state -----
# Two renames rather than an in-place rsync: renames are atomic per-directory
# and don't require an extra tool, at the cost of a brief window (between the
# two renames) where BUILD_DIR doesn't exist. The old content is deleted
# immediately after — this deploy keeps only one directory on disk at rest,
# not a permanent second copy.
log "Swapping ${STAGING_DIR} -> ${BUILD_DIR}..."
rm -rf "${OLD_DIR:?}"
[ -d "$BUILD_DIR" ] && mv "$BUILD_DIR" "$OLD_DIR"
mv "$STAGING_DIR" "$BUILD_DIR"
rm -rf "${OLD_DIR:?}"

log "Restarting serve..."
${COMPOSE} up -d --force-recreate serve

for name in "${ARTIFACT_NAMES[@]}"; do
  echo "${NEW_DIGEST[$name]}" > "${STATE_DIR}/${name}.digest"
done
log "Deploy complete."
