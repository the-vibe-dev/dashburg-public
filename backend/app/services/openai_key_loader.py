from __future__ import annotations

import json
import os
from pathlib import Path

KEY_NAMES = ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")


def _ai_root() -> Path:
    configured = os.getenv("DASHBURG_AI_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    # /home/.../apps/dashgithub/backend/app/services -> /home/... then /ai
    return Path(__file__).resolve().parents[5] / "ai"


def _read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        row = line.strip()
        if not row or row.startswith("#") or "=" not in row:
            continue
        k, v = row.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _pick_key(data: dict) -> str | None:
    for key in KEY_NAMES:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def load_empire_openai_key() -> str:
    empire = _ai_root() / "empire"

    env_key = _pick_key(_read_env(empire / ".env"))
    if env_key:
        return env_key

    for fname in ("config.json", "settings.json"):
        key = _pick_key(_read_json(empire / fname))
        if key:
            return key

    fallback = os.getenv("DASHBURG_OPENAI_API_KEY", "").strip()
    if fallback:
        return fallback

    raise RuntimeError("No OpenAI key found in ai/empire or DASHBURG_OPENAI_API_KEY")
