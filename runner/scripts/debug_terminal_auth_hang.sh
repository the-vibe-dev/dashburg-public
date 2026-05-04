#!/usr/bin/env bash
set -euo pipefail

# Debug helper for deploy script hangs around:
# "Authorizing terminal public key for SSH user ..."
#
# Usage:
#   ./scripts/debug_terminal_auth_hang.sh watch
#   ./scripts/debug_terminal_auth_hang.sh test [ssh_user] [pubkey_path]

mode="${1:-watch}"

watch_mode() {
  echo "[debug] Looking for deploy_runner_node.sh process..."
  pgrep -af deploy_runner_node.sh || true
  pid="$(pgrep -f deploy_runner_node.sh | head -n1 || true)"
  if [[ -z "${pid}" ]]; then
    echo "[debug] No deploy_runner_node.sh process found."
    exit 1
  fi

  echo "[debug] PID=${pid}"
  ps -fp "${pid}" || true
  pstree -ap "${pid}" || true
  echo "[debug] Attaching strace (ctrl+c to stop)..."
  sudo strace -f -p "${pid}" -s 200 -e trace=execve,openat,read,write,wait4 2>&1 | tee /tmp/deploy-strace.log
}

test_mode() {
  ssh_user="${1:-trilobyte}"
  pubkey_path="${2:-$HOME/.ssh/dashburg_remoteops.pub}"

  if [[ ! -f "${pubkey_path}" ]]; then
    echo "[test] Public key file not found: ${pubkey_path}"
    exit 1
  fi

  pubkey="$(cat "${pubkey_path}")"
  home_dir="$(getent passwd "${ssh_user}" | cut -d: -f6)"
  if [[ -z "${home_dir}" ]]; then
    echo "[test] Could not resolve home dir for user: ${ssh_user}"
    exit 1
  fi

  echo "[test] Updating authorized_keys for user=${ssh_user} home=${home_dir}"
  sudo install -d -m 700 -o "${ssh_user}" -g "${ssh_user}" "${home_dir}/.ssh"
  sudo touch "${home_dir}/.ssh/authorized_keys"
  sudo chown "${ssh_user}:${ssh_user}" "${home_dir}/.ssh/authorized_keys"
  sudo chmod 600 "${home_dir}/.ssh/authorized_keys"
  sudo grep -Fq "${pubkey}" "${home_dir}/.ssh/authorized_keys" || printf '%s\n' "${pubkey}" | sudo tee -a "${home_dir}/.ssh/authorized_keys" >/dev/null
  echo "[test] authorized_keys update complete"
}

case "${mode}" in
  watch)
    watch_mode
    ;;
  test)
    test_mode "${2:-trilobyte}" "${3:-$HOME/.ssh/dashburg_remoteops.pub}"
    ;;
  *)
    echo "Usage:"
    echo "  $0 watch"
    echo "  $0 test [ssh_user] [pubkey_path]"
    exit 1
    ;;
esac
