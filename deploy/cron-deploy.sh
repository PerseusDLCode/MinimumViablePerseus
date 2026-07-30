#!/usr/bin/env bash
#
# cron-deploy.sh — Pull pre-built static pages from GHCR, swap them live
#
# Unlike the old flow, no build ever runs on this host: MinimumViablePerseus's
# build-corpus.yml/build-global.yml (GitHub Actions) freeze each corpus's
# pages and the four corpus-independent pages independently, and push each
# as its own OCI artifact to GHCR. This script only pulls whichever
# artifacts have changed and extracts them into the currently-inactive
# blue-green directory — no CPU-heavy work happens here at all.
#
# Environment variables (set these in ENV_FILE or crontab):
#   REGISTRY        GHCR namespace holding the artifacts
#                    (default: ghcr.io/perseusdlcode)
#   CORPORA         space-separated list of corpus tag_names to pull — must
#                   match the lowercase tag_name values in build-corpus.yml's
#                   matrix, not the case-sensitive corpus directory names
#                   (default: greeklit latinlit first1kgreek)
#   ORAS_BIN        path to the oras CLI (default: oras, i.e. on PATH)
#   BUILD_DIR       Symlink path `serve` mounts; points at whichever of the two
#                   blue-green directories (BUILD_DIR-a / BUILD_DIR-b) is live
#                   (default: ./build)
#   STATE_DIR       Directory holding one last-deployed-digest file per
#                   artifact (default: ./state)
#   CONTAINER_CMD   Container runtime (default: podman; set to docker locally)
#   COMPOSE_PROJECT podman/docker compose project name (default: perseus) —
#                   set this explicitly when running alongside other compose
#                   projects on the same host, so container names don't collide.
#   ENV_FILE        optional file to source for the above
#                   (default: <script dir>/.env)
#   GHCR_USER / GHCR_TOKEN  optional; if set, logs in for private pulls
#
# Rollback strategy: two real directories (BUILD_DIR-a, BUILD_DIR-b) and a
# BUILD_DIR symlink pointing at whichever is currently served. Each run that
# detects a changed artifact fully repopulates the *inactive* directory from
# scratch (not an in-place patch — simpler and safer than reconciling
# per-corpus deletions) and, on success, flips the symlink and force-recreates
# `serve`. On failure, nothing is touched — the live symlink still points at
# the last-good build, so there is no restore step.
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
CORPORA="${CORPORA:-greeklit latinlit first1kgreek}"
ORAS_BIN="${ORAS_BIN:-oras}"
export BUILD_DIR="${BUILD_DIR:-./build}"
STATE_DIR="${STATE_DIR:-./state}"
CONTAINER_CMD="${CONTAINER_CMD:-podman}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-perseus}"

BUILD_A="${BUILD_DIR}-a"
BUILD_B="${BUILD_DIR}-b"

COMPOSE_FILE="$(dirname "$0")/compose.yaml"
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

mkdir -p "$STATE_DIR"

# ----- Optional registry login (needed only if packages are private) ------
if [ -n "${GHCR_TOKEN:-}" ] && [ -n "${GHCR_USER:-}" ]; then
  echo "$GHCR_TOKEN" | "$ORAS_BIN" login ghcr.io -u "$GHCR_USER" --password-stdin >/dev/null
fi

# ----- Ensure blue-green layout exists ---------------------------------
mkdir -p "$BUILD_A" "$BUILD_B"

if [ -e "$BUILD_DIR" ] && [ ! -L "$BUILD_DIR" ]; then
  log "Migrating existing ${BUILD_DIR} directory into blue-green layout..."
  rmdir "$BUILD_A" 2>/dev/null || true
  mv "$BUILD_DIR" "$BUILD_A"
  ln -s "$(basename "$BUILD_A")" "$BUILD_DIR"
elif [ ! -e "$BUILD_DIR" ]; then
  ln -s "$(basename "$BUILD_A")" "$BUILD_DIR"
fi

# ----- Determine active/inactive blue-green directories -----------------
ACTIVE_REAL="$(readlink -f "$BUILD_DIR")"
if [ "$ACTIVE_REAL" = "$(readlink -f "$BUILD_A")" ]; then
  INACTIVE_DIR="$BUILD_B"
else
  INACTIVE_DIR="$BUILD_A"
fi

# ----- 1. Resolve every artifact's remote digest ---------------------------
remote_digest() {
  "$ORAS_BIN" manifest fetch --descriptor "$1" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['digest'])" 2>/dev/null || echo ""
}

ARTIFACT_NAMES=()
ARTIFACT_REFS=()
for corpus in $CORPORA; do
  ARTIFACT_NAMES+=("$corpus")
  ARTIFACT_REFS+=("${REGISTRY}/mvp-corpus-${corpus}:latest")
done
ARTIFACT_NAMES+=("global")
ARTIFACT_REFS+=("${REGISTRY}/mvp-global:latest")

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

# ----- 2. Fully repopulate the inactive slot --------------------------------
# A clean rebuild of the whole slot, not an in-place patch: every artifact
# is re-extracted every time anything changed, not just the changed one(s).
# Simpler and safer than reconciling per-corpus deletions (e.g. a text
# removed from a corpus leaving an orphaned page behind), and cheap even for
# unchanged artifacts — GHCR's own digest-addressed storage means an
# unchanged pull transfers no new bytes, just re-extracts what's already
# local to the registry cache.
log "Rebuilding inactive slot ${INACTIVE_DIR}..."
rm -rf "${INACTIVE_DIR:?}"/*

PULL_TMP="$(mktemp -d)"
trap 'rm -rf "$PULL_TMP"' EXIT

for corpus in $CORPORA; do
  ref="${REGISTRY}/mvp-corpus-${corpus}:latest"
  log "Pulling ${ref}..."
  "$ORAS_BIN" pull "$ref" -o "${PULL_TMP}/${corpus}"
  tar --zstd -xf "${PULL_TMP}/${corpus}/pages.tar.zst" -C "$INACTIVE_DIR"
done

log "Pulling ${REGISTRY}/mvp-global:latest..."
"$ORAS_BIN" pull "${REGISTRY}/mvp-global:latest" -o "${PULL_TMP}/global"
tar --zstd -xf "${PULL_TMP}/global/global.tar.zst" -C "$INACTIVE_DIR"

# ----- 3. Flip symlink, restart serve, write state --------------------------
log "Switching ${BUILD_DIR} -> $(basename "$INACTIVE_DIR")..."
ln -sfn "$(basename "$INACTIVE_DIR")" "$BUILD_DIR"

log "Restarting serve..."
${COMPOSE} up -d --force-recreate serve

for name in "${ARTIFACT_NAMES[@]}"; do
  echo "${NEW_DIGEST[$name]}" > "${STATE_DIR}/${name}.digest"
done
log "Deploy complete."
