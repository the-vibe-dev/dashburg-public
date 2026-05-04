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
  exec "$ROOT/scripts/manage_modules.sh" runtime-bootstrap-all
else
  keys=("$@")
fi

for key in "${keys[@]}"; do
  bootstrap_one "$key"
done
