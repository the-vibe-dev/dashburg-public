#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/bootstrap_module_runtime.sh <module> [<module> ...]
  ./scripts/bootstrap_module_runtime.sh all

Bootstraps bundled local runtimes for installed Dashburg modules.
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

bootstrap_one() {
  local key="$1"
  echo "== bootstrap: $key =="
  "$ROOT/scripts/manage_modules.sh" runtime-bootstrap "$key"
}

if [[ "$1" == "all" ]]; then
  mapfile -t keys < <(
    DASHGITHUB_ROOT="$ROOT" "$ROOT/backend/.venv/bin/python" - <<'PY'
import os
import sys

from pathlib import Path

root = Path(os.environ["DASHGITHUB_ROOT"])
sys.path.insert(0, str(root / "backend"))
from app.module_system import catalog_payload  # noqa: E402

for item in catalog_payload():
    runtime = item.get("runtime") or {}
    if item.get("installed") and runtime.get("mode") == "bundled-local-service":
        print(item["key"])
PY
  )
  if [[ ${#keys[@]} -eq 0 ]]; then
    echo "No installed bundled-local-service modules found."
    exit 0
  fi
else
  keys=("$@")
fi

for key in "${keys[@]}"; do
  bootstrap_one "$key"
done
