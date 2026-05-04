#!/usr/bin/env bash
set -euo pipefail

# Easy interactive installer for a Dashburg Runner node.
# Run from the copied runner/ directory on the target node.

if [[ ! -f "requirements.txt" || ! -f "run.py" ]]; then
  echo "Run this script from the runner/ directory."
  exit 1
fi

for cmd in sudo python3 ssh ssh-keygen rsync; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "$cmd is required."
    exit 1
  fi
done

check_python_venv_deps() {
  if ! python3 -m ensurepip --version >/dev/null 2>&1; then
    if ! command -v apt-get >/dev/null 2>&1; then
      echo "Python venv dependencies are missing (ensurepip unavailable)."
      echo "apt-get is unavailable for automatic install."
      exit 1
    fi
    echo "Installing missing Python venv dependencies (python3-venv)..."
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv
    if ! python3 -m ensurepip --version >/dev/null 2>&1; then
      echo "Automatic install completed but ensurepip is still unavailable."
      exit 1
    fi
  fi
}

check_python_venv_deps

DEFAULT_NODE_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
DEFAULT_NODE_IP="${DEFAULT_NODE_IP:-127.0.0.1}"
DEFAULT_NODE_ID="$(hostname -s 2>/dev/null || echo node-1)"
DEFAULT_NODE_ID="${DEFAULT_NODE_ID:-node-1}"
DEFAULT_NODE_LABEL="$(hostname 2>/dev/null || echo Dashburg Node)"
DEFAULT_NODE_LABEL="${DEFAULT_NODE_LABEL:-Dashburg Node}"
DEFAULT_LISTEN_PORT="8844"
DEFAULT_HUB_API="http://hub.example.local:8431"
DEFAULT_DASHBURG_MAIN_PUBKEY=""

prompt() {
  local text="$1"
  local default="${2:-}"
  local value=""
  if [[ -n "$default" ]]; then
    read -r -p "$text [$default]: " value
    echo "${value:-$default}"
  else
    read -r -p "$text: " value
    echo "$value"
  fi
}

prompt_secret() {
  local text="$1"
  local value=""
  read -r -s -p "$text: " value
  echo
  echo "$value"
}

prompt_yes_no() {
  local text="$1"
  local default="$2"
  local value=""
  while true; do
    read -r -p "$text [${default}/$( [[ "$default" == "y" ]] && echo n || echo y )]: " value
    value="${value:-$default}"
    case "$(echo "$value" | tr '[:upper:]' '[:lower:]')" in
      y|yes) echo "y"; return 0 ;;
      n|no) echo "n"; return 0 ;;
      *) echo "Please answer y or n." ;;
    esac
  done
}

prompt_csv() {
  local text="$1"
  local default_csv="$2"
  local out=""
  read -r -p "$text (comma-separated) [$default_csv]: " out
  out="${out:-$default_csv}"
  echo "$out" | sed 's/[[:space:]]*,[[:space:]]*/,/g; s/^,*//; s/,*$//'
}

mask_value() {
  local value="${1:-}"
  local keep="${2:-4}"
  local len=${#value}
  if [[ -z "$value" ]]; then
    echo ""
    return 0
  fi
  if [[ "$len" -le $((keep * 2)) ]]; then
    printf '%*s' "$len" '' | tr ' ' '*'
    return 0
  fi
  local start="${value:0:keep}"
  local end="${value: -keep}"
  local stars_len=$((len - (keep * 2)))
  local stars
  stars="$(printf '%*s' "$stars_len" '' | tr ' ' '*')"
  echo "${start}${stars}${end}"
}

mask_path() {
  local path="${1:-}"
  if [[ -z "$path" ]]; then
    echo ""
    return 0
  fi
  local base
  base="$(basename "$path")"
  local dir
  dir="$(dirname "$path")"
  if [[ "$dir" == "." || "$dir" == "/" ]]; then
    echo "***${base}"
    return 0
  fi
  echo "$(mask_value "$dir" 3)/${base}"
}

sanitize_json_secrets() {
  local raw="${1:-}"
  RAW_JSON="$raw" python3 - <<'PY'
import json
import os

raw = os.environ.get("RAW_JSON", "")
if not raw:
    print("")
    raise SystemExit(0)

secret_tokens = ("secret", "token", "password", "private_key", "shared_secret")

def mask(s: str) -> str:
    s = str(s or "")
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}{'*' * (len(s) - 8)}{s[-4:]}"

def scrub(value, key_name: str = ""):
    lowered = key_name.lower()
    should_mask = any(k in lowered for k in secret_tokens)
    if isinstance(value, dict):
        return {k: scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, key_name) for v in value]
    if should_mask and isinstance(value, (str, int, float)):
        return mask(str(value))
    return value

try:
    parsed = json.loads(raw)
except Exception:
    print(mask(raw))
    raise SystemExit(0)

print(json.dumps(scrub(parsed), separators=(",", ":")))
PY
}

generate_secret() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
}

user_home() {
  local user="$1"
  getent passwd "$user" | cut -d: -f6
}

extract_host_from_url() {
  local url="$1"
  URL_IN="$url" python3 - <<'PY'
from urllib.parse import urlparse
import os
u = (os.environ.get("URL_IN", "") or "").strip()
if not u:
    print("")
    raise SystemExit(0)
try:
    p = urlparse(u)
    print(p.hostname or "")
except Exception:
    print("")
PY
}

