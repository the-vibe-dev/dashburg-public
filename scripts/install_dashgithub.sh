#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_EXAMPLE="$ROOT_DIR/.env.example"
ENV_FILE="$ROOT_DIR/.env"
RUNNER_EXAMPLE="$ROOT_DIR/runner/config.example.yaml"
RUNNER_CONFIG="$ROOT_DIR/runner/config.yaml"

prompt() {
  local label="$1"
  local default="${2:-}"
  local value
  if [[ -n "$default" ]]; then
    read -r -p "$label [$default]: " value
    printf '%s' "${value:-$default}"
  else
    read -r -p "$label: " value
    printf '%s' "$value"
  fi
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd"
    exit 1
  fi
}

update_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text(encoding='utf-8').splitlines()
out = []
replaced = False
for line in lines:
    if line.startswith(f"{key}="):
        out.append(f"{key}={value}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding='utf-8')
PY
}

update_yaml_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text(encoding='utf-8').splitlines()
out = []
replaced = False
for line in lines:
    if line.startswith(f"{key}:"):
        out.append(f"{key}: {value}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(f"{key}: {value}")
path.write_text("\n".join(out) + "\n", encoding='utf-8')
PY
}

echo "Dashgithub guided install"
echo "Repository root: $ROOT_DIR"

require_cmd python3
require_cmd npm

if [[ ! -f "$ENV_EXAMPLE" ]]; then
  echo "Missing $ENV_EXAMPLE"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "Created $ENV_FILE from template"
else
  echo "Using existing $ENV_FILE"
fi

repo_default="$ROOT_DIR"
data_default="$ROOT_DIR/data"
shared_default="$ROOT_DIR/data/shared-memory"
runner_port_default="8444"
api_port_default="8431"
web_port_default="4174"
ssh_user_default="dashterm"
ssh_key_default="$HOME/.ssh/dashgithub_remoteops"
host_monitor_default="http://127.0.0.1:19444"

repo_root="$(prompt 'Repo root allowed for TaskVault/RemoteOps workspaces' "$repo_default")"
data_root="$(prompt 'Data directory' "$data_default")"
shared_root="$(prompt 'Shared memory root' "$shared_default")"
api_port="$(prompt 'API port' "$api_port_default")"
web_port="$(prompt 'Frontend port' "$web_port_default")"
runner_port="$(prompt 'Runner port' "$runner_port_default")"
ssh_user="$(prompt 'RemoteOps SSH user' "$ssh_user_default")"
ssh_key="$(prompt 'RemoteOps SSH private key path' "$ssh_key_default")"
host_monitor_url="$(prompt 'Optional host monitor base URL' "$host_monitor_default")"
admin_token="$(prompt 'RemoteOps admin token (leave blank to fill later)' '')"
openai_key="$(prompt 'OpenAI API key (leave blank to fill later)' '')"

mkdir -p "$data_root" "$shared_root"

update_env_value "$ENV_FILE" "DASHBURG_DATA_DIR" "$data_root"
update_env_value "$ENV_FILE" "DASHBURG_CONFIG_DIR" "$data_root"
update_env_value "$ENV_FILE" "DASHBURG_SECRETS_DIR" "$data_root"
update_env_value "$ENV_FILE" "DASHBURG_SHARED_MEMORY_ROOT" "$shared_root"
update_env_value "$ENV_FILE" "DASHBURG_API_PORT" "$api_port"
update_env_value "$ENV_FILE" "DASHBURG_WEB_PORT" "$web_port"
update_env_value "$ENV_FILE" "VITE_API_URL" "http://127.0.0.1:$api_port"
update_env_value "$ENV_FILE" "REMOTEOPS_SSH_USER" "$ssh_user"
update_env_value "$ENV_FILE" "REMOTEOPS_SSH_KEY_PATH" "$ssh_key"
update_env_value "$ENV_FILE" "HOST_MONITOR_BASE_URL" "$host_monitor_url"
if [[ -n "$admin_token" ]]; then
  update_env_value "$ENV_FILE" "REMOTEOPS_ADMIN_TOKEN" "$admin_token"
fi
if [[ -n "$openai_key" ]]; then
  update_env_value "$ENV_FILE" "OPENAI_API_KEY" "$openai_key"
fi

python3 -m venv "$ROOT_DIR/backend/.venv"
"$ROOT_DIR/backend/.venv/bin/pip" install --upgrade pip
"$ROOT_DIR/backend/.venv/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"

python3 -m venv "$ROOT_DIR/runner/.venv"
"$ROOT_DIR/runner/.venv/bin/pip" install --upgrade pip
"$ROOT_DIR/runner/.venv/bin/pip" install -r "$ROOT_DIR/runner/requirements.txt"

(
  cd "$ROOT_DIR/web"
  npm install
)

if [[ ! -f "$RUNNER_CONFIG" ]]; then
  cp "$RUNNER_EXAMPLE" "$RUNNER_CONFIG"
  echo "Created $RUNNER_CONFIG from template"
else
  echo "Using existing $RUNNER_CONFIG"
fi

node_id_default="$(hostname -s 2>/dev/null || echo runner-node)"
node_id="$(prompt 'Runner node_id' "$node_id_default")"
key_id="$(prompt 'Runner key_id' 'hub-main')"
shared_secret="$(prompt 'Runner shared_secret' 'CHANGE_ME_LONG_RANDOM_SECRET')"

mkdir -p "$data_root/runner"
update_yaml_value "$RUNNER_CONFIG" "host" "0.0.0.0"
update_yaml_value "$RUNNER_CONFIG" "port" "$runner_port"
update_yaml_value "$RUNNER_CONFIG" "node_id" "$node_id"
update_yaml_value "$RUNNER_CONFIG" "key_id" "$key_id"
update_yaml_value "$RUNNER_CONFIG" "shared_secret" "$shared_secret"
update_yaml_value "$RUNNER_CONFIG" "data_dir" "$data_root/runner"
update_yaml_value "$RUNNER_CONFIG" "log_file" "$data_root/runner/runner.log"

python3 - "$RUNNER_CONFIG" "$repo_root" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
repo = sys.argv[2]
text = path.read_text(encoding='utf-8')
lines = []
inside = False
inserted = False
for line in text.splitlines():
    if line.startswith('allowed_repos:'):
        lines.append('allowed_repos:')
        lines.append(f'  - {repo}')
        inside = True
        inserted = True
        continue
    if inside:
        if line.startswith('  - '):
            continue
        inside = False
    lines.append(line)
if not inserted:
    lines.append('allowed_repos:')
    lines.append(f'  - {repo}')
path.write_text("\n".join(lines) + "\n", encoding='utf-8')
PY

echo
echo "Install complete. Review these files before first launch:"
echo "- $ENV_FILE"
echo "- $RUNNER_CONFIG"
echo
echo "Start commands:"
echo "- API:      ./scripts/start_dashburg_backend.sh"
echo "- Runner:   (cd runner && ./.venv/bin/python run.py)"
echo "- Frontend: ./scripts/start_dashburg_frontend.sh"
