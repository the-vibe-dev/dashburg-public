from __future__ import annotations

import sqlite3
import threading
import json
from pathlib import Path
from typing import Any


class JobStore:
    def __init__(self, data_dir: str):
        root = Path(data_dir)
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.db_path = root / "runner_jobs.sqlite3"
        self.mailbox_root = root / "mailbox"
        self.mailbox_attachments_root = self.mailbox_root / "attachments"
        for subdir in ("inbox", "outbox", "archive"):
            (self.mailbox_root / subdir).mkdir(parents=True, exist_ok=True)
        self.mailbox_attachments_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY,
                  type TEXT NOT NULL,
                  status TEXT NOT NULL,
                  params_json TEXT NOT NULL,
                  result_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  started_at TEXT,
                  updated_at TEXT NOT NULL,
                  finished_at TEXT,
                  cancel_requested_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_logs (
                  job_id TEXT NOT NULL,
                  offset INTEGER PRIMARY KEY AUTOINCREMENT,
                  line TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
            cols = [row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
            if "started_at" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN started_at TEXT")
            if "cancel_requested_at" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN cancel_requested_at TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mailbox_items (
                  id TEXT PRIMARY KEY,
                  node_id TEXT NOT NULL,
                  direction TEXT NOT NULL,
                  msg_type TEXT NOT NULL,
                  subject TEXT NOT NULL,
                  body TEXT NOT NULL,
                  job_id TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  severity TEXT NOT NULL,
                  status TEXT NOT NULL,
                  sender TEXT NOT NULL,
                  recipient TEXT NOT NULL,
                  attachments_json TEXT NOT NULL,
                  tags_json TEXT NOT NULL,
                  metadata_json TEXT NOT NULL,
                  acknowledged INTEGER NOT NULL DEFAULT 0,
                  acknowledged_at TEXT,
                  archived INTEGER NOT NULL DEFAULT 0,
                  archived_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )

    def _mailbox_dir(self, direction: str, archived: bool) -> Path:
        if archived:
            return self.mailbox_root / "archive"
        if direction == "inbox":
            return self.mailbox_root / "inbox"
        return self.mailbox_root / "outbox"

    def _serialize_mailbox_row(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        raw = dict(row)
        return {
            "id": str(raw.get("id") or ""),
            "node_id": str(raw.get("node_id") or ""),
            "direction": str(raw.get("direction") or ""),
            "type": str(raw.get("msg_type") or ""),
            "subject": str(raw.get("subject") or ""),
            "body": str(raw.get("body") or ""),
            "job_id": str(raw.get("job_id") or ""),
            "run_id": str(raw.get("run_id") or ""),
            "severity": str(raw.get("severity") or "info"),
            "status": str(raw.get("status") or "new"),
            "created_at": str(raw.get("created_at") or ""),
            "updated_at": str(raw.get("updated_at") or raw.get("created_at") or ""),
            "from": str(raw.get("sender") or ""),
            "to": str(raw.get("recipient") or ""),
            "attachments": json.loads(raw.get("attachments_json") or "[]"),
            "tags": json.loads(raw.get("tags_json") or "[]"),
            "acknowledged": bool(raw.get("acknowledged")),
            "acknowledged_at": raw.get("acknowledged_at"),
            "archived": bool(raw.get("archived")),
            "archived_at": raw.get("archived_at"),
            "metadata": json.loads(raw.get("metadata_json") or "{}"),
        }

    def _write_mailbox_snapshot(self, item: dict[str, Any]) -> None:
        current_dir = self._mailbox_dir(str(item.get("direction") or "outbox"), bool(item.get("archived")))
        target = current_dir / f"{item['id']}.json"
        # Remove stale copies if ack/archive moved the item.
        for subdir in ("inbox", "outbox", "archive"):
            candidate = self.mailbox_root / subdir / f"{item['id']}.json"
            if candidate != target and candidate.exists():
                candidate.unlink()
        target.write_text(json.dumps(item, indent=2), encoding="utf-8")

    def create_job(self, job_id: str, job_type: str, params_json: str, now_iso: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO jobs(id, type, status, params_json, result_json, created_at, started_at, updated_at, finished_at, cancel_requested_at) VALUES(?,?,?,?,?,?,?,?,?,NULL)",
                (job_id, job_type, "queued", params_json, "{}", now_iso, None, now_iso, None),
            )

    def update_job(self, job_id: str, *, status: str, result_json: str | None, now_iso: str, finished: bool = False, started: bool = False) -> None:
        with self._lock, self._conn() as conn:
            if result_json is None:
                if started:
                    conn.execute(
                        "UPDATE jobs SET status=?, started_at=COALESCE(started_at, ?), updated_at=?, finished_at=? WHERE id=?",
                        (status, now_iso, now_iso, now_iso if finished else None, job_id),
                    )
                else:
                    conn.execute(
                        "UPDATE jobs SET status=?, updated_at=?, finished_at=? WHERE id=?",
                        (status, now_iso, now_iso if finished else None, job_id),
                    )
            else:
                if started:
                    conn.execute(
                        "UPDATE jobs SET status=?, result_json=?, started_at=COALESCE(started_at, ?), updated_at=?, finished_at=? WHERE id=?",
                        (status, result_json, now_iso, now_iso, now_iso if finished else None, job_id),
                    )
                else:
                    conn.execute(
                        "UPDATE jobs SET status=?, result_json=?, updated_at=?, finished_at=? WHERE id=?",
                        (status, result_json, now_iso, now_iso if finished else None, job_id),
                    )

    def request_cancel(self, job_id: str, now_iso: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            status = str(row["status"])
            if status == "queued":
                conn.execute(
                    "UPDATE jobs SET status='canceled', cancel_requested_at=?, updated_at=?, finished_at=? WHERE id=?",
                    (now_iso, now_iso, now_iso, job_id),
                )
            else:
                conn.execute(
                    "UPDATE jobs SET cancel_requested_at=?, updated_at=? WHERE id=?",
                    (now_iso, now_iso, job_id),
                )
        return self.get_job(job_id)

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT cancel_requested_at FROM jobs WHERE id=?", (job_id,)).fetchone()
        return bool(row and row["cancel_requested_at"])

    def append_log(self, job_id: str, line: str, now_iso: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("INSERT INTO job_logs(job_id, line, created_at) VALUES(?,?,?)", (job_id, line, now_iso))

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def get_logs(self, job_id: str, offset: int, max_lines: int) -> dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT offset, line FROM job_logs WHERE job_id=? AND offset>? ORDER BY offset ASC LIMIT ?",
                (job_id, offset, max_lines),
            ).fetchall()
        lines = [str(r["line"]) for r in rows]
        new_offset = int(rows[-1]["offset"]) if rows else offset
        return {"offset": new_offset, "lines": lines}

    def list_recent_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def create_mailbox_item(
        self,
        *,
        item_id: str,
        node_id: str,
        direction: str,
        msg_type: str,
        subject: str,
        body: str,
        job_id: str,
        run_id: str,
        severity: str,
        status: str,
        sender: str,
        recipient: str,
        attachments: list[dict[str, Any]] | None,
        tags: list[str] | None,
        metadata: dict[str, Any] | None,
        now_iso: str,
    ) -> dict[str, Any]:
        payload = {
            "item_id": item_id,
            "node_id": node_id,
            "direction": direction,
            "msg_type": msg_type,
            "subject": subject,
            "body": body,
            "job_id": job_id,
            "run_id": run_id,
            "severity": severity,
            "status": status,
            "sender": sender,
            "recipient": recipient,
            "attachments_json": json.dumps(attachments or []),
            "tags_json": json.dumps(tags or []),
            "metadata_json": json.dumps(metadata or {}),
            "now_iso": now_iso,
        }
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO mailbox_items(
                  id, node_id, direction, msg_type, subject, body, job_id, run_id, severity, status,
                  sender, recipient, attachments_json, tags_json, metadata_json,
                  acknowledged, acknowledged_at, archived, archived_at, created_at, updated_at
                ) VALUES(
                  :item_id, :node_id, :direction, :msg_type, :subject, :body, :job_id, :run_id, :severity, :status,
                  :sender, :recipient, :attachments_json, :tags_json, :metadata_json,
                  0, NULL, 0, NULL, :now_iso, :now_iso
                )
                """,
                payload,
            )
            row = conn.execute("SELECT * FROM mailbox_items WHERE id=?", (item_id,)).fetchone()
        assert row is not None
        item = self._serialize_mailbox_row(row)
        self._write_mailbox_snapshot(item)
        return item

    def get_mailbox_item(self, item_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM mailbox_items WHERE id=?", (item_id,)).fetchone()
        return self._serialize_mailbox_row(row) if row else None

    def list_mailbox_items(
        self,
        *,
        direction: str | None = None,
        include_archived: bool = False,
        job_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if direction:
            where.append("direction=?")
            params.append(direction)
        if not include_archived:
            where.append("archived=0")
        if job_id:
            where.append("job_id=?")
            params.append(job_id)
        query = "SELECT * FROM mailbox_items"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._serialize_mailbox_row(row) for row in rows]

    def acknowledge_mailbox_item(self, item_id: str, now_iso: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE mailbox_items SET acknowledged=1, acknowledged_at=COALESCE(acknowledged_at, ?), status='acknowledged', updated_at=? WHERE id=?",
                (now_iso, now_iso, item_id),
            )
            row = conn.execute("SELECT * FROM mailbox_items WHERE id=?", (item_id,)).fetchone()
        if not row:
            return None
        item = self._serialize_mailbox_row(row)
        self._write_mailbox_snapshot(item)
        return item

    def archive_mailbox_item(self, item_id: str, now_iso: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE mailbox_items SET archived=1, archived_at=COALESCE(archived_at, ?), status='archived', updated_at=? WHERE id=?",
                (now_iso, now_iso, item_id),
            )
            row = conn.execute("SELECT * FROM mailbox_items WHERE id=?", (item_id,)).fetchone()
        if not row:
            return None
        item = self._serialize_mailbox_row(row)
        self._write_mailbox_snapshot(item)
        return item