fetch_remoteops_admin_token_via_ssh() {
  local hub_host="$1"
  local ssh_user="$2"
  local ssh_key_path="$3"
  if [[ -z "$hub_host" || -z "$ssh_user" || -z "$ssh_key_path" ]]; then
    echo ""
    return 1
  fi
  ssh -i "$ssh_key_path" \
    -o IdentitiesOnly=yes \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    -o StrictHostKeyChecking=accept-new \
    "${ssh_user}@${hub_host}" \
    "bash -lc '
      set -e
      for envf in ~/apps/dashgithub/.env /srv/repos/dashgithub/.env ~/.env; do
        if [ -f \"\$envf\" ]; then
          token=\$(awk -F= '\''/^[[:space:]]*REMOTEOPS_ADMIN_TOKEN=/{sub(/^[[:space:]]*/,\"\",\$2); sub(/[[:space:]]*$/,\"\",\$2); gsub(/^\"|\"$/, \"\", \$2); gsub(/^\\047|\\047$/, \"\", \$2); print \$2; exit}'\'' \"\$envf\")
          if [ -n \"\$token\" ]; then
            printf \"%s\" \"\$token\"
            exit 0
          fi
        fi
      done
      exit 1
    '" 2>/dev/null || true
}

split_csv_to_yaml_list() {
  local csv="$1"
  local indent="$2"
  local item
  local wrote="0"
  IFS=',' read -r -a items <<< "$csv"
  for item in "${items[@]}"; do
    item="$(echo "$item" | sed 's/^ *//; s/ *$//')"
    [[ -z "$item" ]] && continue
    printf "%s- %s\n" "$indent" "$item"
    wrote="1"
  done
  if [[ "$wrote" == "0" ]]; then
    printf "%s[]\n" "$indent"
  fi
}

run_as_runner_user() {
  local runner_user="$1"
  shift
  sudo -u "$runner_user" -H bash -lc "$*"
}

configure_passwordless_sudo() {
  local runner_user="$1"
  if [[ -z "$runner_user" ]]; then
    echo "Cannot configure sudoers: empty user."
    return 1
  fi
  if [[ "$runner_user" == "root" ]]; then
    echo "Skipping sudoers change for root user."
    return 0
  fi
  local sudoers_path="/etc/sudoers.d/90-dashburg-${runner_user}-nopasswd"
  local rule="${runner_user} ALL=(ALL) NOPASSWD:ALL"
  printf '%s\n' "$rule" | sudo tee "$sudoers_path" >/dev/null
  sudo chmod 440 "$sudoers_path"
  if ! sudo visudo -cf "$sudoers_path" >/dev/null; then
    echo "sudoers validation failed for $sudoers_path"
    return 1
  fi
}

service_runner_config_value() {
  local service_path="$1"
  awk -F= '/^Environment=RUNNER_CONFIG=/{print $3; exit}' "$service_path" 2>/dev/null || true
}

ensure_service_runner_config_file() {
  local service_path="$1"
  local desired_config="$2"
  local current
  current="$(service_runner_config_value "$service_path")"
  if [[ -z "$current" ]]; then
    echo "missing"
    return 1
  fi
  if [[ -d "$current" ]]; then
    sudo sed -i "s|^Environment=RUNNER_CONFIG=.*|Environment=RUNNER_CONFIG=${desired_config}|" "$service_path"
    echo "fixed_from_dir"
    return 0
  fi
  if [[ "$current" != "$desired_config" ]]; then
    sudo sed -i "s|^Environment=RUNNER_CONFIG=.*|Environment=RUNNER_CONFIG=${desired_config}|" "$service_path"
    echo "fixed_mismatch"
    return 0
  fi
  echo "ok"
}

install_codex_prereqs() {
  if command -v npm >/dev/null 2>&1 && command -v node >/dev/null 2>&1; then
    return 0
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    echo "Node.js/npm are missing and apt-get is unavailable for automatic install."
    echo "Install Node.js and npm manually, then re-run deploy."
    return 1
  fi

  echo "Installing Codex prerequisites (nodejs, npm)..."
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs npm

  if ! command -v npm >/dev/null 2>&1 || ! command -v node >/dev/null 2>&1; then
    echo "Failed to install Node.js/npm prerequisites."
    return 1
  fi
}

install_codex_for_user() {
  local runner_user="$1"
  if run_as_runner_user "$runner_user" "command -v codex >/dev/null 2>&1"; then
    echo "Codex CLI already installed for ${runner_user}."
    return 0
  fi
  if ! install_codex_prereqs; then
    return 1
  fi
  echo "Installing Codex CLI globally via npm for ${runner_user}..."
  sudo npm install -g @openai/codex
  run_as_runner_user "$runner_user" "command -v codex >/dev/null 2>&1"
}

codex_login_for_user() {
  local runner_user="$1"
  local codex_cmd
  codex_cmd="$(run_as_runner_user "$runner_user" "command -v codex || true")"
  if [[ -z "$codex_cmd" ]]; then
    echo "Codex CLI is not available for ${runner_user}; skipping login."
    return 1
  fi
  local status_out=""
  set +e
  status_out="$(run_as_runner_user "$runner_user" "\"$codex_cmd\" login status 2>&1")"
  local status_code=$?
  set -e
  if [[ $status_code -eq 0 && "$status_out" == *"Logged in"* ]]; then
    echo "Codex already logged in for ${runner_user}; skipping login."
    return 0
  fi
  echo ""
  echo "Starting Codex device-auth login for user ${runner_user} (headless-safe)."
  echo "Use the shown code + URL from any browser-enabled device, then return here."
  sudo -u "$runner_user" -H "$codex_cmd" login --device-auth
}

run_codex_exec_profiles() {
  local runner_user="$1"
  local investigations_dir="$2"
  local node_profile_file="$3"
  local repo_profile_file="$4"
  local node_id="$5"
  local node_label="$6"
  local node_ip="$7"
  local base_url="$8"
  local repos_csv="$9"
  local services_csv="${10}"
  local job_types_csv="${11}"
  local deploy_user="${12}"
  local runner_home="${13}"
  local data_dir="${14}"
  local log_file="${15}"

  local codex_cmd
  codex_cmd="$(run_as_runner_user "$runner_user" "command -v codex || true")"
  if [[ -z "$codex_cmd" ]]; then
    echo "Codex CLI is unavailable; skipping codex exec profile generation."
    return 1
  fi

  local server_role
  local primary_workloads
  local os_notes
  local network_notes
  local known_issues
  local repo_layout_notes
  local config_paths_notes

  server_role="$(prompt 'Codex profile input: server role/purpose' 'Dashburg runner node')"
  primary_workloads="$(prompt 'Codex profile input: primary workloads/services on this server' 'dashburg-runner, remote jobs')"
  os_notes="$(prompt 'Codex profile input: OS + runtime notes' "$(uname -s) $(uname -r)")"
  network_notes="$(prompt 'Codex profile input: network/access notes' "base_url=${base_url}, host=${node_ip}")"
  known_issues="$(prompt 'Codex profile input: known issues or caveats' 'none noted')"
  repo_layout_notes="$(prompt 'Codex profile input: repo layout/entrypoints notes' 'document runner repos and entry commands')"
  config_paths_notes="$(prompt 'Codex profile input: config/env path notes' 'document config yaml, env files, secrets paths')"

  local prompt_file
  prompt_file="$(mktemp)"
  cat > "$prompt_file" <<EOF
You are operating on a Linux runner node.
Task:
1) Ask short follow-up questions ONLY if critical details are missing.
2) Update both markdown files with concrete, durable operational notes:
   - ${node_profile_file}
   - ${repo_profile_file}
3) Keep structure readable with short sections and bullet points.
4) Do not remove existing useful content; refine and append where needed.

Known context:
- node_id: ${node_id}
- node_label: ${node_label}
- host: ${node_ip}
- base_url: ${base_url}
- deploy_user: ${deploy_user}
- runner_user: ${runner_user}
- runner_home: ${runner_home}
- data_dir: ${data_dir}
- log_file: ${log_file}
- investigations_dir: ${investigations_dir}
- allowed_repos: ${repos_csv}
- allowed_services: ${services_csv}
- allowed_job_types: ${job_types_csv}

Operator answers:
- server_role: ${server_role}
- primary_workloads: ${primary_workloads}
- os_notes: ${os_notes}
- network_notes: ${network_notes}
- known_issues: ${known_issues}
- repo_layout_notes: ${repo_layout_notes}
- config_paths_notes: ${config_paths_notes}

Required output quality:
- host profile should include identity/access/runtime/services/observations/known issues.
- repo profile should include allowed repos/services/job types/layout/config paths/known issues.
- include actionable next steps where uncertainty remains.
EOF

  if [[ ! -d "$investigations_dir" ]]; then
    sudo install -d -m 755 -o "$runner_user" -g "$runner_user" "$investigations_dir"
  fi

  local exec_cmd
  exec_cmd="cd \"$investigations_dir\" && \"$codex_cmd\" exec -s workspace-write \"\$(cat '$prompt_file')\""
  run_as_runner_user "$runner_user" "$exec_cmd"
  rm -f "$prompt_file"
}

append_pubkey_for_user() {
  local target_user="$1"
  local pubkey="$2"
  local home_dir
  home_dir="$(user_home "$target_user")"
  if [[ -z "$home_dir" ]]; then
    echo "Could not resolve home for user $target_user"
    return 1
  fi

  if [[ "$target_user" == "$USER" ]]; then
    mkdir -p "$home_dir/.ssh"
    chmod 700 "$home_dir/.ssh"
    touch "$home_dir/.ssh/authorized_keys"
    chmod 600 "$home_dir/.ssh/authorized_keys"
    if ! grep -Fq "$pubkey" "$home_dir/.ssh/authorized_keys"; then
      printf '%s\n' "$pubkey" >> "$home_dir/.ssh/authorized_keys"
    fi
  else
    sudo install -d -m 700 -o "$target_user" -g "$target_user" "$home_dir/.ssh"
    sudo touch "$home_dir/.ssh/authorized_keys"
    sudo chown "$target_user:$target_user" "$home_dir/.ssh/authorized_keys"
    sudo chmod 600 "$home_dir/.ssh/authorized_keys"
    if ! sudo grep -Fq "$pubkey" "$home_dir/.ssh/authorized_keys"; then
      printf '%s\n' "$pubkey" | sudo tee -a "$home_dir/.ssh/authorized_keys" >/dev/null
    fi
  fi
}

