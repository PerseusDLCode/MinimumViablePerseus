#!/usr/bin/env bash
#
# cron-deploy.sh — Poll GHCR for new builder image, build on VM
#
# Environment variables (set these in /opt/perseus/env or crontab):
#   IMAGE         GHCR image (default: ghcr.io/perseusdlcode/minimumviableperseus)
#   MORPH_URL     Morpheus endpoint for the build (required)
#   BUILD_DIR     Host directory for build output (default: /opt/perseus/build)
#   BUILD_PREV    Path to previous build snapshot (default: /opt/perseus/build-prev)
#   STATE_FILE    Path to last-deployed digest file (default: /opt/perseus/last-digest)
#   BUILD_CTR     Name for the build container (default: perseus-build)
#   SERVE_PORT    Host port for nginx (default: 8080)
#   CONTAINER_CMD Container runtime (default: docker; set to podman on VM)
#
# Intended to run under `flock` every 10 minutes:
#   */10 * * * * /usr/bin/flock -n /opt/perseus/deploy.lock /opt/perseus/cron-deploy.sh >> /opt/perseus/deploy.log 2>&1

set -euo pipefail

# ----- Configuration defaults -----------------------------------------
IMAGE="${IMAGE:-ghcr.io/perseusdlcode/minimumviableperseus}"
MORPH_URL="${MORPH_URL:?MORPH_URL is required}"
BUILD_DIR="${BUILD_DIR:-build}"
BUILD_PREV="${BUILD_PREV:-build-prev}"
STATE_FILE="${STATE_FILE:-last-digest}"
BUILD_CTR="${BUILD_CTR:-perseus-build}"
SERVE_PORT="${SERVE_PORT:-8080}"
CONTAINER_CMD="${CONTAINER_CMD:-podman}"

COMPOSE_FILE="$(dirname "$0")/compose.yaml"

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }

# ----- Ensure build directory exists -----------------------------------
mkdir -p "$BUILD_DIR"

# ----- 1. Poll remote digest ------------------------------------------
REMOTE_DIGEST=$(${CONTAINER_CMD} manifest inspect "${IMAGE}:dev-latest" 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['config']['digest'])" 2>/dev/null \
  || echo "")

if [ -z "$REMOTE_DIGEST" ]; then
  log "WARN: Could not fetch digest for ${IMAGE}:dev-latest; will retry next tick."
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

log "New image detected: ${REMOTE_DIGEST:0:12}... (was ${LAST_DIGEST:0:12:-})."

# ----- 3. Cancel any running build ------------------------------------
if ${CONTAINER_CMD} ps --format '{{.Names}}' 2>/dev/null | grep -q "^${BUILD_CTR}$"; then
  log "Cancelling running build container ${BUILD_CTR}..."
  ${CONTAINER_CMD} stop "${BUILD_CTR}" 2>/dev/null || true
  ${CONTAINER_CMD} rm "${BUILD_CTR}" 2>/dev/null || true
fi

# ----- 4. Pull new image ----------------------------------------------
log "Pulling ${IMAGE}:dev-latest..."
${CONTAINER_CMD} pull "${IMAGE}:dev-latest"

# ----- 5. Rollback snapshot -------------------------------------------
log "Saving rollback snapshot to ${BUILD_PREV}..."
mkdir -p "$BUILD_PREV"
rsync -a --delete "${BUILD_DIR}/" "${BUILD_PREV}/"

# ----- 6. Build on server ---------------------------------------------
log "Running build container ${BUILD_CTR}..."
BUILD_EXIT=0
${CONTAINER_CMD} run --rm --name "${BUILD_CTR}" \
  -v "${BUILD_DIR}:/app/build" \
  -e MORPH_URL="${MORPH_URL}" \
  "${IMAGE}:dev-latest" \
  || BUILD_EXIT=$?

if [ "$BUILD_EXIT" -ne 0 ]; then
  log "ERROR: Build failed with exit code ${BUILD_EXIT}."

  # Restore previous build snapshot
  log "Restoring previous build from ${BUILD_PREV}..."
  if [ -d "$BUILD_PREV" ] && [ "$(ls -A "$BUILD_PREV" 2>/dev/null)" ]; then
    rsync -a --delete "${BUILD_PREV}/" "${BUILD_DIR}/"
  fi

  # Restart serve on the restored build
  log "Restarting serve on restored build..."
  ${CONTAINER_CMD} compose -f "$COMPOSE_FILE" -p perseus up -d --force-recreate serve

  log "Rollback complete. STATE_FILE unchanged; retry next tick."
  exit "$BUILD_EXIT"
fi

log "Build succeeded."

# ----- 7. Restart serve, write state ----------------------------------
log "Restarting serve..."
${CONTAINER_CMD} compose -f "$COMPOSE_FILE" -p perseus up -d --force-recreate serve

echo "$REMOTE_DIGEST" > "$STATE_FILE"
log "Deploy complete. Digest written to ${STATE_FILE}."
