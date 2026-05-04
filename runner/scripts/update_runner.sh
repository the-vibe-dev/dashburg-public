#!/usr/bin/env bash
set -euo pipefail

RUNNER_HOME="/opt/dashburg-runner"
SERVICE_PATH="/etc/systemd/system/dashburg-runner.service"
CONFIG_PATH="/etc/dashburg-runner/config.yaml"
WEBAGENT_ENV_PATH="/etc/dashburg-runner/webagent.env"
DEFAULT_RUNNER_USER="dashburg-runner"

detect_service_user() {
  if [[ -f "$SERVICE_PATH" ]]; then
    local parsed
    parsed="$(awk -F= '/^User=/{print $2; exit}' "$SERVICE_PATH" 2>/dev/null | tr -d '[:space:]')"
    if [[ -n "$parsed" ]]; then
      echo "$parsed"
      return
    fi
  fi
  echo "$DEFAULT_RUNNER_USER"
}

RUNNER_USER="$(detect_service_user)"

ensure_runner_venv() {
  if ! sudo test -x "$RUNNER_HOME/.venv/bin/python"; then
    sudo python3 -m venv "$RUNNER_HOME/.venv"
  fi
  if ! sudo "$RUNNER_HOME/.venv/bin/python" -m pip --version >/dev/null 2>&1; then
    sudo rm -rf "$RUNNER_HOME/.venv"
    sudo python3 -m venv "$RUNNER_HOME/.venv"
  fi
}

sudo useradd --system --create-home --shell /usr/sbin/nologin "$RUNNER_USER" || true
sudo rsync -a --delete ./ "$RUNNER_HOME"/
ensure_runner_venv
sudo "$RUNNER_HOME/.venv/bin/python" -m pip install -r "$RUNNER_HOME/requirements.txt"
if [[ -f "$CONFIG_PATH" ]]; then
  sudo install -d -m 750 -o root -g "$RUNNER_USER" /etc/dashburg-runner
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
    sudo chown root:"$RUNNER_USER" "$WEBAGENT_ENV_PATH" || true
    sudo chmod 640 "$WEBAGENT_ENV_PATH"
    sudo sed -i 's|^webagent_node_api_token:.*|webagent_node_api_token: ""|' "$CONFIG_PATH"
  fi
  sudo chown root:"$RUNNER_USER" "$CONFIG_PATH" || true
  sudo chmod 640 "$CONFIG_PATH" || true
fi
if [[ -f "$SERVICE_PATH" ]]; then
  current_cfg="$(awk -F= '/^Environment=RUNNER_CONFIG=/{print $3; exit}' "$SERVICE_PATH" 2>/dev/null || true)"
  if [[ -z "$current_cfg" || -d "$current_cfg" || "$current_cfg" != "$CONFIG_PATH" ]]; then
    sudo sed -i "s|^Environment=RUNNER_CONFIG=.*|Environment=RUNNER_CONFIG=$CONFIG_PATH|" "$SERVICE_PATH"
  fi
  if ! sudo grep -q '^EnvironmentFile=-/etc/dashburg-runner/webagent.env' "$SERVICE_PATH"; then
    sudo sed -i '/^Environment=RUNNER_CONFIG=.*/a EnvironmentFile=-/etc/dashburg-runner/webagent.env' "$SERVICE_PATH"
  fi
  sudo systemctl daemon-reload
fi
if [[ -x "$RUNNER_HOME/scripts/install_mailbox_cron.sh" ]]; then
  sudo "$RUNNER_HOME/scripts/install_mailbox_cron.sh"
fi
if [[ -x "$RUNNER_HOME/scripts/ensure_nfs_mem_mount.sh" ]]; then
  sudo "$RUNNER_HOME/scripts/ensure_nfs_mem_mount.sh" || true
fi
sudo systemctl restart dashburg-runner.service
sudo systemctl status dashburg-runner.service --no-pager