create_entry_script_if_missing() {
  local target_user="$1"
  local desired_path="$2"
  local home_dir
  home_dir="$(user_home "$target_user")"
  [[ -z "$home_dir" ]] && return 1

  local path="$desired_path"
  if [[ -z "$path" ]]; then
    path="$home_dir/dashterm-entry"
  fi

  if [[ -x "$path" ]]; then
    echo "$path"
    return 0
  fi

  local parent_dir
  parent_dir="$(dirname "$path")"
  if [[ "$target_user" == "$USER" ]]; then
    mkdir -p "$parent_dir"
  else
    sudo install -d -m 755 -o "$target_user" -g "$target_user" "$parent_dir"
  fi

  if [[ "$target_user" == "$USER" ]]; then
    cat > "$path" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "Welcome to RemoteOps Terminal"
cd "$HOME"
exec bash -l
EOF
    chmod +x "$path"
  else
    cat <<'EOF' | sudo tee "$path" >/dev/null
#!/usr/bin/env bash
set -euo pipefail
echo "Welcome to RemoteOps Terminal"
cd "$HOME"
exec bash -l
EOF
    sudo chown "$target_user:$target_user" "$path"
    sudo chmod 755 "$path"
  fi
  echo "$path"
}

check_rw_as_user() {
  local target_user="$1"
  local path="$2"
  local kind="$3"
  if ! sudo -u "$target_user" test "$kind" "$path"; then
    echo "Permission check failed: user=$target_user path=$path test=$kind"
    return 1
  fi
}

register_with_hub() {
  local hub_api="$1"
  local admin_token="$2"
  local node_id="$3"
  local node_label="$4"
  local base_url="$5"
  local supports_codex="$6"
  local supports_terminal="$7"
  local allowed_repos_csv="$8"
  local allowed_services_csv="$9"
  local allowed_job_types_csv="${10}"

  HUB_API="$hub_api" HUB_TOKEN="$admin_token" NODE_ID="$node_id" NODE_LABEL="$node_label" BASE_URL="$base_url" SUPPORTS_CODEX="$supports_codex" SUPPORTS_TERMINAL="$supports_terminal" REPOS_CSV="$allowed_repos_csv" SERVICES_CSV="$allowed_services_csv" TYPES_CSV="$allowed_job_types_csv" python3 - <<'PY'
import json
import os
import urllib.request
import urllib.error

api = os.environ["HUB_API"].rstrip("/")
token = os.environ.get("HUB_TOKEN", "").replace("\r", "").replace("\n", "").strip()

def parse_csv(text):
    text = (text or "").strip()
    if not text:
        return []
    return [x.strip() for x in text.split(",") if x.strip()]

payload = {
    "id": os.environ["NODE_ID"],
    "label": os.environ["NODE_LABEL"],
    "base_url": os.environ["BASE_URL"],
    "enabled": True,
    "supports_codex": os.environ["SUPPORTS_CODEX"].lower() == "true",
    "supports_terminal": os.environ["SUPPORTS_TERMINAL"].lower() == "true",
    "allowed_repos": parse_csv(os.environ.get("REPOS_CSV", "")),
    "allowed_services": parse_csv(os.environ.get("SERVICES_CSV", "")),
    "allowed_job_types": parse_csv(os.environ.get("TYPES_CSV", "")),
    "notes": "created by deploy_runner_node.sh",
}

headers = {"Content-Type": "application/json", "Accept": "application/json"}
if token:
    headers["X-RemoteOps-Admin-Token"] = token

req = urllib.request.Request(url=f"{api}/api/remote/nodes", method="POST", data=json.dumps(payload).encode("utf-8"), headers=headers)

def rotate_key(node_id: str):
    rotate_req = urllib.request.Request(
        url=f"{api}/api/remote/nodes/{node_id}/rotate-key",
        method="POST",
        data=json.dumps({"disable_previous": True}).encode("utf-8"),
        headers=headers,
    )
    with urllib.request.urlopen(rotate_req, timeout=20) as rotate_resp:
        body = json.loads(rotate_resp.read().decode("utf-8") or "{}")
        return {
            "ok": True,
            "rotated": True,
            "key_id": body.get("key_id") or "",
            "secret": body.get("secret") or "",
            "node_id": body.get("node_id") or node_id,
        }

try:
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8") or "{}")
        created_node_id = body.get("id") or payload["id"]
        out = rotate_key(created_node_id)
        out["created"] = True
        print(json.dumps(out))
except urllib.error.HTTPError as exc:
    raw = exc.read().decode("utf-8", errors="replace")
    out = {"ok": False, "status": exc.code, "raw": raw}
    if exc.code == 409:
        try:
            out = rotate_key(payload["id"])
            out["created"] = False
        except Exception as rotate_exc:
            out["rotate_error"] = str(rotate_exc)
    print(json.dumps(out))
except Exception as exc:
    print(json.dumps({"ok": False, "status": 0, "raw": str(exc)}))
PY
}

check_runner_monitor() {
  local base_url="$1"
  BASE_URL="$base_url" python3 - <<'PY'
import json
import os
import urllib.request

base = os.environ["BASE_URL"].rstrip("/")
url = f"{base}/v1/host-monitor/status"
out = {"ok": False, "url": url}
try:
    with urllib.request.urlopen(url, timeout=6) as resp:
        body = json.loads((resp.read() or b"{}").decode("utf-8", errors="replace"))
        out.update(
            {
                "ok": True,
                "http_status": getattr(resp, "status", 200),
                "health": ((body.get("health") or {}).get("status")) if isinstance(body, dict) else None,
                "host": body.get("host") if isinstance(body, dict) else None,
                "timestamp": body.get("timestamp") if isinstance(body, dict) else None,
            }
        )
except Exception as exc:
    out["error"] = str(exc)
print(json.dumps(out))
PY
}

install_node_exporter_local() {
  local version="${1:-1.8.2}"
  local service_user="node_exporter"
  local bin_dir="/usr/local/bin"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local arch_raw arch
  trap 'rm -rf "$tmp_dir"' RETURN

  arch_raw="$(uname -m)"
  case "$arch_raw" in
    x86_64) arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    armv7l|armv6l) arch="armv7" ;;
    *) echo "Skipping node_exporter install: unsupported architecture $arch_raw"; return 1 ;;
  esac

  if ! id "$service_user" >/dev/null 2>&1; then
    sudo useradd --no-create-home --shell /usr/sbin/nologin "$service_user" || true
  fi

  curl -fsSL "https://github.com/prometheus/node_exporter/releases/download/v${version}/node_exporter-${version}.linux-${arch}.tar.gz" -o "${tmp_dir}/node_exporter.tar.gz"
  tar -xzf "${tmp_dir}/node_exporter.tar.gz" -C "${tmp_dir}"
  sudo install "${tmp_dir}/node_exporter-${version}.linux-${arch}/node_exporter" "${bin_dir}/node_exporter"

  sudo tee /etc/systemd/system/node_exporter.service >/dev/null <<'UNIT'
[Unit]
Description=Prometheus Node Exporter
After=network-online.target
Wants=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
  sudo systemctl daemon-reload
  sudo systemctl enable --now node_exporter
  sudo systemctl is-active --quiet node_exporter
}

