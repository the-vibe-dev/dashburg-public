from __future__ import annotations

import threading
import time
from pathlib import Path

from app.modules.memory import storage


def test_distributed_append_writes_jsonl_lines(tmp_path: Path) -> None:
    path = tmp_path / "shared" / "memory" / "MEMORY_DELTAS.jsonl"

    def worker(prefix: str) -> None:
        for idx in range(30):
            storage.append_jsonl_line(path, {"worker": prefix, "idx": idx})

    t1 = threading.Thread(target=worker, args=("a",), daemon=True)
    t2 = threading.Thread(target=worker, args=("b",), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    rows = storage.iter_jsonl(path)
    assert len(rows) == 60


def test_lock_retry_waits_then_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "shared" / "memory" / "MEMORY_DELTAS.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    lock.write_text("locked", encoding="utf-8")

    def release_later() -> None:
        time.sleep(0.2)
        lock.unlink(missing_ok=True)

    rel = threading.Thread(target=release_later, daemon=True)
    rel.start()
    storage.append_jsonl_line(path, {"ok": True})
    rel.join(timeout=2)

    rows = storage.iter_jsonl(path)
    assert rows[-1]["ok"] is True


def test_lock_timeout_spools_to_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DASHBURG_SHARED_MEMORY_ROOT", str(tmp_path / "shared"))

    # Force lock acquisition failure to trigger fallback spool path.
    monkeypatch.setattr(storage, "_acquire_lock", lambda _path, timeout_s=3.0: False)

    dest, _fp = storage.append_with_fallback("memory/MEMORY_DELTAS.jsonl", {"kind": "test"})
    assert dest == "fallback"

    local_rows = storage.iter_jsonl(storage.fallback_root() / "memory" / "MEMORY_DELTAS.jsonl")
    replay_rows = storage.iter_jsonl(storage.fallback_root() / "replay_queue.jsonl")
    assert local_rows
    assert replay_rows


def test_replay_queue_dedupes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("DASHBURG_SHARED_MEMORY_ROOT", raising=False)

    _dest, fp = storage.append_with_fallback("memory/SESSION_INDEX.jsonl", {"session_id": "s1", "summary": "x"})
    assert fp

    shared = tmp_path / "shared"
    monkeypatch.setenv("DASHBURG_SHARED_MEMORY_ROOT", str(shared))
    shared.mkdir(parents=True, exist_ok=True)

    replayed = storage.replay_local_queue(limit=50)
    assert replayed >= 1

    rows = storage.iter_jsonl(shared / "memory" / "SESSION_INDEX.jsonl")
    assert any(str(row.get("session_id")) == "s1" for row in rows)
