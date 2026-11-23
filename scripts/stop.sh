#!/usr/bin/env bash
# Stops both services started by ./scripts/quickstart.sh.
set -uo pipefail

PLATFORM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDS_FILE="$PLATFORM_ROOT/.quickstart.pids"

if [[ ! -f "$PIDS_FILE" ]]; then
    echo "No $PIDS_FILE found -- nothing started by quickstart.sh to stop."
    exit 0
fi

while read -r pid; do
    [[ -n "$pid" ]] || continue
    if kill -0 "$pid" 2>/dev/null; then
        echo "==> Stopping PID $pid"
        kill "$pid"
    else
        echo "==> PID $pid already gone"
    fi
done < "$PIDS_FILE"

rm -f "$PIDS_FILE"
echo "==> Stopped. Box containers themselves are untouched -- they expire/reap on their own normal TTL."