enroll_monitor_target() {
  local monitor_host="$1"
  local monitor_user="$2"
  local monitor_key_path="$3"
  local node_ip="$4"
  local node_id="$5"
  local scrape_port="${6:-9100}"
  local target_file="${7:-~/monitoring-stack/prometheus/targets/linux_nodes.yml}"

  if [[ -z "$monitor_host" || -z "$monitor_user" || -z "$monitor_key_path" || -z "$node_ip" ]]; then
    echo "Monitoring enroll skipped: missing monitor host/user/key/ip."
    return 1
  fi
  if [[ ! -f "$monitor_key_path" ]]; then
    echo "Monitoring enroll skipped: monitor SSH key missing at $monitor_key_path"
    return 1
  fi

  ssh -i "$monitor_key_path" \
    -o IdentitiesOnly=yes \
    -o BatchMode=yes \
    -o ConnectTimeout=12 \
    -o StrictHostKeyChecking=accept-new \
    "${monitor_user}@${monitor_host}" \
    "python3 - <<'PY'
from pathlib import Path

target = '${node_ip}:${scrape_port}'
path = Path('${target_file}').expanduser()
path.parent.mkdir(parents=True, exist_ok=True)
text = path.read_text() if path.exists() else '- targets:\\n  labels:\\n    role: linux\\n'
if target not in text:
    lines = text.splitlines()
    out = []
    inserted = False
    for ln in lines:
        out.append(ln)
        if ln.strip() == '- targets:' and not inserted:
            out.append(f'  - {target}')
            inserted = True
    if not inserted:
        out.extend(['- targets:', f'  - {target}', '  labels:', '    role: linux'])
    path.write_text('\\n'.join(out).rstrip() + '\\n')
PY
curl -fsS -X POST http://localhost:9090/-/reload >/dev/null || true"
}

# --- minimal prompts ---
NODE_ID="$(prompt 'Node ID (for Dashburg UI)' "$DEFAULT_NODE_ID")"
NODE_LABEL="$(prompt 'Node label (for Dashburg UI)' "$DEFAULT_NODE_LABEL")"
NODE_IP="$(prompt 'Node IP or hostname reachable from Hub' "$DEFAULT_NODE_IP")"
LISTEN_PORT="$(prompt 'Runner listen port' "$DEFAULT_LISTEN_PORT")"
DEPLOY_USER="$(prompt 'Run runner as user (all paths derived from this home)' "$USER")"
DEPLOY_HOME="$(user_home "$DEPLOY_USER")"
if [[ -z "$DEPLOY_HOME" || ! -d "$DEPLOY_HOME" ]]; then
  echo "Could not resolve home directory for user: $DEPLOY_USER"
  exit 1
fi

echo "Using deploy user home: $DEPLOY_HOME"
RUNNER_USER="$(prompt 'Runner service user (default: deploy user for consistent ownership)' "$DEPLOY_USER")"
if [[ "$RUNNER_USER" != "$DEPLOY_USER" ]]; then
  echo "Warning: RUNNER_USER (${RUNNER_USER}) differs from DEPLOY_USER (${DEPLOY_USER})."
  echo "This can create ownership differences under ${DEPLOY_HOME}/runner."
  if [[ "$(prompt_yes_no 'Continue with different runner user?' 'n')" != "y" ]]; then
    echo "Aborting so you can re-run with matching user ownership."
    exit 1
  fi
fi
RUNNER_HOME="$(prompt 'Runner install path' "$DEPLOY_HOME/runner")"
CONFIG_PATH="$(prompt 'Runner config path' "$RUNNER_HOME/config/config.yaml")"
SERVICE_NAME="dashburg-runner"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
DATA_DIR="$(prompt 'Runner data dir' "$RUNNER_HOME/data")"
LOG_DIR="$(prompt 'Runner log dir' "$RUNNER_HOME/logs")"
LOG_FILE="$(prompt 'Runner log file' "$RUNNER_HOME/logs/dashburg-runner.log")"
LISTEN_HOST="0.0.0.0"
RUNNER_WORKSPACE_ROOT="$(prompt 'Runner workspace root' "$DEPLOY_HOME/runner")"
INVESTIGATIONS_DIR="$RUNNER_WORKSPACE_ROOT/investigations"
NODE_PROFILE_FILE="$INVESTIGATIONS_DIR/${NODE_ID}-host-profile.md"
REPO_PROFILE_FILE="$INVESTIGATIONS_DIR/${NODE_ID}-repo-profile.md"
RUNNER_MEMORY_HIGH="${RUNNER_MEMORY_HIGH:-768M}"
RUNNER_MEMORY_MAX="${RUNNER_MEMORY_MAX:-1G}"
RUNNER_TASKS_MAX="${RUNNER_TASKS_MAX:-512}"

SUPPORTS_CODEX="$(prompt_yes_no 'Supports codex.exec jobs?' 'y')"
SUPPORTS_TERMINAL="$(prompt_yes_no 'Supports RemoteOps terminal?' 'y')"
APT_UPGRADE_ENABLED="$(prompt_yes_no 'Enable apt.upgrade job type?' 'y')"
WEBAGENT_ENABLED="$(prompt_yes_no 'Enable webagent.run job type?' 'n')"

REPOS_CSV="$(prompt_csv 'Allowed repos' "$DEPLOY_HOME")"
SERVICES_CSV="$(prompt_csv 'Allowed systemd services' 'dashburg-api')"
COMPOSE_CSV="$(prompt_csv 'Allowed docker compose dirs' '')"
ALLOWED_JOB_TYPES_CSV="$(prompt_csv 'Allowed job types (blank means all managed)' '')"

BOOL_CODEX="false"; [[ "$SUPPORTS_CODEX" == "y" ]] && BOOL_CODEX="true"
BOOL_APT="false"; [[ "$APT_UPGRADE_ENABLED" == "y" ]] && BOOL_APT="true"
BOOL_TERMINAL="false"; [[ "$SUPPORTS_TERMINAL" == "y" ]] && BOOL_TERMINAL="true"
BOOL_WEBAGENT="false"; [[ "$WEBAGENT_ENABLED" == "y" ]] && BOOL_WEBAGENT="true"
BASE_URL="http://${NODE_IP}:${LISTEN_PORT}"
ENABLE_NOPASSWD_SUDO="$(prompt_yes_no 'Grant passwordless sudo to deploy user?' 'y')"
SUDOERS_RESULT="skipped"
INSTALL_NODE_EXPORTER_NOW="$(prompt_yes_no 'Install node_exporter on this node now?' 'y')"
ENROLL_MONITOR_TARGET_NOW="$(prompt_yes_no 'Enroll this node into monitorlxc Prometheus targets?' 'y')"
MONITOR_HOST="$(prompt 'Monitor host (for Prometheus target enrollment)' 'monitor.example.local')"
MONITOR_SSH_USER="$(prompt 'Monitor SSH user' 'dashterm')"
MONITOR_SSH_KEY_PATH="$(prompt 'Monitor SSH private key path' "$HOME/.ssh/dashburg_remoteops")"
MONITOR_TARGET_FILE="$(prompt 'Monitor target file path' '~/monitoring-stack/prometheus/targets/linux_nodes.yml')"
MONITOR_ENROLL_RESULT="skipped"
NODE_EXPORTER_INSTALL_RESULT="skipped"

CODEX_SETUP_ENABLED="n"
CODEX_LOGIN_ENABLED="n"
CODEX_PROFILE_GEN_ENABLED="n"
if [[ "$SUPPORTS_CODEX" == "y" ]]; then
  CODEX_SETUP_ENABLED="$(prompt_yes_no 'Install Codex CLI on this node for runner user?' 'y')"
  if [[ "$CODEX_SETUP_ENABLED" == "y" ]]; then
    CODEX_LOGIN_ENABLED="$(prompt_yes_no 'Run interactive \"codex login\" now?' 'y')"
  fi
  CODEX_PROFILE_GEN_ENABLED="$(prompt_yes_no 'Run \"codex exec\" to build server profile markdown files?' 'y')"
