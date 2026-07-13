# VM Deployment Setup

This directory contains the scripts and configuration for running the
MinimumViablePerseus static site build on your own server, triggered by
new images pushed to GHCR.

## Prerequisites

- Docker (locally) or Podman (on the VM), both with `compose` subcommand
- A public GitHub Container Registry image

## Environment variables

| Variable        | Default                                                         | Description                     |
|-----------------|-----------------------------------------------------------------|---------------------------------|
| `IMAGE`         | `ghcr.io/perseusdlcode/minimumviableperseus`                    | GHCR builder image              |
| `MORPH_URL`     | *(required)*                                                    | Morpheus endpoint               |
| `BUILD_DIR`     | `/home/perseus/build`                                           | Symlink `serve` mounts; points at whichever blue-green directory is live |
| `STATE_FILE`    | `/home/perseus/last-digest`                                     | Last-deployed image digest      |
| `BUILD_CTR`     | `perseus-build`                                                 | Build container name            |
| `SERVE_PORT`    | `8080`                                                          | Host port for nginx             |
| `CONTAINER_CMD` | `docker`                                                        | Container runtime (set to `podman` on VM) |

`BUILD_DIR-a` and `BUILD_DIR-b` (e.g. `/home/perseus/build-a`, `/home/perseus/build-b`)
are created automatically alongside `BUILD_DIR` — see "How it works" below.

## One-time setup

```bash
# Copy the deploy artifacts
cp cron-deploy.sh compose.yaml /home/perseus/
chmod +x /home/perseus/cron-deploy.sh

# Create the env file
cat > /home/perseus/env << 'EOF'
MORPH_URL=https://your-morpheus-endpoint.example.com
CONTAINER_CMD=podman
EOF
```

## Cron

Add this line to your crontab (`crontab -e`):

```
*/10 * * * * /usr/bin/flock -n /home/perseus/deploy.lock /home/perseus/cron-deploy.sh >> /home/perseus/deploy.log 2>&1
```

## How it works

1. The nginx serve container is defined declaratively in `compose.yaml`
   and managed via `$CONTAINER_CMD compose`.
2. Every 10 minutes, the script polls GHCR for the `dev-latest` image digest.
3. Rollback uses a blue-green pair of directories, `BUILD_DIR-a` and
   `BUILD_DIR-b`, with `BUILD_DIR` a symlink pointing at whichever one is
   currently served. If the digest differs from the last-deployed one, it:
   - Cancels any in-progress build container.
   - Pulls the new image, then prunes the image it replaces
     (`$CONTAINER_CMD image prune -f`) so old layers don't accumulate.
   - Runs `$CONTAINER_CMD run` with the builder image, mounting the
     *inactive* blue-green directory — the live, served directory is never
     touched during the build.
4. On success: `BUILD_DIR` is flipped to the directory that was just built,
   `compose up -d --force-recreate serve` restarts nginx so it picks up the
   new symlink target, and the new digest is recorded.
5. On failure: nothing is touched — the symlink still points at the last-good
   build, so there is no restore step. The state file is left unchanged
   (retries next tick).

Because the build never writes into the live directory, there's always
exactly one full extra copy of the site on disk (the inactive slot) — no
more, no less — and no per-tick full-tree copy the way an rsync-based
snapshot would require.

## Making the GHCR package public

After the first push, go to:

```
https://github.com/orgs/perseusdlcode/packages/container/minimumviableperseus/settings
```

and set visibility to **public** so the VM can pull without authentication.
