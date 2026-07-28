#!/usr/bin/env bash
#
# cron-deploy.sh — Poll GHCR for new builder image, build on VM
#
# Environment variables (set these in ENV_FILE or crontab):
#   IMAGE           GHCR image (default: ghcr.io/perseusdlcode/minimumviableperseus)
#   MORPH_URL       Morpheus endpoint for the build (required) — this is baked
#                   into the built HTML and fetched by browsers client-side,
#                   so it must be the public morph-server URL, not an
#                   internal/container-network address.
#   BUILD_DIR       Symlink path `serve` mounts; points at whichever of the two
#                   blue-green directories (BUILD_DIR-a / BUILD_DIR-b) is live
#                   (default: ./build)
#   STATE_FILE      Path to last-deployed digest file (default: ./last-digest)
#   BUILD_CTR       Name for the build container (default: perseus-build)
#   IMAGE_TAG       Image tag to poll/build (default: dev-latest)
#   CONTAINER_CMD   Container runtime (default: podman; set to docker locally)
#   COMPOSE_PROJECT podman/docker compose project name (default: perseus) —
#                   set this explicitly when running alongside other compose
#                   projects on the same host, so container names don't collide.
#   ENV_FILE        optional file to source for the above
#                   (default: <script dir>/.env)
#   GHCR_USER / GHCR_TOKEN  optional; if set, logs in for private pulls
#
# Rollback strategy: two real directories (BUILD_DIR-a, BUILD_DIR-b) and a
# BUILD_DIR symlink pointing at whichever is currently served. Each run
# builds into the *inactive* directory (mounted as BUILD_TARGET_DIR) and, on
# success, flips the symlink and force-recreates `serve`. On failure, nothing
# is touched — the live symlink still points at the last-good build, so there
# is no restore step and no full-tree copy on every tick.
#
# Intended to run under `flock` every 10 minutes:
#   */10 * * * * /usr/bin/flock -n /home/perseus/deploy.lock /home/perseus/MinimumViablePerseus/deploy/cron-deploy.sh >> /home/perseus/deploy.log 2>&1

set -euo pipefail

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }

# ----- Config -------------------------------------------------------------
ENV_FILE="${ENV_FILE:-$(dirname "$0")/.env}"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

export IMAGE="${IMAGE:-ghcr.io/perseusdlcode/minimumviableperseus}"
export MORPH_URL="${MORPH_URL:?MORPH_URL is required}"
export BUILD_DIR="${BUILD_DIR:-./build}"
STATE_FILE="${STATE_FILE:-last-digest}"
export BUILD_CTR="${BUILD_CTR:-perseus-build}"
export IMAGE_TAG="${IMAGE_TAG:-dev-latest}"
CONTAINER_CMD="${CONTAINER_CMD:-podman}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-perseus}"

BUILD_A="${BUILD_DIR}-a"
BUILD_B="${BUILD_DIR}-b"

COMPOSE_FILE="$(dirname "$0")/compose.yaml"
COMPOSE="${CONTAINER_CMD} compose -f ${COMPOSE_FILE} -p ${COMPOSE_PROJECT}"
COMPOSE_BUILD="${COMPOSE} --profile build"

# ----- Optional registry login (needed only if the package is private) ----
if [ -n "${GHCR_TOKEN:-}" ] && [ -n "${GHCR_USER:-}" ]; then
  echo "$GHCR_TOKEN" | ${CONTAINER_CMD} login ghcr.io -u "$GHCR_USER" --password-stdin >/dev/null
fi

# ----- Ensure blue-green layout exists ---------------------------------
mkdir -p "$BUILD_A" "$BUILD_B"

if [ -e "$BUILD_DIR" ] && [ ! -L "$BUILD_DIR" ]; then
  # First run after migrating from the old rsync-based layout: adopt the
  # existing plain directory as the "a" slot instead of discarding it.
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
export BUILD_TARGET_DIR="$INACTIVE_DIR"

# ----- 1. Poll remote digest ------------------------------------------
REMOTE_DIGEST=$(${CONTAINER_CMD} manifest inspect "${IMAGE}:${IMAGE_TAG}" 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['manifests'][0]['digest'])" 2>/dev/null \
  || echo "")

if [ -z "$REMOTE_DIGEST" ]; then
  log "WARN: Could not fetch digest for ${IMAGE}:${IMAGE_TAG}; will retry next tick."
  exit 0
fi

# ----- 2. Compare to last deployed digest -----------------------------
if [ -f "$STATE_FILE" ]; then
  LAST_DIGEST=$(cat "$STATE_FILE")
  if [ "$REMOTE_DIGEST" = "$LAST_DIGEST" ]; then
    log "No new image (digest unchanged: ${REMOTE_DIGEST:0:12}...)."
    exit 0
  fi
fi

log "New image detected: ${REMOTE_DIGEST:0:12}..."

# ----- 3. Cancel any running build ------------------------------------
if ${CONTAINER_CMD} ps --format '{{.Names}}' 2>/dev/null | grep -q "^${BUILD_CTR}$"; then
  log "Cancelling running build container ${BUILD_CTR}..."
  ${CONTAINER_CMD} stop "${BUILD_CTR}" 2>/dev/null || true
  ${CONTAINER_CMD} rm "${BUILD_CTR}" 2>/dev/null || true
fi

# ----- 4. Pull new image, prune the one it replaces --------------------
log "Pulling ${IMAGE}:${IMAGE_TAG}..."
${COMPOSE_BUILD} pull build

log "Pruning dangling images..."
${CONTAINER_CMD} image prune -f || true

# ----- 5. Build into the inactive directory -----------------------------
log "Building into inactive slot ${BUILD_TARGET_DIR} via ${BUILD_CTR}..."
BUILD_EXIT=0
${COMPOSE_BUILD} run --rm build || BUILD_EXIT=$?

if [ "$BUILD_EXIT" -ne 0 ]; then
  log "ERROR: Build failed with exit code ${BUILD_EXIT}. Leaving live build (${BUILD_DIR} -> $(readlink "$BUILD_DIR")) untouched; retry next tick."
  exit "$BUILD_EXIT"
fi

log "Build succeeded."

# ----- 6. Flip symlink, restart serve, write state ----------------------
log "Switching ${BUILD_DIR} -> $(basename "$INACTIVE_DIR")..."
ln -sfn "$(basename "$INACTIVE_DIR")" "$BUILD_DIR"

log "Restarting serve..."
${COMPOSE} up -d --force-recreate serve

echo "$REMOTE_DIGEST" > "$STATE_FILE"
log "Deploy complete. Digest written to ${STATE_FILE}."
