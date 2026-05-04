#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ENV_FILE="$ROOT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

HOST="${DASHBURG_API_HOST:-0.0.0.0}"
PORT="${DASHBURG_API_PORT:-8321}"
CMD=()
if [[ "${DASHBURG_RELOAD:-0}" == "1" ]]; then
  RELOAD_FLAG=(--reload)
else
  RELOAD_FLAG=()
fi

cd "$BACKEND_DIR"
if [[ -x "$BACKEND_DIR/.venv/bin/uvicorn" ]]; then
  CMD=("$BACKEND_DIR/.venv/bin/uvicorn" app.main:app "${RELOAD_FLAG[@]}" --host "$HOST" --port "$PORT")
elif [[ -x "$ROOT_DIR/.venv/bin/uvicorn" ]]; then
  CMD=("$ROOT_DIR/.venv/bin/uvicorn" app.main:app "${RELOAD_FLAG[@]}" --host "$HOST" --port "$PORT")
else
  CMD=(python3 -m uvicorn app.main:app "${RELOAD_FLAG[@]}" --host "$HOST" --port "$PORT")
fi

exec "${CMD[@]}"
