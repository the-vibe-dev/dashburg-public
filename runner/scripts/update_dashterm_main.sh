#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f ./remoteops_cli.py ]]; then
  echo "Run from runner/ directory."
  exit 1
fi

sudo install -m 755 ./remoteops_cli.py /usr/local/bin/remoteops
sudo install -m 755 ./scripts/install_dashterm_main.sh /usr/local/bin/install_dashterm_main.sh

echo "Updated remoteops helper binaries on main server."