fi
CODEX_INSTALL_RESULT="skipped"
CODEX_LOGIN_RESULT="skipped"
CODEX_PROFILE_GEN_RESULT="skipped"
SERVICE_CONFIG_RESULT="pending"

# key flow: hub first (recommended)
USE_HUB_KEYS="$(prompt_yes_no 'Get key_id/shared_secret from Dashburg Hub now? (recommended)' 'y')"
KEY_ID=""
SHARED_SECRET=""
HUB_RESULT_RAW=""
if [[ "$USE_HUB_KEYS" == "y" ]]; then
  HUB_API="$(prompt 'Dashburg Hub API base URL' "$DEFAULT_HUB_API")"
  HUB_ADMIN_TOKEN=""
  HUB_HOST_FROM_API="$(extract_host_from_url "$HUB_API")"
  AUTO_FETCH_HUB_TOKEN="$(prompt_yes_no 'Auto-fetch REMOTEOPS_ADMIN_TOKEN from Hub via SSH key?' 'y')"
  if [[ "$AUTO_FETCH_HUB_TOKEN" == "y" ]]; then
    HUB_SSH_USER="$(prompt 'Hub SSH user for token fetch' 'dashterm')"
    HUB_SSH_KEY_PATH="$(prompt 'Hub SSH private key path for token fetch' "$HOME/.ssh/dashburg_remoteops")"
    if [[ -f "$HUB_SSH_KEY_PATH" && -n "$HUB_HOST_FROM_API" ]]; then
      HUB_ADMIN_TOKEN="$(fetch_remoteops_admin_token_via_ssh "$HUB_HOST_FROM_API" "$HUB_SSH_USER" "$HUB_SSH_KEY_PATH")"
      if [[ -n "$HUB_ADMIN_TOKEN" ]]; then
        echo "Fetched Hub admin token via SSH (masked): $(mask_value "$HUB_ADMIN_TOKEN")"
      else
        echo "Could not auto-fetch Hub admin token via SSH; falling back to manual entry."
      fi
    else
      echo "Hub host or SSH key unavailable for auto-fetch; falling back to manual entry."
    fi
  fi
  if [[ -z "$HUB_ADMIN_TOKEN" ]]; then
    HUB_ADMIN_TOKEN="$(prompt_secret 'Dashburg admin token (input hidden; leave blank if not required)')"
  fi
  HUB_ADMIN_TOKEN="$(echo "$HUB_ADMIN_TOKEN" | tr -d '\r\n' | sed 's/^ *//; s/ *$//')"
  HUB_RESULT_RAW="$(register_with_hub "$HUB_API" "$HUB_ADMIN_TOKEN" "$NODE_ID" "$NODE_LABEL" "$BASE_URL" "$BOOL_CODEX" "$BOOL_TERMINAL" "$REPOS_CSV" "$SERVICES_CSV" "$ALLOWED_JOB_TYPES_CSV")"
  KEY_ID="$(python3 - <<PY
import json
r=json.loads('''$HUB_RESULT_RAW''')
print(r.get('key_id',''))
PY
)"
  SHARED_SECRET="$(python3 - <<PY
import json
r=json.loads('''$HUB_RESULT_RAW''')
print(r.get('secret',''))
PY
)"
  HUB_OK="$(python3 - <<PY
import json
r=json.loads('''$HUB_RESULT_RAW''')
print('y' if r.get('ok') else 'n')
PY
)"
  if [[ "$HUB_OK" != "y" || -z "$KEY_ID" || -z "$SHARED_SECRET" ]]; then
    echo "Hub key retrieval failed; aborting deploy to prevent key mismatch."
    echo "Hub response (sanitized): $(sanitize_json_secrets "$HUB_RESULT_RAW")"
    echo "Fix Hub registration/key generation first, then re-run deploy."
    exit 1
  fi
fi

if [[ -z "$KEY_ID" ]]; then
  DEFAULT_KEY_ID="${NODE_ID}-$(date +%s | tail -c 5)"
  KEY_ID="$(prompt 'Runner key_id (HMAC)' "$DEFAULT_KEY_ID")"
fi
if [[ -z "$SHARED_SECRET" ]]; then
  SHARED_SECRET="$(prompt_secret 'Runner shared_secret (input hidden; blank to auto-generate)')"
  [[ -z "$SHARED_SECRET" ]] && SHARED_SECRET="$(generate_secret)"
fi

WEBAGENT_COMMAND=""
WEBAGENT_NODE_API_BASE="http://127.0.0.1:9477"
WEBAGENT_NODE_API_TOKEN_ENV="WEBAGENT_NODE_API_TOKEN"
WEBAGENT_NODE_API_TOKEN_VALUE=""
WEBAGENT_ENV_FILE="$RUNNER_HOME/config/webagent.env"
WEBAGENT_NODE_ARTIFACTS_DIR="$RUNNER_HOME/artifacts/webagent"
WEBAGENT_TIMEOUT_SECONDS="900"
WEBAGENT_POLL_INTERVAL_SECONDS="2.0"
WEBAGENT_ACTION_TIMEOUT_SECONDS="45"
if [[ "$WEBAGENT_ENABLED" == "y" ]]; then
  WEBAGENT_COMMAND="$(prompt 'webagent_command (blank uses webagent node API mode)' '')"
  WEBAGENT_NODE_API_BASE="$(prompt 'webagent_node_api_base' "$WEBAGENT_NODE_API_BASE")"
  WEBAGENT_NODE_API_TOKEN_ENV="$(prompt 'webagent_node_api_token_env (env var name read by runner)' "$WEBAGENT_NODE_API_TOKEN_ENV")"
  WEBAGENT_NODE_API_TOKEN_VALUE="$(prompt_secret 'webagent_node_api_token value (optional; writes to protected env file, leave blank to manage externally)')"
  WEBAGENT_NODE_ARTIFACTS_DIR="$(prompt 'webagent_node_artifacts_dir' "$WEBAGENT_NODE_ARTIFACTS_DIR")"
  WEBAGENT_TIMEOUT_SECONDS="$(prompt 'webagent_timeout_seconds' "$WEBAGENT_TIMEOUT_SECONDS")"
  WEBAGENT_POLL_INTERVAL_SECONDS="$(prompt 'webagent_poll_interval_seconds' "$WEBAGENT_POLL_INTERVAL_SECONDS")"
  WEBAGENT_ACTION_TIMEOUT_SECONDS="$(prompt 'webagent_action_timeout_seconds' "$WEBAGENT_ACTION_TIMEOUT_SECONDS")"
fi

SSH_TEST_ENABLED="$(prompt_yes_no 'Run SSH self-test to verify terminal path?' 'y')"
SSH_TEST_USER="$(prompt 'SSH test user (used by Hub terminal)' "$DEPLOY_USER")"
SSH_KEY_PATH="$(prompt 'SSH private key path used by Hub terminal' "$HOME/.ssh/dashburg_remoteops")"
SSH_STRICT_HOST_KEY_CHECKING="$(prompt 'Hub SSH strict host key checking mode (accept-new|yes|no)' 'accept-new')"
ENTRY_SCRIPT="$(prompt 'Terminal entry script path on this node' "$(user_home "$SSH_TEST_USER")/dashterm-entry")"

LOCAL_PUB_DEFAULT=""
if [[ -f "${SSH_KEY_PATH}.pub" ]]; then
  LOCAL_PUB_DEFAULT="$(cat "${SSH_KEY_PATH}.pub")"
