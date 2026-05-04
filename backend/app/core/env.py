from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(start_dir: Path | None = None) -> Path | None:
    current = (start_dir or Path(__file__).resolve()).parent
    for candidate_dir in [current, *current.parents]:
        candidate = candidate_dir / ".env"
        if candidate.exists():
            _read_dotenv(candidate)
            return candidate
    return None


def _read_dotenv(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
