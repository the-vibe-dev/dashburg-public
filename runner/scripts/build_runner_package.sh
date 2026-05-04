#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="runner-deploy-with-codex-${STAMP}.zip"

python3 - <<'PY'
from pathlib import Path
import time
import zipfile

root = Path.cwd()
stamp = time.strftime("%Y%m%d-%H%M%S")
out = root / f"runner-deploy-with-codex-{stamp}.zip"

files: list[Path] = []
for path in sorted((root / "runner").rglob("*")):
    if not path.is_file():
        continue
    rel = path.relative_to(root)
    s = str(rel)
    if s.startswith("runner/.venv/"):
        continue
    if "/__pycache__/" in s:
        continue
    if s.startswith("runner/.deploy/"):
        continue
    if s == "runner/config.yaml":
        continue
    files.append(rel)

with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for rel in files:
        zf.write(root / rel, arcname=str(rel))

print(out)
PY

LATEST="$(ls -1t runner-deploy-with-codex-*.zip | head -n1)"
echo "Built: $ROOT_DIR/$LATEST"
echo "Contents:"
unzip -l "$LATEST" | sed -n '1,220p'
