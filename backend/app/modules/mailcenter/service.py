from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from hashlib import sha1
from typing import Any

from sqlmodel import Session, select

from app.models.remoteops import RemoteOpsNode
from app.modules.orchestration.service import create_mailbox_note, list_mailbox_items


def _parse_dt(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.min.replace(tzinfo=UTC)
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return datetime.min.replace(tzinfo=UTC)


def _thread_id(item: dict[str, Any]) -> str:
    seed = f"{item.get('job_id','')}|{item.get('subject','')}|{item.get('node_id','')}|{item.get('to','')}|{item.get('from','')}"
    return sha1(seed.encode("utf-8")).hexdigest()[:16]


def _folder(direction: str, archived: bool, failed: bool) -> str:
    if archived:
        return "archived"
    if failed:
        return "failed"
    if direction == "outbound":
        return "sent"
    return "inbox"


def _processing_state(status: str) -> str:
    value = status.strip().lower()
    if value in {"queued", "accepted", "waiting_dependency"}:
        return "queued"
    if value in {"running", "preparing", "dispatched"}:
        return "running"
    if value in {"failed", "error", "timed_out"}:
        return "failed"
    return "completed"


def _coerce_message(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status") or "received").strip().lower()
    severity = str(item.get("severity") or "").strip().lower()
    direction = "inbound" if str(item.get("direction") or "inbox").strip().lower() == "inbox" else "outbound"
    failed = status in {"failed", "error", "timed_out"} or severity in {"error", "critical"}
    archived = bool(item.get("archived"))
    thread_id = _thread_id(item)
    subject = str(item.get("subject") or "Mailbox note").strip() or "Mailbox note"
    body = str(item.get("body") or "").strip()
    snippet = body[:220]
    created_at = str(item.get("created_at") or "")
    updated_at = str(item.get("updated_at") or created_at)
    node_id = str(item.get("node_id") or "").strip()
    recipient = str(item.get("to") or f"node:{node_id}/runner").strip()
    recipient_kind = "agent" if "/agent:" in recipient else "runner"
    recipient_agent_slug = recipient.split("/agent:", 1)[1] if "/agent:" in recipient else ""
    return {
        "id": str(item.get("id") or ""),
        "thread_id": thread_id,
        "subject": subject,
        "snippet": snippet,
        "body": body,
        "from": str(item.get("from") or "dashgithub-operator").strip(),
        "to": recipient,
        "cc": [],
        "bcc": [],
        "direction": direction,
        "status": status or "received",
        "folder": _folder(direction, archived, failed),
        "created_at": created_at,
        "sent_at": created_at if direction == "outbound" else "",
        "received_at": created_at if direction == "inbound" else "",
        "updated_at": updated_at,
        "tags": [str(tag).strip() for tag in (item.get("tags") or []) if str(tag).strip()],
        "unread": direction == "inbound" and not bool(item.get("acknowledged")),
        "has_attachments": bool(item.get("attachments")),
        "attachments": [row for row in (item.get("attachments") or []) if isinstance(row, dict)],
        "processing_state": _processing_state(status),
        "classification": str(item.get("type") or "note"),
        "automation_rule": "",
        "reply_draft_state": "",
        "failure_reason": str(item.get("last_error") or item.get("error") or ""),
        "retry_info": {},
        "linked_entity": {"job_id": str(item.get("job_id") or "")},
        "account": node_id or "orchestration",
        "mailbox": "archive" if archived else ("sent" if direction == "outbound" else "inbox"),
        "source": "orchestration_mailbox",
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        "recipient_node_id": node_id,
        "recipient_kind": recipient_kind,
        "recipient_agent_slug": recipient_agent_slug,
    }


def _load_messages(session: Session, limit: int = 250) -> list[dict[str, Any]]:
    items = list_mailbox_items(session, direction=None, include_archived=True, limit=max(limit, 200))
    rows = [_coerce_message(item) for item in items]
    rows.sort(key=lambda row: _parse_dt(row.get("updated_at") or row.get("created_at")), reverse=True)
    return rows[:limit]


def list_messages(
    session: Session,
    *,
    folder: str | None = None,
    status: str | None = None,
    direction: str | None = None,
    account: str | None = None,
    tag: str | None = None,
    recipient_node_id: str | None = None,
    recipient_agent_slug: str | None = None,
    unread_only: bool = False,
    query: str | None = None,
    limit: int = 120,
) -> list[dict[str, Any]]:
    rows = _load_messages(session, limit=max(limit * 3, 200))
    out: list[dict[str, Any]] = []
    q = str(query or "").strip().lower()
    for row in rows:
        if folder and folder != "all" and row["folder"] != folder:
            continue
        if status and row["status"] != status:
            continue
        if direction and row["direction"] != direction:
            continue
        if account and row["account"] != account:
            continue
        if tag and tag not in row["tags"]:
            continue
        if recipient_node_id and row.get("recipient_node_id") != recipient_node_id:
            continue
        if recipient_agent_slug and row.get("recipient_agent_slug") != recipient_agent_slug:
            continue
        if unread_only and not row["unread"]:
            continue
        if q:
            hay = " ".join([row["subject"], row["snippet"], row["body"], row["from"], row["to"], " ".join(row["tags"])]).lower()
            if q not in hay:
                continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def list_threads(session: Session, *, folder: str | None = None, query: str | None = None, limit: int = 120) -> list[dict[str, Any]]:
    rows = list_messages(session, folder=folder, query=query, limit=max(limit * 4, 200))
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[row["thread_id"]].append(row)
    threads: list[dict[str, Any]] = []
    for thread_id, items in buckets.items():
        items.sort(key=lambda row: _parse_dt(row["created_at"]))
        latest = max(items, key=lambda row: _parse_dt(row["updated_at"] or row["created_at"]))
        statuses = Counter(str(row["status"]) for row in items)
        directions = Counter(str(row["direction"]) for row in items)
        participants = sorted({str(row["from"]) for row in items} | {str(row["to"]) for row in items})
        threads.append(
            {
                "thread_id": thread_id,
                "subject": latest["subject"],
                "snippet": latest["snippet"],
                "latest_message_id": latest["id"],
                "latest_at": latest["updated_at"],
                "message_count": len(items),
                "unread_count": sum(1 for row in items if row["unread"]),
                "has_failed": any(row["status"] in {"failed", "error", "timed_out"} for row in items),
                "participants": participants,
                "status_counts": dict(statuses),
                "direction_mix": dict(directions),
                "account": latest["account"],
                "tags": sorted({tag for row in items for tag in row["tags"]}),
                "folder": latest["folder"],
            }
        )
    threads.sort(key=lambda row: _parse_dt(row["latest_at"]), reverse=True)
    return threads[:limit]


def get_message_detail(session: Session, message_id: str) -> dict[str, Any] | None:
    rows = _load_messages(session, limit=500)
    selected = next((row for row in rows if row["id"] == message_id), None)
    if not selected:
        return None
    thread_items = [row for row in rows if row["thread_id"] == selected["thread_id"]]
    thread_items.sort(key=lambda row: _parse_dt(row["created_at"]))
    return {
        "message": selected,
        "thread": {
            "thread_id": selected["thread_id"],
            "subject": selected["subject"],
            "message_count": len(thread_items),
            "messages": thread_items,
            "activity": [
                {
                    "at": row["created_at"],
                    "event": row["status"],
                    "summary": row["subject"],
                    "direction": row["direction"],
                    "id": row["id"],
                }
                for row in thread_items
            ],
        },
    }


def get_overview(session: Session) -> dict[str, Any]:
    rows = _load_messages(session, limit=400)
    counts = Counter(row["folder"] for row in rows)
    statuses = Counter(row["status"] for row in rows)
    processing = Counter(row["processing_state"] for row in rows)
    directions = Counter(row["direction"] for row in rows)
    accounts = Counter(row["account"] for row in rows)
    latest = max((_parse_dt(row["updated_at"] or row["created_at"]) for row in rows), default=None)
    folders = [
        {"key": key, "label": label, "count": counts.get(key, 0)}
        for key, label in [("all", "All"), ("inbox", "Inbox"), ("sent", "Sent"), ("queued", "Queued"), ("failed", "Failed"), ("archived", "Archived")]
    ]
    return {
        "counts": {
            "inbox": counts.get("inbox", 0),
            "sent": counts.get("sent", 0),
            "queued": processing.get("queued", 0),
            "failed": counts.get("failed", 0),
            "replies_needed": sum(1 for row in rows if row["direction"] == "inbound" and row["unread"]),
        },
        "statuses": dict(statuses),
        "processing": dict(processing),
        "directions": dict(directions),
        "accounts": [{"account": account, "count": count} for account, count in accounts.most_common()],
        "subsystem": {
            "status": "ok",
            "last_activity_at": latest.isoformat().replace("+00:00", "Z") if latest and latest != datetime.min.replace(tzinfo=UTC) else None,
            "sources": ["orchestration_mailbox"],
            "threads": len({row["thread_id"] for row in rows}),
        },
        "folders": folders,
    }


def build_recipients(session: Session, *, skilled_agents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = session.exec(select(RemoteOpsNode).where(RemoteOpsNode.enabled == True).order_by(RemoteOpsNode.label.asc())).all()  # noqa: E712
    return {
        "nodes": [
            {
                "node_id": row.id,
                "label": row.label,
                "address": f"node:{row.id}/runner",
                "kind": "runner",
            }
            for row in rows
        ],
        "agents": [],
    }


def send_message(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    recipient = str(payload.get("to") or "").strip()
    if not recipient.startswith("node:"):
        raise ValueError("recipient must be a node runner address")
    node_id = recipient.split(":", 1)[1].split("/", 1)[0].strip()
    if not node_id:
        raise ValueError("recipient node_id missing")
    body = {
        "to": recipient,
        "subject": str(payload.get("subject") or "Message from MailCenter").strip(),
        "body": str(payload.get("body") or "").strip(),
        "type": str(payload.get("type") or "note").strip() or "note",
        "severity": str(payload.get("severity") or "info").strip() or "info",
        "job_id": str(payload.get("job_id") or "").strip(),
        "tags": [str(tag).strip() for tag in (payload.get("tags") or []) if str(tag).strip()],
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }
    created = create_mailbox_note(session, node_id, body)
    return _coerce_message(created)