fi
USE_DASHBURG_MAIN_PUBKEY="$(prompt_yes_no 'Use built-in Dashburg Main public key for terminal SSH auth?' 'y')"
if [[ "$USE_DASHBURG_MAIN_PUBKEY" == "y" ]]; then
  HUB_TERMINAL_PUBKEY="$DEFAULT_DASHBURG_MAIN_PUBKEY"
else
  USE_LOCAL_KEY_PUB="n"
  if [[ -n "$LOCAL_PUB_DEFAULT" ]]; then
    USE_LOCAL_KEY_PUB="$(prompt_yes_no "Use local pubkey file ${SSH_KEY_PATH}.pub for terminal SSH auth?" 'y')"
  fi
  if [[ "$USE_LOCAL_KEY_PUB" == "y" ]]; then
    HUB_TERMINAL_PUBKEY="$LOCAL_PUB_DEFAULT"
  else
    HUB_TERMINAL_PUBKEY="$(prompt_secret 'Hub terminal public key to authorize for SSH user (input hidden; blank to skip)')"
  fi
fi

mkdir -p .deploy
STAMP="$(date +%Y%m%d-%H%M%S)"
SUMMARY_FILE=".deploy/deploy-summary-${NODE_ID}-${STAMP}.md"
CONFIG_ARTIFACT=".deploy/config-${NODE_ID}-${STAMP}.yaml"
SERVICE_ARTIFACT=".deploy/install_runner-${NODE_ID}-${STAMP}.service"

TMP_CONFIG="$(mktemp)"
cat > "$TMP_CONFIG" <<EOF
host: ${LISTEN_HOST}
port: ${LISTEN_PORT}
node_id: "${NODE_ID}"

key_id: ${KEY_ID}
shared_secret: ${SHARED_SECRET}
auth_max_skew_seconds: 60
auth_required: true

data_dir: ${DATA_DIR}
log_file: ${LOG_FILE}

apt_upgrade_enabled: ${BOOL_APT}
codex_enabled: ${BOOL_CODEX}
webagent_enabled: ${BOOL_WEBAGENT}
webagent_command: "${WEBAGENT_COMMAND}"
webagent_node_api_base: "${WEBAGENT_NODE_API_BASE}"
webagent_node_api_token_env: "${WEBAGENT_NODE_API_TOKEN_ENV}"
webagent_node_api_token: ""
webagent_node_artifacts_dir: "${WEBAGENT_NODE_ARTIFACTS_DIR}"
webagent_timeout_seconds: ${WEBAGENT_TIMEOUT_SECONDS}
webagent_poll_interval_seconds: ${WEBAGENT_POLL_INTERVAL_SECONDS}
webagent_action_timeout_seconds: ${WEBAGENT_ACTION_TIMEOUT_SECONDS}

allowed_repos:
$(split_csv_to_yaml_list "$REPOS_CSV" "  ")
allowed_services:
$(split_csv_to_yaml_list "$SERVICES_CSV" "  ")
allowed_compose_dirs:
$(split_csv_to_yaml_list "$COMPOSE_CSV" "  ")
EOF

TMP_SERVICE="$(mktemp)"
cat > "$TMP_SERVICE" <<EOF
[Unit]
Description=Dashburg Runner
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUNNER_USER}
Group=${RUNNER_USER}
WorkingDirectory=${RUNNER_HOME}
Environment=RUNNER_CONFIG=${CONFIG_PATH}
EnvironmentFile=-${WEBAGENT_ENV_FILE}
ExecStart=${RUNNER_HOME}/.venv/bin/python ${RUNNER_HOME}/run.py
Restart=always
RestartSec=2
MemoryAccounting=true
MemoryHigh=${RUNNER_MEMORY_HIGH}
MemoryMax=${RUNNER_MEMORY_MAX}
TasksMax=${RUNNER_TASKS_MAX}
LimitNOFILE=65536
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=${RUNNER_HOME} ${DATA_DIR} ${LOG_DIR}

[Install]
WantedBy=multi-user.target
EOF

cp "$TMP_CONFIG" "$CONFIG_ARTIFACT"
cp "$TMP_SERVICE" "$SERVICE_ARTIFACT"

echo ""
echo "Installing runner service..."

if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  sudo useradd --system --create-home --shell /usr/sbin/nologin "$RUNNER_USER" || true
fi

sudo install -d -m 755 -o "$RUNNER_USER" -g "$RUNNER_USER" "$RUNNER_HOME"
sudo install -d -m 755 -o "$RUNNER_USER" -g "$RUNNER_USER" "$DATA_DIR"
if [[ "$LOG_DIR" == "/var/log" ]]; then
  sudo install -d -m 755 /var/log
else
  sudo install -d -m 755 -o "$RUNNER_USER" -g "$RUNNER_USER" "$LOG_DIR"
fi
sudo install -m 664 -o "$RUNNER_USER" -g "$RUNNER_USER" /dev/null "$LOG_FILE"
sudo install -d -m 755 -o "$RUNNER_USER" -g "$RUNNER_USER" "$RUNNER_WORKSPACE_ROOT"
sudo install -d -m 755 -o "$RUNNER_USER" -g "$RUNNER_USER" "$INVESTIGATIONS_DIR"

if [[ "$ENABLE_NOPASSWD_SUDO" == "y" ]]; then
  if configure_passwordless_sudo "$RUNNER_USER"; then
    SUDOERS_RESULT="ok"
  else
    SUDOERS_RESULT="failed"
    echo "Failed to configure passwordless sudo for ${RUNNER_USER}; aborting deploy."
    exit 1
  fi
fi

sudo rsync -a --delete ./ "$RUNNER_HOME"/
sudo chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_HOME" "$DATA_DIR" "$RUNNER_WORKSPACE_ROOT"
sudo chown "$RUNNER_USER:$RUNNER_USER" "$LOG_FILE" || true

sudo -u "$RUNNER_USER" python3 -m venv "$RUNNER_HOME/.venv"
sudo -u "$RUNNER_USER" "$RUNNER_HOME/.venv/bin/pip" install --upgrade pip
sudo -u "$RUNNER_USER" "$RUNNER_HOME/.venv/bin/pip" install -r "$RUNNER_HOME/requirements.txt"

if [[ "$CODEX_SETUP_ENABLED" == "y" ]]; then
  set +e
  install_codex_for_user "$RUNNER_USER"
  CODEX_INSTALL_CODE=$?
  set -e
  if [[ $CODEX_INSTALL_CODE -eq 0 ]]; then
    CODEX_INSTALL_RESULT="ok"
  else
    CODEX_INSTALL_RESULT="failed"
  fi

  if [[ "$CODEX_LOGIN_ENABLED" == "y" ]]; then
    set +e
    codex_login_for_user "$RUNNER_USER"
    CODEX_LOGIN_CODE=$?
    set -e
    if [[ $CODEX_LOGIN_CODE -eq 0 ]]; then
      CODEX_LOGIN_RESULT="ok"
    else
      CODEX_LOGIN_RESULT="failed"
    fi
  fi
fi

sudo install -d -m 755 -o "$RUNNER_USER" -g "$RUNNER_USER" "$(dirname "$CONFIG_PATH")"
sudo install -o "$RUNNER_USER" -g "$RUNNER_USER" -m 640 "$TMP_CONFIG" "$CONFIG_PATH"
if [[ "$WEBAGENT_ENABLED" == "y" && -n "$WEBAGENT_NODE_API_TOKEN_VALUE" ]]; then
  TMP_WEBAGENT_ENV="$(mktemp)"
  cat > "$TMP_WEBAGENT_ENV" <<EOF
${WEBAGENT_NODE_API_TOKEN_ENV}=${WEBAGENT_NODE_API_TOKEN_VALUE}
EOF
  sudo install -d -m 755 -o "$RUNNER_USER" -g "$RUNNER_USER" "$(dirname "$WEBAGENT_ENV_FILE")"
  sudo install -o "$RUNNER_USER" -g "$RUNNER_USER" -m 640 "$TMP_WEBAGENT_ENV" "$WEBAGENT_ENV_FILE"
  rm -f "$TMP_WEBAGENT_ENV"
