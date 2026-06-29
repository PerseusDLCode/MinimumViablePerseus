# VM Deployment Setup

This directory contains the scripts and configuration for running the
MinimumViablePerseus static site build on your own server, triggered by
new images pushed to GHCR.

## Prerequisites

- Docker (locally) or Podman (on the VM), both with `compose` subcommand
- `rsync`
- A public GitHub Container Registry image

## Environment variables

| Variable        | Default                                                         | Description                     |
|-----------------|-----------------------------------------------------------------|---------------------------------|
| `IMAGE`         | `ghcr.io/perseusdlcode/minimumviableperseus`                    | GHCR builder image              |
| `MORPH_URL`     | *(required)*                                                    | Morpheus endpoint               |
| `BUILD_DIR`     | `/opt/perseus/build`                                            | Host directory for build output |
| `BUILD_PREV`    | `/opt/perseus/build-prev`                                       | Rollback snapshot path          |
| `STATE_FILE`    | `/opt/perseus/last-digest`                                      | Last-deployed image digest      |
| `BUILD_CTR`     | `perseus-build`                                                 | Build container name            |
| `SERVE_PORT`    | `8080`                                                          | Host port for nginx             |
| `CONTAINER_CMD` | `docker`                                                        | Container runtime (set to `podman` on VM) |

## One-time setup

```bash
# Create directories
sudo mkdir -p /opt/perseus
sudo chown "$USER" /opt/perseus

# Copy the deploy artifacts
cp cron-deploy.sh compose.yaml /opt/perseus/
chmod +x /opt/perseus/cron-deploy.sh

# Create the env file
cat > /opt/perseus/env << 'EOF'
MORPH_URL=https://your-morpheus-endpoint.example.com
CONTAINER_CMD=podman
EOF
```

## Cron

Add this line to your crontab (`crontab -e`):

```
*/10 * * * * /usr/bin/flock -n /opt/perseus/deploy.lock /opt/perseus/cron-deploy.sh >> /opt/perseus/deploy.log 2>&1
```

## How it works

1. The nginx serve container is defined declaratively in `compose.yaml`
   and managed via `$CONTAINER_CMD compose`.
2. Every 10 minutes, the script polls GHCR for the `dev-latest` image digest.
3. If the digest differs from the last-deployed one, it:
   - Cancels any in-progress build container.
   - Pulls the new image.
   - Snapshots the current build directory (for rollback).
   - Runs `$CONTAINER_CMD run` with the builder image, mounting the build dir.
4. On success: `compose up -d --force-recreate serve` restarts nginx and the
   new digest is recorded.
5. On failure: the old snapshot is restored via `rsync`, nginx is restarted on
   the restored content, and the state file is left unchanged (retries next
   tick).

## Making the GHCR package public

After the first push, go to:

```
https://github.com/orgs/perseusdlcode/packages/container/minimumviableperseus/settings
```

and set visibility to **public** so the VM can pull without authentication.
