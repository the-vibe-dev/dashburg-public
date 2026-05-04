#!/usr/bin/env bash
set -euo pipefail

RUNNER_USER="${RUNNER_USER:-dashburg-runner}"
RUNNER_HOME="/opt/dashburg-runner"
CONFIG_PATH="/etc/dashburg-runner/config.yaml"
SERVICE_PATH="/etc/systemd/system/dashburg-runner.service"
WEBAGENT_ENV_PATH="/etc/dashburg-runner/webagent.env"
ENABLE_NOPASSWD_SUDO="${ENABLE_NOPASSWD_SUDO:-true}"

check_python_venv_deps() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required."
    exit 1
  fi

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

ensure_runner_venv() {
  if ! sudo test -x "$RUNNER_HOME/.venv/bin/python"; then
    sudo python3 -m venv "$RUNNER_HOME/.venv"
  fi
  if ! sudo "$RUNNER_HOME/.venv/bin/python" -m pip --version >/dev/null 2>&1; then
    sudo rm -rf "$RUNNER_HOME/.venv"
    sudo python3 -m venv "$RUNNER_HOME/.venv"
  fi
}

configure_passwordless_sudo() {
  local sudoers_path="/etc/sudoers.d/90-dashburg-${RUNNER_USER}-nopasswd"
  local rule="${RUNNER_USER} ALL=(ALL) NOPASSWD:ALL"
  printf '%s\n' "$rule" | sudo tee "$sudoers_path" >/dev/null
  sudo chmod 440 "$sudoers_path"
  sudo visudo -cf "$sudoers_path" >/dev/null
}

sudo useradd --system --create-home --shell /usr/sbin/nologin "$RUNNER_USER" || true
if [[ "$ENABLE_NOPASSWD_SUDO" == "true" ]]; then
  configure_passwordless_sudo
fi
sudo mkdir -p "$RUNNER_HOME" /etc/dashburg-runner /var/lib/dashburg-runner
sudo chown root:"$RUNNER_USER" /etc/dashburg-runner
sudo chmod 750 /etc/dashburg-runner
sudo chown -R "$RUNNER_USER":"$RUNNER_USER" "$RUNNER_HOME" /var/lib/dashburg-runner

sudo rsync -a --delete ./ "$RUNNER_HOME"/

ensure_runner_venv
sudo "$RUNNER_HOME/.venv/bin/python" -m pip install --upgrade pip
sudo "$RUNNER_HOME/.venv/bin/python" -m pip install -r "$RUNNER_HOME/requirements.txt"

if [[ ! -f "$CONFIG_PATH" ]]; then
  sudo cp "$RUNNER_HOME/config.example.yaml" "$CONFIG_PATH"
fi
sudo sed -i 's|^host:.*|host: 0.0.0.0|' "$CONFIG_PATH" || true
sudo sed -i 's|^port:.*|port: 8844|' "$CONFIG_PATH" || true
sudo sed -i 's|^data_dir:.*|data_dir: /var/lib/dashburg-runner|' "$CONFIG_PATH" || true
sudo sed -i 's|^log_file:.*|log_file: /var/log/dashburg-runner.log|' "$CONFIG_PATH" || true
if ! sudo grep -q '^node_id:' "$CONFIG_PATH"; then
  sudo tee -a "$CONFIG_PATH" >/dev/null <<EOF
node_id: "$(hostname -s)"
EOF
fi
if ! sudo grep -q '^webagent_node_api_token_env:' "$CONFIG_PATH"; then
  sudo tee -a "$CONFIG_PATH" >/dev/null <<'EOF'
webagent_node_api_token_env: "WEBAGENT_NODE_API_TOKEN"
EOF
fi
legacy_token="$(sudo awk -F': ' '/^webagent_node_api_token:/{gsub(/^"|"$/, "", $2); print $2; exit}' "$CONFIG_PATH" 2>/dev/null || true)"
if [[ -n "$legacy_token" ]]; then
  token_env_name="$(sudo awk -F': ' '/^webagent_node_api_token_env:/{gsub(/^"|"$/, "", $2); print $2; exit}' "$CONFIG_PATH" 2>/dev/null || true)"
  token_env_name="${token_env_name:-WEBAGENT_NODE_API_TOKEN}"
  sudo install -d -m 750 -o root -g "$RUNNER_USER" /etc/dashburg-runner
  sudo tee "$WEBAGENT_ENV_PATH" >/dev/null <<EOF
${token_env_name}=${legacy_token}
EOF
  sudo chown root:"$RUNNER_USER" "$WEBAGENT_ENV_PATH"
  sudo chmod 640 "$WEBAGENT_ENV_PATH"
  sudo sed -i 's|^webagent_node_api_token:.*|webagent_node_api_token: ""|' "$CONFIG_PATH"
fi
sudo chown root:"$RUNNER_USER" "$CONFIG_PATH"
sudo chmod 640 "$CONFIG_PATH"

sudo cp "$RUNNER_HOME/scripts/install_runner.service" "$SERVICE_PATH"
sudo systemctl daemon-reload
sudo systemctl enable --now dashburg-runner.service
if [[ -x "$RUNNER_HOME/scripts/install_mailbox_cron.sh" ]]; then
  sudo "$RUNNER_HOME/scripts/install_mailbox_cron.sh"
fi
if [[ -x "$RUNNER_HOME/scripts/ensure_nfs_mem_mount.sh" ]]; then
  sudo "$RUNNER_HOME/scripts/ensure_nfs_mem_mount.sh" || true
fi
sudo systemctl status dashburg-runner.service --no-pager