fi
sudo install -o root -g root -m 644 "$TMP_SERVICE" "$SERVICE_PATH"
SERVICE_CONFIG_RESULT="$(ensure_service_runner_config_file "$SERVICE_PATH" "$CONFIG_PATH" || true)"
sudo rm -f "$RUNNER_HOME/config.json" || true

APPLIED_KEY_ID="$(sudo awk -F': ' '/^key_id:/{print $2;exit}' "$CONFIG_PATH" | tr -d '\r')"
APPLIED_SECRET="$(sudo awk -F': ' '/^shared_secret:/{print $2;exit}' "$CONFIG_PATH" | tr -d '\r')"
if [[ "$APPLIED_KEY_ID" != "$KEY_ID" || "$APPLIED_SECRET" != "$SHARED_SECRET" ]]; then
  echo "Config verification failed after write."
  echo "Expected key_id(masked)=$(mask_value "$KEY_ID")"
  echo "Applied  key_id(masked)=$(mask_value "$APPLIED_KEY_ID")"
  exit 1
fi

if [[ ! -f "$NODE_PROFILE_FILE" ]]; then
  cat <<EOF | sudo -u "$RUNNER_USER" tee "$NODE_PROFILE_FILE" >/dev/null
# Host Profile - ${NODE_ID}

## Identity
- node_id: ${NODE_ID}
- label: ${NODE_LABEL}
- host: ${NODE_IP}
- runner_base_url: ${BASE_URL}
- deploy_user: ${RUNNER_USER}

## Access
- ssh_user: ${SSH_TEST_USER}
- ssh_key_path_hint: ${SSH_KEY_PATH}
- terminal_entry: ${ENTRY_SCRIPT}

## Runtime Paths
- runner_home: ${RUNNER_HOME}
- runner_workspace_root: ${RUNNER_WORKSPACE_ROOT}
- investigations_dir: ${INVESTIGATIONS_DIR}
- data_dir: ${DATA_DIR}
- log_file: ${LOG_FILE}

## Services
- dashburg-runner (systemd)

## Observations
- Add host-level findings here.

## Known Issues / Fixes
- Track recurring host issues and known-good fixes.
EOF
fi

if [[ ! -f "$REPO_PROFILE_FILE" ]]; then
  cat <<EOF | sudo -u "$RUNNER_USER" tee "$REPO_PROFILE_FILE" >/dev/null
# Repo Profile - ${NODE_ID}

## Allowed Repos
${REPOS_CSV}

## Allowed Services
${SERVICES_CSV}

## Allowed Job Types
${ALLOWED_JOB_TYPES_CSV:-<all managed>}

## Layout / Entrypoints
- Document repo locations and entry commands.

## Settings / Config Paths
- Add discovered config files and env files.

## Known Issues / Fixes
- Add repo-specific troubleshooting notes.
EOF
fi

if [[ "$CODEX_PROFILE_GEN_ENABLED" == "y" ]]; then
  set +e
  run_codex_exec_profiles \
    "$RUNNER_USER" \
    "$INVESTIGATIONS_DIR" \
    "$NODE_PROFILE_FILE" \
    "$REPO_PROFILE_FILE" \
    "$NODE_ID" \
    "$NODE_LABEL" \
    "$NODE_IP" \
    "$BASE_URL" \
    "$REPOS_CSV" \
    "$SERVICES_CSV" \
    "${ALLOWED_JOB_TYPES_CSV:-<all managed>}" \
    "$DEPLOY_USER" \
    "$RUNNER_HOME" \
    "$DATA_DIR" \
    "$LOG_FILE"
  CODEX_PROFILE_GEN_CODE=$?
  set -e
  if [[ $CODEX_PROFILE_GEN_CODE -eq 0 ]]; then
    CODEX_PROFILE_GEN_RESULT="ok"
  else
    CODEX_PROFILE_GEN_RESULT="failed"
  fi
fi

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
if [[ -x "$RUNNER_HOME/scripts/ensure_nfs_mem_mount.sh" ]]; then
  sudo "$RUNNER_HOME/scripts/ensure_nfs_mem_mount.sh" || true
fi
sudo systemctl status "$SERVICE_NAME" --no-pager || true

if [[ "$INSTALL_NODE_EXPORTER_NOW" == "y" ]]; then
  set +e
  install_node_exporter_local "1.8.2"
  NODE_EXPORTER_INSTALL_CODE=$?
  set -e
  if [[ $NODE_EXPORTER_INSTALL_CODE -eq 0 ]]; then
    NODE_EXPORTER_INSTALL_RESULT="ok"
  else
    NODE_EXPORTER_INSTALL_RESULT="failed"
  fi
fi

if [[ "$ENROLL_MONITOR_TARGET_NOW" == "y" ]]; then
  set +e
  enroll_monitor_target "$MONITOR_HOST" "$MONITOR_SSH_USER" "$MONITOR_SSH_KEY_PATH" "$NODE_IP" "$NODE_ID" "9100" "$MONITOR_TARGET_FILE"
  MONITOR_ENROLL_CODE=$?
  set -e
  if [[ $MONITOR_ENROLL_CODE -eq 0 ]]; then
    MONITOR_ENROLL_RESULT="ok"
  else
    MONITOR_ENROLL_RESULT="failed"
  fi
fi

MONITOR_RESULT_RAW="$(check_runner_monitor "$BASE_URL")"
MONITOR_OK="$(python3 - <<PY
import json
r=json.loads('''$MONITOR_RESULT_RAW''')
print('y' if r.get('ok') else 'n')
PY
)"
if [[ "$MONITOR_OK" != "y" ]]; then
  echo "Warning: host-monitor endpoint check failed."
  echo "Monitor check response: $MONITOR_RESULT_RAW"
fi

rm -f "$TMP_CONFIG" "$TMP_SERVICE"

if [[ -n "$HUB_TERMINAL_PUBKEY" ]]; then
  echo "Authorizing terminal public key for SSH user ${SSH_TEST_USER}"
  append_pubkey_for_user "$SSH_TEST_USER" "$HUB_TERMINAL_PUBKEY" || true
fi

SSH_TEST_RESULT="skipped"
SSH_OUT=""
if [[ "$SSH_TEST_ENABLED" == "y" ]]; then
  ENTRY_SCRIPT="$(create_entry_script_if_missing "$SSH_TEST_USER" "$ENTRY_SCRIPT")"
  set +e
  SSH_OUT=$(ssh -i "$SSH_KEY_PATH" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking="$SSH_STRICT_HOST_KEY_CHECKING" "${SSH_TEST_USER}@${NODE_IP}" "test -x \"${ENTRY_SCRIPT}\" && echo SSH_SELFTEST_OK" 2>&1)
  SSH_CODE=$?
  set -e
  if [[ $SSH_CODE -eq 0 && "$SSH_OUT" == *"SSH_SELFTEST_OK"* ]]; then
    SSH_TEST_RESULT="ok"
  else
    SSH_TEST_RESULT="failed"
  fi
fi

# permission checks
PERM_ERRORS=0
check_rw_as_user "$RUNNER_USER" "$RUNNER_HOME" "-w" || PERM_ERRORS=$((PERM_ERRORS+1))
check_rw_as_user "$RUNNER_USER" "$CONFIG_PATH" "-r" || PERM_ERRORS=$((PERM_ERRORS+1))
check_rw_as_user "$RUNNER_USER" "$DATA_DIR" "-w" || PERM_ERRORS=$((PERM_ERRORS+1))
check_rw_as_user "$RUNNER_USER" "$LOG_FILE" "-w" || PERM_ERRORS=$((PERM_ERRORS+1))

