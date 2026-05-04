#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="$ROOT_DIR/data/remoteops"
SECRETS_FILE="$DATA_DIR/secrets.json"
KNOWN_HOSTS_FILE="$DATA_DIR/known_hosts"

mkdir -p "$DATA_DIR"
chmod 700 "$DATA_DIR" || true

if [[ ! -f "$SECRETS_FILE" ]]; then
  cat > "$SECRETS_FILE" <<'JSON'
{
  "nodes": {}
}
JSON
fi

chmod 600 "$SECRETS_FILE" || true
touch "$KNOWN_HOSTS_FILE"
chmod 600 "$KNOWN_HOSTS_FILE" || true

echo "Initialized $DATA_DIR"
ls -la "$DATA_DIR"
echo "Tip: set REMOTEOPS_TERMINAL_IDLE_TIMEOUT_SECONDS=300 in backend env for 5m idle timeout."
