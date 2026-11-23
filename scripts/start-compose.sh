#!/usr/bin/env bash
# Docker-based one-command setup: generates .env with random secrets on
# first run (reused on every rerun), then `docker compose up`. See
# ./scripts/quickstart.sh for the native alternative, and SETUP.md for
# the trade-offs between the two -- most notably that this grants the
# orchestrator container the real host's /var/run/docker.sock.
set -euo pipefail

PLATFORM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PLATFORM_ROOT/.env"

cd "$PLATFORM_ROOT"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "==> Generating $ENV_FILE (never commit this)"
    PUBLIC_ADDRESS="$(curl -s --max-time 3 ifconfig.me || true)"
    if [[ -z "$PUBLIC_ADDRESS" ]]; then
        echo "    Could not auto-detect this host's public address -- defaulting to 127.0.0.1."
        echo "    If players will connect from elsewhere, edit PUBLIC_ADDRESS in $ENV_FILE and rerun."
        PUBLIC_ADDRESS="127.0.0.1"
    fi
    cat > "$ENV_FILE" <<EOF
PUBLIC_ADDRESS=$PUBLIC_ADDRESS
ORCHESTRATOR_AUTH_TOKEN=$(openssl rand -hex 32)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$(openssl rand -hex 12)
SESSION_SECRET=$(openssl rand -hex 32)
ORCHESTRATOR_MAX_INSTANCES_PER_TEAM=4
EOF
else
    echo "==> Found existing $ENV_FILE, reusing it"
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

echo "==> docker compose up -d --build (first run builds everything, including all 8 box images -- can take a while)"
docker compose up -d --build

echo "==> Waiting for ctf-platform to answer on :9200"
for _ in $(seq 1 60); do
    curl -s -o /dev/null http://127.0.0.1:9200/ && break
    sleep 2
done
curl -s -o /dev/null http://127.0.0.1:9200/ || { echo "ctf-platform did not come up -- check: docker compose logs"; exit 1; }

echo
echo "================================================================"
echo " ctf-platform is up: http://${PUBLIC_ADDRESS}:9200"
echo " Admin login: ${ADMIN_USERNAME} / ${ADMIN_PASSWORD}"
echo " (credentials saved in $ENV_FILE, reused on every rerun)"
echo " Stop everything with: docker compose down"
echo "================================================================"
