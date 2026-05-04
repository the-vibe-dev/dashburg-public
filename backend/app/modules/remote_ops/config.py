from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

from app.core.paths import remoteops_inventory_path


ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_INVENTORY = remoteops_inventory_path()
FALLBACK_INVENTORY = ROOT_DIR / "examples" / "servers.yaml"


def _normalize_server(raw: dict[str, Any]) -> dict[str, Any]:
    sid = str(raw.get("id", "")).strip()
    return {
        "id": sid,
        "name": str(raw.get("name", sid or "unknown")),
        "base_url": str(raw.get("base_url", "")).rstrip("/"),
        "key_id": str(raw.get("key_id", "")),
        "secret_env": str(raw.get("secret_env", "")),
        "secret": str(raw.get("secret", "")),
        "codex_enabled": bool(raw.get("codex_enabled", False)),
        "tags": [str(v) for v in raw.get("tags", [])],
        "repos": [str(v) for v in raw.get("repos", [])],
    }


def load_remote_inventory() -> dict[str, dict[str, Any]]:
    path = DEFAULT_INVENTORY if DEFAULT_INVENTORY.exists() else FALLBACK_INVENTORY
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8")
    if yaml is None:
        raise RuntimeError("PyYAML is required for remote ops inventory")

    parsed = yaml.safe_load(text) or {}
    rows = parsed.get("servers", []) if isinstance(parsed, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        norm = _normalize_server(row)
        if not norm["id"] or not norm["base_url"]:
            continue
        if norm["secret_env"]:
            norm["secret"] = os.getenv(norm["secret_env"], norm["secret"])
        out[norm["id"]] = norm
    return out
