#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/web"
ENV_FILE="$ROOT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

HOST="${DASHBURG_WEB_HOST:-0.0.0.0}"
PORT="${DASHBURG_WEB_PORT:-4173}"
MODE="${DASHBURG_WEB_MODE:-preview}"

cd "$WEB_DIR"

if [[ "$MODE" == "dev" ]]; then
  exec npm run dev -- --host "$HOST" --port "$PORT"
fi

if [[ ! -d "$WEB_DIR/dist" ]] || [[ "${DASHBURG_WEB_REBUILD_ON_START:-0}" == "1" ]]; then
  npm run build
fi

exec npm run preview -- --host "$HOST" --port "$PORT"
