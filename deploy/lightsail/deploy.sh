#!/usr/bin/env bash
# Runs on the server, from /opt/msa. CI pipes it over ssh after copying the
# compose file and Caddyfile; it also works by hand:
#
#   cd /opt/msa && bash deploy.sh <image-tag>     # tag = a commit SHA, or "latest"
#
# Expects the registry login to have happened already (CI does it just before).
set -euo pipefail

IMAGE_TAG="${1:?usage: deploy.sh <image-tag>}"
export IMAGE_TAG
cd /opt/msa

echo "==> Pulling backend:$IMAGE_TAG"
docker compose pull backend
docker logout ghcr.io >/dev/null 2>&1 || true

# Schema first: code that expects a column must never start before the column
# exists. `set -e` stops the script here on a failed migration, so the running
# containers are never replaced by ones the database cannot serve.
echo "==> Applying migrations"
docker compose run --rm backend alembic upgrade head

echo "==> Starting services"
docker compose up -d --remove-orphans

echo "==> Waiting for /health/health"
ORIGIN_SECRET="$(grep '^ORIGIN_SECRET=' .env | cut -d= -f2-)"
for _ in $(seq 1 30); do
  if curl -fsS -H "X-Origin-Verify: $ORIGIN_SECRET" http://localhost/health/health; then
    echo
    docker image prune -f >/dev/null
    echo "==> Deployed $IMAGE_TAG"
    exit 0
  fi
  sleep 2
done

echo "Health check never passed - recent backend logs:" >&2
docker compose logs --tail 50 backend >&2
exit 1
