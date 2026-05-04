from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

LOCK_TIMEOUT_SECONDS = float(os.getenv("DASHBURG_MEMORY_LOCK_TIMEOUT_SECONDS", "3.0") or "3.0")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def shared_root() -> Path:
    raw = str(os.getenv("DASHBURG_SHARED_MEMORY_ROOT", "")).strip()
    if not raw:
        return Path("/__dashburg_shared_memory_unset__")
    return Path(raw).expanduser()


def fallback_root() -> Path:
    return Path("~/.dashburg/local_memory").expanduser()


def _required_dirs(root: Path) -> list[Path]:
    return [
        root / "memory",
        root / "routing",
        root / "docs" / "investigations",
        root / "docs" / "profiles",
        root / "compacted",
        root / "logs",
    ]


def ensure_layout(root: Path) -> None:
    for path in _required_dirs(root):
        path.mkdir(parents=True, exist_ok=True)
    for file_path in [
        root / "memory" / "MEMORY_DELTAS.jsonl",
        root / "memory" / "MEMORY_CANDIDATES.jsonl",
        root / "memory" / "SESSION_INDEX.jsonl",
        root / "memory" / "DOC_RELATIONSHIPS.jsonl",
        root / "compacted" / "memory_compactions.jsonl",
        root / "logs" / "memory_ops.log",
    ]:
        if not file_path.exists():
            file_path.touch()


def shared_available() -> bool:
    root = shared_root()
    if not str(root).strip():
        return False
    try:
        ensure_layout(root)
    except Exception:
        return False
    return root.exists() and os.access(root, os.W_OK)


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint_record(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _lock_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".lock")


def _acquire_lock(lock_path: Path, timeout_s: float = LOCK_TIMEOUT_SECONDS) -> bool:
    deadline = time.time() + max(0.05, timeout_s)
    sleep_s = 0.05
    while time.time() < deadline:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
            os.close(fd)
            return True
        except FileExistsError:
            time.sleep(sleep_s)
            sleep_s = min(0.5, sleep_s * 2)
    return False


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def _write_tmp_line(path: Path, line: str) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("wb", delete=False, dir=str(path.parent), prefix=".tmp_mem_", suffix=".line") as tmp:
        data = line.encode("utf-8")
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    try:
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def append_jsonl_line(path: Path, payload: dict[str, Any]) -> None:
    line = canonical_json(payload) + "\n"
    blob = _write_tmp_line(path, line)
    lock_path = _lock_path(path)
    if not _acquire_lock(lock_path):
        raise TimeoutError(f"lock timeout for {path}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        _release_lock(lock_path)


def append_text_line(path: Path, text: str) -> None:
    line = text if text.endswith("\n") else (text + "\n")
    blob = _write_tmp_line(path, line)
    lock_path = _lock_path(path)
    if not _acquire_lock(lock_path):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        _release_lock(lock_path)


def iter_jsonl(path: Path, *, tail: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if tail is not None and tail > 0:
        lines = lines[-tail:]
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def append_with_fallback(rel_path: str, payload: dict[str, Any]) -> tuple[str, str]:
    rel = str(rel_path).strip().lstrip("/")
    if not rel:
        raise ValueError("rel_path required")

    target_root = shared_root()
    local_root = fallback_root()
    ensure_layout(local_root)
    local_replay = local_root / "replay_queue.jsonl"

    payload = dict(payload)
    payload.setdefault("ts", _now_iso())
    fp = fingerprint_record(payload)

    if shared_available():
        try:
            ensure_layout(target_root)
            append_jsonl_line(target_root / rel, payload)
            return "shared", fp
        except Exception:
            pass

    append_jsonl_line(local_root / rel, payload)
    append_jsonl_line(
        local_replay,
        {
            "queued_at": _now_iso(),
            "rel_path": rel,
            "fingerprint": fp,
            "payload": payload,
        },
    )
    return "fallback", fp


def replay_local_queue(limit: int = 500) -> int:
    if not shared_available():
        return 0
    local_root = fallback_root()
    ensure_layout(local_root)
    replay_path = local_root / "replay_queue.jsonl"
    rows = iter_jsonl(replay_path)
    if not rows:
        return 0

    target_root = shared_root()
    done = 0
    keep: list[dict[str, Any]] = []
    seen_fp: set[str] = set()

    for row in rows[: max(1, limit)]:
        rel = str(row.get("rel_path") or "").strip().lstrip("/")
        fp = str(row.get("fingerprint") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else None
        if not rel or not fp or not payload:
            continue
        if fp in seen_fp:
            done += 1
            continue
        target = target_root / rel
        existing = iter_jsonl(target, tail=5000)
        existing_fp = {fingerprint_record(item) for item in existing if isinstance(item, dict)}
        if fp in existing_fp:
            done += 1
            seen_fp.add(fp)
            continue
        try:
            append_jsonl_line(target, payload)
            done += 1
            seen_fp.add(fp)
        except Exception:
            keep.append(row)

    # Keep unprocessed rows + failed rows from processed window.
    remainder = rows[max(1, limit) :] if len(rows) > max(1, limit) else []
    keep.extend(remainder)
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    with replay_path.open("w", encoding="utf-8") as fh:
        for row in keep:
            fh.write(canonical_json(row) + "\n")
    return done
