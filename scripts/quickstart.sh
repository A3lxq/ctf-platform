#!/usr/bin/env bash
# Native (non-Docker) one-command setup: clones ctf-orchestrator as a
# sibling directory if it isn't already there, sets up both venvs,
# builds every box image, generates secrets once (reused on rerun),
# starts both services in the background, and prints the URL + admin
# credentials. Companion to ./scripts/stop.sh, and to
# ./scripts/start-compose.sh for the Docker alternative -- see SETUP.md
# for the trade-offs between the two.
set -euo pipefail

PLATFORM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR_ROOT="$(dirname "$PLATFORM_ROOT")/ctf-orchestrator"
SECRETS_FILE="$PLATFORM_ROOT/.quickstart-secrets"
PIDS_FILE="$PLATFORM_ROOT/.quickstart.pids"
ORCHESTRATOR_LOG="$PLATFORM_ROOT/.quickstart-orchestrator.log"
PLATFORM_LOG="$PLATFORM_ROOT/.quickstart-platform.log"

echo "==> ctf-platform quickstart"

# 1. Fetch the sibling orchestrator repo if it isn't already checked out.
if [[ ! -d "$ORCHESTRATOR_ROOT" ]]; then
    echo "==> Cloning ctf-orchestrator to $ORCHESTRATOR_ROOT"
    git clone https://github.com/A3lxq/CTF-orchestrator.git "$ORCHESTRATOR_ROOT"
else
    echo "==> Found existing ctf-orchestrator at $ORCHESTRATOR_ROOT (not touching it -- pull manually if you want updates)"
fi

# 2. Set up both venvs.
for repo in "$ORCHESTRATOR_ROOT" "$PLATFORM_ROOT"; do
    if [[ ! -d "$repo/.venv" ]]; then
        echo "==> Creating venv in $repo"
        python3 -m venv "$repo/.venv"
    fi
    echo "==> Installing dependencies in $repo"
    "$repo/.venv/bin/pip" install --quiet --upgrade pip
    "$repo/.venv/bin/pip" install --quiet -r "$repo/requirements.txt"
done

# 3. Build every box image (the slow step on first run; fast on reruns
# thanks to Docker's own build cache).
echo "==> Building box images (this can take a few minutes the first time)"
(cd "$ORCHESTRATOR_ROOT" && ./scripts/build_boxes.sh)

# 4. Generate secrets once, reused on every rerun.
if [[ ! -f "$SECRETS_FILE" ]]; then
    echo "==> Generating secrets (saved to $SECRETS_FILE, never commit this)"
    PUBLIC_ADDRESS="$(curl -s --max-time 3 ifconfig.me || true)"
    if [[ -z "$PUBLIC_ADDRESS" ]]; then
        echo "    Could not auto-detect this host's public address -- defaulting to 127.0.0.1."
        echo "    If players will connect from elsewhere, edit PUBLIC_ADDRESS in $SECRETS_FILE and rerun."
        PUBLIC_ADDRESS="127.0.0.1"
    fi
    cat > "$SECRETS_FILE" <<EOF
PUBLIC_ADDRESS=$PUBLIC_ADDRESS
ORCHESTRATOR_AUTH_TOKEN=$(openssl rand -hex 32)
PLATFORM_SESSION_SECRET=$(openssl rand -hex 32)
PLATFORM_ADMIN_USERNAME=admin
PLATFORM_ADMIN_PASSWORD=$(openssl rand -hex 12)
EOF
fi
# shellcheck disable=SC1090
source "$SECRETS_FILE"

# 5. Start the orchestrator, then wait for it to answer.
echo "==> Starting ctf-orchestrator on :9100"
(
    cd "$ORCHESTRATOR_ROOT"
    ORCHESTRATOR_PUBLIC_ADDRESS="$PUBLIC_ADDRESS" \
    ORCHESTRATOR_AUTH_TOKEN="$ORCHESTRATOR_AUTH_TOKEN" \
    nohup "$ORCHESTRATOR_ROOT/.venv/bin/uvicorn" orchestrator.main:app --host 0.0.0.0 --port 9100 \
        > "$ORCHESTRATOR_LOG" 2>&1 &
    echo $! > "$PIDS_FILE"
)
for _ in $(seq 1 30); do
    curl -s -o /dev/null http://127.0.0.1:9100/healthz && break
    sleep 1
done
curl -s -o /dev/null http://127.0.0.1:9100/healthz || { echo "orchestrator did not come up -- check $ORCHESTRATOR_LOG"; exit 1; }

# 6. Start ctf-platform, then wait for it to answer.
echo "==> Starting ctf-platform on :9200"
(
    cd "$PLATFORM_ROOT"
    PLATFORM_ORCHESTRATOR_URL="http://127.0.0.1:9100" \
    PLATFORM_ORCHESTRATOR_AUTH_TOKEN="$ORCHESTRATOR_AUTH_TOKEN" \
    PLATFORM_SESSION_SECRET="$PLATFORM_SESSION_SECRET" \
    PLATFORM_ADMIN_USERNAME="$PLATFORM_ADMIN_USERNAME" \
    PLATFORM_ADMIN_PASSWORD="$PLATFORM_ADMIN_PASSWORD" \
    nohup "$PLATFORM_ROOT/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 9200 \
        > "$PLATFORM_LOG" 2>&1 &
    echo $! >> "$PIDS_FILE"
)
for _ in $(seq 1 30); do
    curl -s -o /dev/null http://127.0.0.1:9200/ && break
    sleep 1
done
curl -s -o /dev/null http://127.0.0.1:9200/ || { echo "ctf-platform did not come up -- check $PLATFORM_LOG"; exit 1; }

echo
echo "================================================================"
echo " ctf-platform is up: http://${PUBLIC_ADDRESS}:9200"
echo " Admin login: ${PLATFORM_ADMIN_USERNAME} / ${PLATFORM_ADMIN_PASSWORD}"
echo " (credentials saved in $SECRETS_FILE, reused on every rerun)"
echo " Stop everything with: ./scripts/stop.sh"
echo "================================================================"
