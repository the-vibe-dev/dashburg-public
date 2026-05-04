#!/usr/bin/env bash
set -euo pipefail

SRC="${NEWMAIL_SOURCE_PATH:-/mnt/nas_ai/shared/NEWMAIL.md}"
DEST_HOME="${NEWMAIL_DEST_HOME:-$HOME/NEWMAIL.md}"

if [[ ! -f "$SRC" ]]; then
  echo "Source not available: $SRC" >&2
  exit 1
fi

install -d -m 755 "$(dirname "$DEST_HOME")"
cp "$SRC" "$DEST_HOME"

if [[ -d "$HOME/apps/dashgithub" ]]; then
  cp "$SRC" "$HOME/apps/dashgithub/NEWMAIL.md"
fi

echo "Synced NEWMAIL from $SRC"
