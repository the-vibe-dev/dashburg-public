#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  source "$ROOT_DIR/.env"
  set +a
fi

: "${DASHBURG_API_PORT:=8431}"
: "${DASHBURG_WEB_PORT:=4174}"

cd "$ROOT_DIR"
./scripts/start_dashburg_backend.sh > /tmp/dashgithub-api.log 2>&1 &
api_pid=$!
(
  cd "$ROOT_DIR/runner"
  ./.venv/bin/python run.py > /tmp/dashgithub-runner.log 2>&1
) &
runner_pid=$!
./scripts/start_dashburg_frontend.sh > /tmp/dashgithub-web.log 2>&1 &
web_pid=$!

echo "API PID=$api_pid PORT=$DASHBURG_API_PORT"
echo "RUNNER PID=$runner_pid PORT=8444"
echo "WEB PID=$web_pid PORT=$DASHBURG_WEB_PORT"
wait