MASKED_KEY_ID="$(mask_value "$KEY_ID")"
MASKED_SHARED_SECRET="$(mask_value "$SHARED_SECRET")"
MASKED_HUB_ADMIN_TOKEN="$(mask_value "${HUB_ADMIN_TOKEN:-}")"
MASKED_WEBAGENT_NODE_API_TOKEN="$(mask_value "${WEBAGENT_NODE_API_TOKEN_VALUE:-}")"
MASKED_SSH_KEY_PATH="$(mask_path "$SSH_KEY_PATH")"
HUB_RESULT_SAFE="$(sanitize_json_secrets "$HUB_RESULT_RAW")"

{
  echo "# Dashburg Runner Deployment Summary"
  echo
  echo "## Node"
  echo "- id: ${NODE_ID}"
  echo "- label: ${NODE_LABEL}"
  echo "- base_url: ${BASE_URL}"
  echo "- supports_codex: ${BOOL_CODEX}"
  echo "- supports_terminal: ${BOOL_TERMINAL}"
  echo
  echo "## Sudoers"
  echo "- passwordless_requested: ${ENABLE_NOPASSWD_SUDO}"
  echo "- passwordless_config: ${SUDOERS_RESULT}"
  echo
  echo "## NodeHealth API"
  echo "- endpoint: ${BASE_URL}/v1/host-monitor/status"
  echo "- probe: ${MONITOR_RESULT_RAW}"
  echo
  echo "## Runtime"
  echo "- runner_user: ${RUNNER_USER}"
  echo "- runner_home: ${RUNNER_HOME}"
  echo "- config_path: ${CONFIG_PATH}"
  echo "- service_runner_config_check: ${SERVICE_CONFIG_RESULT}"
  echo "- data_dir: ${DATA_DIR}"
  echo "- log_file: ${LOG_FILE}"
  echo
  echo "## Runner Auth"
  echo "- key_id(masked): ${MASKED_KEY_ID}"
  echo "- shared_secret(masked): ${MASKED_SHARED_SECRET}"
  echo
  echo "## Allowlists"
  echo "- allowed_repos: ${REPOS_CSV}"
  echo "- allowed_services: ${SERVICES_CSV}"
  echo "- allowed_compose_dirs: ${COMPOSE_CSV}"
  echo "- allowed_job_types: ${ALLOWED_JOB_TYPES_CSV:-<all managed>}"
  echo
  echo "## WebAgent"
  echo "- enabled: ${BOOL_WEBAGENT}"
  echo "- command: ${WEBAGENT_COMMAND:-<none>}"
  echo "- node_api_base: ${WEBAGENT_NODE_API_BASE}"
  echo "- node_api_token_env: ${WEBAGENT_NODE_API_TOKEN_ENV}"
  echo "- node_api_token(masked): ${MASKED_WEBAGENT_NODE_API_TOKEN:-}"
  echo "- node_env_file: ${WEBAGENT_ENV_FILE}"
  echo "- node_artifacts_dir: ${WEBAGENT_NODE_ARTIFACTS_DIR}"
  echo "- timeout_seconds: ${WEBAGENT_TIMEOUT_SECONDS}"
  echo "- poll_interval_seconds: ${WEBAGENT_POLL_INTERVAL_SECONDS}"
  echo "- action_timeout_seconds: ${WEBAGENT_ACTION_TIMEOUT_SECONDS}"
  echo
  echo "## Terminal"
  echo "- ssh_test: ${SSH_TEST_RESULT}"
  echo "- ssh_user: ${SSH_TEST_USER}"
  echo "- ssh_key_path(masked): ${MASKED_SSH_KEY_PATH}"
  echo "- ssh_strict_host_key_checking: ${SSH_STRICT_HOST_KEY_CHECKING}"
  echo "- terminal_entry: ${ENTRY_SCRIPT}"
  echo "- investigations_dir: ${INVESTIGATIONS_DIR}"
  echo "- node_profile_file: ${NODE_PROFILE_FILE}"
  echo "- repo_profile_file: ${REPO_PROFILE_FILE}"
  echo
  echo "## Monitoring Enrollment"
  echo "- install_node_exporter_requested: ${INSTALL_NODE_EXPORTER_NOW}"
  echo "- install_node_exporter_result: ${NODE_EXPORTER_INSTALL_RESULT}"
  echo "- enroll_monitor_target_requested: ${ENROLL_MONITOR_TARGET_NOW}"
  echo "- enroll_monitor_target_result: ${MONITOR_ENROLL_RESULT}"
  echo "- monitor_host: ${MONITOR_HOST}"
  echo "- monitor_target_file: ${MONITOR_TARGET_FILE}"
  echo
  echo "## Codex Setup"
  echo "- enabled: ${CODEX_SETUP_ENABLED}"
  echo "- install: ${CODEX_INSTALL_RESULT}"
  echo "- login_requested: ${CODEX_LOGIN_ENABLED}"
  echo "- login: ${CODEX_LOGIN_RESULT}"
  echo "- profile_gen_requested: ${CODEX_PROFILE_GEN_ENABLED}"
  echo "- profile_gen: ${CODEX_PROFILE_GEN_RESULT}"
  echo
  echo "## Permission Checks"
  echo "- errors: ${PERM_ERRORS}"
  echo
  echo "## WebUI Add Node Values"
  echo "- id=${NODE_ID}"
  echo "- label=${NODE_LABEL}"
  echo "- base_url=${BASE_URL}"
  echo "- supports_codex=${BOOL_CODEX}"
  echo "- supports_terminal=${BOOL_TERMINAL}"
  echo "- allowed_repos=${REPOS_CSV}"
  echo "- allowed_services=${SERVICES_CSV}"
  echo "- allowed_job_types=${ALLOWED_JOB_TYPES_CSV}"
  echo
  echo "## Hub Env (terminal)"
  echo "REMOTEOPS_SSH_USER=${SSH_TEST_USER}"
  echo "REMOTEOPS_SSH_KEY_PATH=${MASKED_SSH_KEY_PATH}"
  echo "REMOTEOPS_SSH_STRICT_HOST_KEY_CHECKING=${SSH_STRICT_HOST_KEY_CHECKING}"
  echo "REMOTEOPS_TERMINAL_ENTRY=${ENTRY_SCRIPT}"
  echo
  echo "## Token Hints (masked)"
  echo "- hub_admin_token(masked): ${MASKED_HUB_ADMIN_TOKEN:-<not provided>}"
  echo "- note: set REMOTEOPS_ADMIN_TOKEN and chat_client_token in Hub settings/env as needed"
  echo
  echo "## Generated Artifacts"
  echo "- config_yaml: ${CONFIG_ARTIFACT}"
  echo "- service_unit: ${SERVICE_ARTIFACT}"
  if [[ -n "$HUB_RESULT_RAW" ]]; then
    echo
    echo "## Hub Registration"
    echo "- raw(sanitized): ${HUB_RESULT_SAFE}"
  fi
} | tee "$SUMMARY_FILE"

if [[ "$SSH_TEST_ENABLED" == "y" && "$SSH_TEST_RESULT" == "failed" ]]; then
  echo ""
  echo "SSH self-test failed. Output:"
  echo "$SSH_OUT"
fi

if [[ "$PERM_ERRORS" -gt 0 ]]; then
  echo ""
  echo "Permission checks failed (${PERM_ERRORS}). Fix ownership/modes before production use."
fi

echo ""
echo "Deployment summary written to: $SUMMARY_FILE"
echo "Generated config artifact: $CONFIG_ARTIFACT"
echo "Generated service artifact: $SERVICE_ARTIFACT"
echo "Done."
