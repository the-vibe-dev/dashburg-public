#!/usr/bin/env bash
set -euo pipefail

HUB_URL="http://hub.example.local:8431"
TOKEN_FILE="/etc/dashburg/remoteops-client-token"
PUBLIC_KEY_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hub-url) HUB_URL="$2"; shift 2 ;;
    --token-file) TOKEN_FILE="$2"; shift 2 ;;
    --hub-pubkey) PUBLIC_KEY_PATH="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

sudo useradd -m -s /bin/bash dashterm 2>/dev/null || true
sudo mkdir -p /home/dashterm/.ssh /etc/dashburg
sudo chown -R dashterm:dashterm /home/dashterm/.ssh
sudo chmod 700 /home/dashterm/.ssh

if [[ -n "$PUBLIC_KEY_PATH" && -f "$PUBLIC_KEY_PATH" ]]; then
  sudo install -m 600 -o dashterm -g dashterm "$PUBLIC_KEY_PATH" /home/dashterm/.ssh/authorized_keys
else
  echo "No --hub-pubkey provided. Add Dashburg hub pubkey to /home/dashterm/.ssh/authorized_keys"
fi

sudo install -m 755 /dev/stdin /usr/local/bin/dashterm-entry <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

echo "Welcome to RemoteOps Terminal"
echo "Commands: codex | remoteops nodes list | remoteops node info <id> | remoteops job create ... | remoteops job tail ..."
export PATH="/usr/local/bin:/usr/bin:/bin"
export PS1="(dashterm) \\u@\\h:\\w$ "
cd /home/dashterm
if command -v tmux >/dev/null 2>&1; then
  exec tmux new-session -A -s dashterm
fi
exec bash -l
EOF

sudo install -m 755 ./remoteops_cli.py /usr/local/bin/remoteops

if [[ ! -f "$TOKEN_FILE" ]]; then
  sudo sh -c "echo '<SET_REMOTEOPS_CLIENT_TOKEN>' > '$TOKEN_FILE'"
fi
sudo chmod 600 "$TOKEN_FILE"
sudo chown dashterm:dashterm "$TOKEN_FILE"

sudo install -m 644 /dev/stdin /etc/profile.d/remoteops.sh <<EOF
export REMOTEOPS_HUB_URL="$HUB_URL"
export REMOTEOPS_CLIENT_TOKEN_FILE="$TOKEN_FILE"
EOF

echo "Installed dashterm user, entry script, and remoteops CLI."
echo "If needed, set sshd Match config manually to force command /usr/local/bin/dashterm-entry for dashterm user."
