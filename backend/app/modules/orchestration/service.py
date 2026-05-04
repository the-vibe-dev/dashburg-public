from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models.orchestration import OrchestrationJob, OrchestrationSettings
from app.models.remoteops import RemoteOpsNode, RemoteOpsSettings
from app.modules.remote_ops.runner_client import RunnerClientError
from app.services.knowledge import maybe_add_mail_record, search_mail_knowledge
from app.modules.remote_ops.service import (
    _jloads_dict,
    _jloads_list,
    _jdumps,
    _runner_client_for_node,
    get_node,
    get_nodes_health_status,
)
try:
    from knowledge_layer.records import MAIL_RECORD_TYPES
except ModuleNotFoundError:
    MAIL_RECORD_TYPES = {"note", "task", "result", "alert", "summary"}

TERMINAL_STATUSES = {"succeeded", "failed", "canceled", "timed_out"}
ACTIVE_STATUSES = {"dispatched", "accepted", "preparing", "running"}
WAITING_STATUSES = {"queued", "waiting_dependency"}
TERMINAL_FAILURE_STATUSES = {"failed", "canceled", "timed_out"}
MAIL_RECIPIENT_RE = re.compile(r"^node:(?P<node_id>[a-zA-Z0-9._-]+)/(?P<target>runner|agent:[a-zA-Z0-9._-]+)$")


def _utcnow() -> datetime:
    return datetime.utcnow()


def _parse_mail_recipient(value: str) -> dict[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return {"raw": "", "node_id": "", "kind": "", "agent_slug": ""}
    match = MAIL_RECIPIENT_RE.match(raw)
    if not match:
        return {"raw": raw, "node_id": "", "kind": "", "agent_slug": ""}
    target = str(match.group("target") or "").strip().lower()
    if target == "runner":
        return {"raw": raw, "node_id": str(match.group("node_id") or ""), "kind": "runner", "agent_slug": ""}
    return {
        "raw": raw,
        "node_id": str(match.group("node_id") or ""),
        "kind": "agent",
        "agent_slug": target.split(":", 1)[1] if ":" in target else "",
    }


def ensure_settings(session: Session) -> OrchestrationSettings:
    row = session.get(OrchestrationSettings, 1)
    if row:
        preferred_terminal_node_id = str(row.preferred_terminal_node_id or "").strip()
        if not preferred_terminal_node_id or preferred_terminal_node_id == "codex-main":
            row.preferred_terminal_node_id = "devwork"
            row.updated_at = _utcnow()
            session.add(row)
            session.commit()
            session.refresh(row)
        return row
    row = OrchestrationSettings(id=1)
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        row = session.get(OrchestrationSettings, 1)
        if row:
            return row
        raise
    session.refresh(row)
    return row


def settings_to_dict(row: OrchestrationSettings) -> dict[str, Any]:
    return {
        "preferred_terminal_node_id": row.preferred_terminal_node_id,
        "preferred_execution_mode": row.preferred_execution_mode,
        "default_codex_mode": row.default_codex_mode,
        "default_timeout_seconds": row.default_timeout_seconds,
        "global_max_active_jobs": row.global_max_active_jobs,
        "default_max_retries": row.default_max_retries,
        "scheduler_poll_seconds": row.scheduler_poll_seconds,
    }


def update_settings(session: Session, payload: dict[str, Any]) -> OrchestrationSettings:
    row = ensure_settings(session)
    row.preferred_terminal_node_id = str(payload.get("preferred_terminal_node_id", row.preferred_terminal_node_id)).strip() or row.preferred_terminal_node_id
    row.preferred_execution_mode = str(payload.get("preferred_execution_mode", row.preferred_execution_mode)).strip() or row.preferred_execution_mode
    row.default_codex_mode = str(payload.get("default_codex_mode", row.default_codex_mode)).strip() or row.default_codex_mode
    row.default_timeout_seconds = int(payload.get("default_timeout_seconds", row.default_timeout_seconds))
    row.global_max_active_jobs = int(payload.get("global_max_active_jobs", row.global_max_active_jobs))
    row.default_max_retries = int(payload.get("default_max_retries", row.default_max_retries))
    row.scheduler_poll_seconds = int(payload.get("scheduler_poll_seconds", row.scheduler_poll_seconds))
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def orchestration_job_to_payload(row: OrchestrationJob) -> dict[str, Any]:
    metadata = _jloads_dict(row.metadata_json)
    dependency_state = metadata.get("dependency_state")
    if not isinstance(dependency_state, list):
        dependency_state = []
    return {
        "id": row.id,
        "title": row.title,
        "task_type": row.task_type,
        "target_node": row.target_node,
        "repo_path": row.repo_path,
        "workspace_path": row.workspace_path,
        "prompt": row.prompt,
        "instructions": row.instructions,
        "execution_mode": row.execution_mode,
        "codex_mode": row.codex_mode,
        "priority": row.priority,
        "timeout_seconds": row.timeout_seconds,
        "dependencies": _jloads_list(row.dependencies_json),
        "status": row.status,
        "runner_job_id": row.runner_job_id,
        "retry_count": row.retry_count,
        "max_retries": row.max_retries,
        "assigned_runner": row.assigned_runner,
        "logs_url": row.logs_url,
        "result_summary": row.result_summary,
        "changed_files": _jloads_list(row.changed_files_json),
        "artifacts": _jloads_dict(row.artifacts_json, fallback={"items": []}).get("items", []),
        "metadata": _jloads_dict(row.metadata_json),
        "dependency_state": dependency_state,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "updated_at": row.updated_at,
    }


def _mailbox_item_to_payload(node_id: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "node_id": node_id,
        "direction": str(item.get("direction") or ""),
        "type": str(item.get("type") or ""),
        "subject": str(item.get("subject") or ""),
        "body": str(item.get("body") or ""),
        "job_id": str(item.get("job_id") or ""),
        "run_id": str(item.get("run_id") or ""),
        "severity": str(item.get("severity") or "info"),
        "status": str(item.get("status") or "new"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "from": str(item.get("from") or ""),
        "to": str(item.get("to") or ""),
        "attachments": item.get("attachments") if isinstance(item.get("attachments"), list) else [],
        "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
        "acknowledged": bool(item.get("acknowledged")),
        "acknowledged_at": item.get("acknowledged_at"),
        "archived": bool(item.get("archived")),
        "archived_at": item.get("archived_at"),
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    }


def list_jobs(session: Session) -> list[OrchestrationJob]:
    stmt = select(OrchestrationJob).order_by(OrchestrationJob.created_at.desc())
    return list(session.exec(stmt).all())


def get_job(session: Session, job_id: str) -> OrchestrationJob | None:
    return session.get(OrchestrationJob, job_id)


def _dependency_state(session: Session, deps: list[str]) -> tuple[bool, bool]:
    if not deps:
        return True, False
    rows = [session.get(OrchestrationJob, dep_id) for dep_id in deps]
    if any(row is None for row in rows):
        return False, True
    if any(row.status in {"failed", "canceled", "timed_out"} for row in rows if row):
        return False, True
    if all(row.status == "succeeded" for row in rows if row):
        return True, False
    return False, False


def _dependency_state_rows(session: Session, deps: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dep_id in deps:
        dep = session.get(OrchestrationJob, dep_id)
        rows.append(
            {
                "job_id": dep_id,
                "status": dep.status if dep else "missing",
                "title": dep.title if dep else "",
            }
        )
    return rows


def create_job(session: Session, payload: dict[str, Any]) -> OrchestrationJob:
    settings = ensure_settings(session)
    row = OrchestrationJob(
        id=uuid.uuid4().hex,
        title=str(payload.get("title", "")).strip(),
        task_type=str(payload.get("task_type", "codex_task")).strip() or "codex_task",
        target_node=str(payload.get("target_node", "")).strip(),
        repo_path=str(payload.get("repo_path", "")).strip(),
        workspace_path=str(payload.get("workspace_path", "")).strip(),
        prompt=str(payload.get("prompt", "")).strip(),
        instructions=str(payload.get("instructions", "")).strip(),
        execution_mode=str(payload.get("execution_mode", settings.preferred_execution_mode)).strip() or settings.preferred_execution_mode,
        codex_mode=str(payload.get("codex_mode", settings.default_codex_mode)).strip() or settings.default_codex_mode,
        priority=int(payload.get("priority", 100)),
        timeout_seconds=int(payload.get("timeout_seconds", settings.default_timeout_seconds)),
        dependencies_json=_jdumps(payload.get("dependencies", [])),
        status="queued",
        max_retries=int(payload.get("max_retries", settings.default_max_retries)),
        metadata_json=_jdumps(payload.get("metadata", {})),
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def create_jobs(session: Session, payloads: list[dict[str, Any]]) -> list[OrchestrationJob]:
    rows = [create_job(session, payload) for payload in payloads]
    reconcile_jobs(session)
    return rows


def _runner_status_to_orchestration(status: str) -> str:
    value = status.strip().lower()
    mapping = {
        "queued": "accepted",
        "dispatched": "dispatched",
        "accepted": "accepted",
        "preparing": "preparing",
        "running": "running",
        "completed": "succeeded",
        "succeeded": "succeeded",
        "failed": "failed",
        "cancelled": "canceled",
        "canceled": "canceled",
        "timed_out": "timed_out",
        "timeout": "timed_out",
    }
    return mapping.get(value, value or "queued")


def _active_jobs_by_node(rows: list[OrchestrationJob]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        if row.status in ACTIVE_STATUSES:
            out[row.target_node] = out.get(row.target_node, 0) + 1
    return out


def _workspace_locked(rows: list[OrchestrationJob], current: OrchestrationJob) -> bool:
    key = current.workspace_path or current.repo_path
    if not key:
        return False
    for row in rows:
        if row.id == current.id or row.target_node != current.target_node or row.status not in ACTIVE_STATUSES:
            continue
        if (row.workspace_path or row.repo_path) == key:
            return True
    return False


def _sync_running_job(session: Session, row: OrchestrationJob) -> None:
    node = get_node(session, row.target_node)
    if not node or not row.runner_job_id:
        return
    try:
        detail = _runner_client_for_node(node).get_job(row.runner_job_id)
    except RunnerClientError as exc:
        row.last_error = str(exc.detail)
        row.updated_at = _utcnow()
        session.add(row)
        session.commit()
        return
    runner_status = str(detail.get("status", row.status))
    row.status = _runner_status_to_orchestration(runner_status)
    result = detail.get("result") if isinstance(detail.get("result"), dict) else detail
    metadata = _jloads_dict(row.metadata_json)
    metadata["runner_detail"] = detail if isinstance(detail, dict) else {}
    row.metadata_json = _jdumps(metadata)
    row.result_summary = str(result.get("summary") or result.get("next_steps") or result.get("diffstat") or row.result_summary)[:2000]
    changed_files = result.get("changed_files")
    if isinstance(changed_files, list):
        row.changed_files_json = _jdumps([str(item) for item in changed_files])
    if row.status in TERMINAL_STATUSES and row.finished_at is None:
        row.finished_at = _utcnow()
    if row.status in {"preparing", "running"} and row.started_at is None:
        row.started_at = _utcnow()
    row.updated_at = _utcnow()
    try:
        artifacts = _runner_client_for_node(node).get_artifacts(row.runner_job_id)
        row.artifacts_json = _jdumps(artifacts if isinstance(artifacts, dict) else {"items": []})
    except Exception:
        pass
    session.add(row)
    session.commit()


def reconcile_jobs(session: Session) -> list[OrchestrationJob]:
    settings = ensure_settings(session)
    rows = list_jobs(session)
    active_global = 0
    active_rows: list[OrchestrationJob] = []
    for row in rows:
        if row.status in ACTIVE_STATUSES:
            _sync_running_job(session, row)
    rows = list_jobs(session)
    active_by_node = _active_jobs_by_node(rows)
    active_global = sum(active_by_node.values())
    for row in sorted(rows, key=lambda item: (item.priority, item.created_at)):
        if row.status in TERMINAL_STATUSES:
            continue
        deps = _jloads_list(row.dependencies_json)
        ready, blocked = _dependency_state(session, deps)
        metadata = _jloads_dict(row.metadata_json)
        metadata["dependency_state"] = _dependency_state_rows(session, deps)
        row.metadata_json = _jdumps(metadata)
        if blocked and row.status not in TERMINAL_STATUSES:
            row.status = "failed"
            row.last_error = "dependency_failed_or_missing"
            row.finished_at = row.finished_at or _utcnow()
            row.updated_at = _utcnow()
            session.add(row)
            continue
        if not ready:
            row.status = "waiting_dependency"
            row.updated_at = _utcnow()
            session.add(row)
            continue
        if row.execution_mode != "delegated_runner":
            if row.status not in TERMINAL_STATUSES:
                row.status = "queued"
                row.last_error = "direct_ssh is preserved for LocalOps fallback; orchestration dispatch only supports delegated_runner in v1"
                row.updated_at = _utcnow()
                session.add(row)
            continue
        if row.status not in {"queued", "waiting_dependency"}:
            continue
        node = get_node(session, row.target_node)
        if not node or not node.enabled:
            row.last_error = "target node unavailable"
            row.updated_at = _utcnow()
            session.add(row)
            continue
        node_limit = max(1, int(getattr(node, "max_concurrent_jobs", 1) or 1))
        if active_global >= settings.global_max_active_jobs or active_by_node.get(row.target_node, 0) >= node_limit or _workspace_locked(rows, row):
            row.status = "queued"
            row.updated_at = _utcnow()
            session.add(row)
            continue
        payload = {
            "title": row.title,
            "repo_path": row.repo_path,
            "workspace_path": row.workspace_path,
            "prompt": row.prompt,
            "instructions": row.instructions,
            "mode": row.codex_mode,
            "timeout_seconds": row.timeout_seconds,
            "task_type": row.task_type,
            "metadata": _jloads_dict(row.metadata_json),
        }
        try:
            response = _runner_client_for_node(node).create_job("orchestration.codex", payload)
        except RunnerClientError as exc:
            row.last_error = str(exc.detail)
            row.updated_at = _utcnow()
            session.add(row)
            continue
        row.runner_job_id = str(response.get("job_id") or response.get("id") or "")
        row.assigned_runner = node.base_url
        row.logs_url = f"/api/orchestration/jobs/{row.id}/logs"
        row.status = _runner_status_to_orchestration(str(response.get("status", "dispatched")))
        row.started_at = row.started_at or _utcnow()
        row.updated_at = _utcnow()
        row.metadata_json = _jdumps(
            {
                **_jloads_dict(row.metadata_json),
                "dispatch": {
                    "node_id": node.id,
                    "node_label": node.label,
                    "base_url": node.base_url,
                    "execution_mode": row.execution_mode,
                },
            }
        )
        session.add(row)
        active_by_node[row.target_node] = active_by_node.get(row.target_node, 0) + 1
        active_global += 1
    session.commit()
    return list_jobs(session)


def cancel_job(session: Session, row: OrchestrationJob) -> OrchestrationJob:
    if row.status in TERMINAL_STATUSES:
        return row
    node = get_node(session, row.target_node)
    if row.runner_job_id and node:
        try:
            _runner_client_for_node(node).cancel_job(row.runner_job_id)
        except Exception as exc:
            row.last_error = f"cancel request failed: {exc}"
    row.status = "canceled"
    row.finished_at = row.finished_at or _utcnow()
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def retry_job(session: Session, row: OrchestrationJob) -> OrchestrationJob:
    row.retry_count += 1
    row.runner_job_id = ""
    row.status = "queued"
    row.started_at = None
    row.finished_at = None
    row.assigned_runner = ""
    row.logs_url = ""
    row.result_summary = ""
    row.changed_files_json = "[]"
    row.artifacts_json = "[]"
    row.last_error = ""
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    reconcile_jobs(session)
    session.refresh(row)
    return row


def get_job_logs(session: Session, row: OrchestrationJob, offset: int = 0, max_lines: int = 200) -> dict[str, Any]:
    node = get_node(session, row.target_node)
    if not node or not row.runner_job_id:
        return {"offset": offset, "lines": []}
    try:
        return _runner_client_for_node(node).get_logs(row.runner_job_id, offset=offset, max_lines=max_lines)
    except Exception as exc:
        return {"offset": offset, "lines": [], "error": str(exc)}


def get_job_result(session: Session, row: OrchestrationJob) -> dict[str, Any]:
    node = get_node(session, row.target_node)
    payload = orchestration_job_to_payload(row)
    payload["runner_detail"] = _jloads_dict(row.metadata_json).get("runner_detail", {})
    if not node or not row.runner_job_id:
        return payload
    try:
        detail = _runner_client_for_node(node).get_job(row.runner_job_id)
        payload["runner_detail"] = detail if isinstance(detail, dict) else {}
    except Exception as exc:
        payload["runner_detail_error"] = str(exc)
    return payload


def list_mailbox_items(
    session: Session,
    *,
    direction: str | None = None,
    node_id: str | None = None,
    job_id: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    nodes: list[RemoteOpsNode]
    if node_id:
        node = get_node(session, node_id)
        nodes = [node] if node else []
    else:
        nodes = list(session.exec(select(RemoteOpsNode).where(RemoteOpsNode.enabled.is_(True))).all())
    items: list[dict[str, Any]] = []
    for node in nodes:
        if not node:
            continue
        client = _runner_client_for_node(node)
        try:
            if direction == "inbox":
                payload = client.mailbox_inbox(limit=limit, include_archived=include_archived, job_id=job_id)
            elif direction == "outbox":
                payload = client.mailbox_outbox(limit=limit, include_archived=include_archived, job_id=job_id)
            else:
                payload = client.mailbox_archive(limit=limit, job_id=job_id) if include_archived else client.mailbox_outbox(limit=limit, include_archived=False, job_id=job_id)
        except Exception:
            continue
        rows = payload.get("items") if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            if direction is None and not include_archived:
                # Pull inbox alongside outbox when the caller asks for aggregate active feed.
                items.append(_mailbox_item_to_payload(node.id, item))
            else:
                items.append(_mailbox_item_to_payload(node.id, item))
        if direction is None and not include_archived:
            try:
                inbox_payload = client.mailbox_inbox(limit=limit, include_archived=False, job_id=job_id)
                inbox_rows = inbox_payload.get("items") if isinstance(inbox_payload, dict) else []
                if isinstance(inbox_rows, list):
                    for item in inbox_rows:
                        if isinstance(item, dict):
                            items.append(_mailbox_item_to_payload(node.id, item))
            except Exception:
                pass
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items[:limit]


def create_mailbox_note(session: Session, node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    node = get_node(session, node_id)
    if not node:
        raise ValueError("node not found")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata = dict(metadata)
    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    knowledge_query = str(metadata.get("knowledge_query") or payload.get("subject") or payload.get("body") or "").strip()
    if metadata.get("knowledge_lookup", True) and knowledge_query:
        knowledge_matches = search_mail_knowledge(
            knowledge_query,
            filters={
                "topic": str(metadata.get("knowledge_topic") or "").strip() or None,
                "tags": tags[:8] or None,
            },
            limit=max(1, min(int(metadata.get("knowledge_limit") or 3), 10)),
        )
        if knowledge_matches:
            metadata["knowledge_matches"] = [
                {
                    "title": str(match.get("title") or ""),
                    "summary": str(match.get("summary") or ""),
                    "record_type": str(match.get("record_type") or ""),
                    "topic": str(match.get("topic") or ""),
                }
                for match in knowledge_matches[:5]
            ]
            metadata["knowledge_matches_count"] = len(knowledge_matches)
    body = {
        "type": str(payload.get("type") or "note"),
        "subject": str(payload.get("subject") or "").strip(),
        "body": str(payload.get("body") or "").strip(),
        "job_id": str(payload.get("job_id") or "").strip(),
        "run_id": str(payload.get("run_id") or "").strip(),
        "severity": str(payload.get("severity") or "info"),
        "from": str(payload.get("from") or "dashburg-operator"),
        "to": str(payload.get("to") or f"runner@{node.id}"),
        "attachments": payload.get("attachments") if isinstance(payload.get("attachments"), list) else [],
        "tags": tags,
        "metadata": metadata,
    }
    item = _runner_client_for_node(node).create_mailbox_note(body)
    note = _mailbox_item_to_payload(node.id, item if isinstance(item, dict) else {})

    save_to_knowledge = bool(
        metadata.get("save_to_knowledge")
        or metadata.get("reusable")
        or "knowledge" in tags
        or "reusable" in tags
    )
    if save_to_knowledge and body["body"]:
        record_type = str(metadata.get("knowledge_record_type") or "").strip().lower().replace("-", "_")
        if record_type not in MAIL_RECORD_TYPES:
            record_type = "email_playbook" if body["type"] in {"handoff", "needs_input", "diagnostic"} else "reply_pattern"
        knowledge_result = maybe_add_mail_record(
            record_type=record_type,
            title=str(metadata.get("knowledge_title") or body["subject"] or f"{node.label} mailbox note").strip(),
            summary=str(metadata.get("knowledge_summary") or body["body"][:280]).strip(),
            content=body["body"],
            tags=sorted({*tags, "orchestration_mailbox", node.id}),
            topic=str(metadata.get("knowledge_topic") or body["subject"] or node.label).strip(),
            metadata={
                "node_id": node.id,
                "mailbox_item_id": note.get("id"),
                "mailbox_type": body["type"],
                "job_id": body["job_id"],
                "run_id": body["run_id"],
            },
            confidence=float(metadata.get("knowledge_confidence") or 0.82),
            usefulness=float(metadata.get("knowledge_usefulness") or 0.8),
            reusable=True,
        )
        note_metadata = note.get("metadata") if isinstance(note.get("metadata"), dict) else {}
        note_metadata["knowledge_write"] = knowledge_result
        note["metadata"] = note_metadata
    return note


def send_mail_message(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    to_value = str(payload.get("to") or "").strip()
    parsed = _parse_mail_recipient(to_value)
    target_node_id = str(
        payload.get("target_node_id")
        or payload.get("node_id")
        or parsed.get("node_id")
        or ""
    ).strip()
    if not target_node_id:
        raise ValueError("target node could not be inferred from recipient")
    if not to_value:
        to_value = f"node:{target_node_id}/runner"
        parsed = _parse_mail_recipient(to_value)

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    merged_metadata = {
        **metadata,
        "recipient": to_value,
        "recipient_node_id": target_node_id,
        "recipient_kind": str(parsed.get("kind") or "runner"),
        "recipient_agent_slug": str(parsed.get("agent_slug") or ""),
        "mail_origin": "orchestration",
    }
    note_payload: dict[str, Any] = {
        "type": str(payload.get("type") or "note"),
        "subject": str(payload.get("subject") or "").strip(),
        "body": str(payload.get("body") or "").strip(),
        "severity": str(payload.get("severity") or "info"),
        "from": str(payload.get("from") or "orchestration@dashburg.local"),
        "to": to_value,
        "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else [],
        "metadata": merged_metadata,
        "job_id": str(payload.get("job_id") or "").strip(),
        "run_id": str(payload.get("run_id") or "").strip(),
        "attachments": payload.get("attachments") if isinstance(payload.get("attachments"), list) else [],
    }
    if not note_payload["subject"]:
        raise ValueError("subject is required")
    if not note_payload["body"]:
        raise ValueError("body is required")
    return create_mailbox_note(session, target_node_id, note_payload)


def acknowledge_mailbox_item(session: Session, node_id: str, item_id: str) -> dict[str, Any]:
    node = get_node(session, node_id)
    if not node:
        raise ValueError("node not found")
    item = _runner_client_for_node(node).acknowledge_mailbox_item(item_id)
    return _mailbox_item_to_payload(node.id, item if isinstance(item, dict) else {})


def archive_mailbox_item(session: Session, node_id: str, item_id: str) -> dict[str, Any]:
    node = get_node(session, node_id)
    if not node:
        raise ValueError("node not found")
    item = _runner_client_for_node(node).archive_mailbox_item(item_id)
    return _mailbox_item_to_payload(node.id, item if isinstance(item, dict) else {})


def build_overview(session: Session) -> dict[str, Any]:
    rows = reconcile_jobs(session)
    settings = ensure_settings(session)
    remote_settings = session.get(RemoteOpsSettings, 1)
    health_rows = {item["node_id"]: item for item in get_nodes_health_status(session).get("items", [])}
    nodes = session.exec(select(RemoteOpsNode).order_by(RemoteOpsNode.label.asc(), RemoteOpsNode.id.asc())).all()
    active_by_node = _active_jobs_by_node(rows)
    queued_by_node: dict[str, int] = {}
    for row in rows:
        if row.status in {"queued", "waiting_dependency"}:
            queued_by_node[row.target_node] = queued_by_node.get(row.target_node, 0) + 1
    node_rows = []
    for node in nodes:
        caps = _jloads_dict(getattr(node, "capabilities_json", "{}"))
        node_rows.append(
            {
                "id": node.id,
                "label": node.label,
                "base_url": node.base_url,
                "enabled": node.enabled,
                "supports_codex": node.supports_codex,
                "supports_terminal": node.supports_terminal,
                "max_concurrent_jobs": getattr(node, "max_concurrent_jobs", 1) or 1,
                "running_jobs": active_by_node.get(node.id, 0),
                "queued_jobs": queued_by_node.get(node.id, 0),
                "health_status": str((health_rows.get(node.id) or {}).get("status") or "unknown"),
                "capabilities": {
                    "installed_repos": _jloads_list(node.allowed_repos_json),
                    **caps,
                },
                "repos": _jloads_list(node.allowed_repos_json),
                "mailbox_counts": {
                    "inbox": 0,
                    "outbox": 0,
                    "archive": 0,
                },
            }
        )
    mailbox_feed = list_mailbox_items(session, limit=40)
    mailbox_by_node: dict[str, dict[str, int]] = {}
    for item in mailbox_feed:
        bucket = mailbox_by_node.setdefault(str(item["node_id"]), {"inbox": 0, "outbox": 0, "archive": 0})
        direction = str(item.get("direction") or "outbox")
        if item.get("archived"):
            bucket["archive"] += 1
        elif direction in {"inbox", "outbox"}:
            bucket[direction] += 1
    for node in node_rows:
        node["mailbox_counts"] = mailbox_by_node.get(node["id"], {"inbox": 0, "outbox": 0, "archive": 0})
    return {
        "localops_mode": "LocalOps remains the direct/manual process described in MEM.md.",
        "orchestration_mode": "Orchestration is the delegated multi-node runner path.",
        "settings": settings_to_dict(settings),
        "nodes": node_rows,
        "running_jobs": [orchestration_job_to_payload(row) for row in rows if row.status in ACTIVE_STATUSES],
        "queued_jobs": [orchestration_job_to_payload(row) for row in rows if row.status in WAITING_STATUSES],
        "recent_jobs": [orchestration_job_to_payload(row) for row in rows[:20]],
        "dependency_edges": [
            {"job_id": row.id, "depends_on": dep["job_id"], "status": dep["status"]}
            for row in rows
            for dep in (orchestration_job_to_payload(row).get("dependency_state") or [])
        ][:80],
        "mailbox": mailbox_feed,
        "remoteops_defaults": {
            "default_target_node_id": remote_settings.default_target_node_id if remote_settings else "",
            "max_concurrent_jobs_per_node": remote_settings.max_concurrent_jobs_per_node if remote_settings else 1,
        },
    }


def terminal_launch_payload(session: Session) -> dict[str, Any]:
    settings = ensure_settings(session)
    node_id = settings.preferred_terminal_node_id or "devwork"
    codex_prompt = (
        'Please load cluster memory from /mnt/nas_ai/shared/MEM.md first when available; if unavailable, fallback to ~/MEM.md, '
        "and use that as host topology memory for this session. "
        "For remote investigations, open ONE persistent SSH session per target host and run multiple commands inside that session; "
        "avoid one-off ssh command invocations unless necessary. Before finishing any remote investigation, write two markdown files "
        "on that remote machine under ~/runner/investigations/: (1) a timestamped conclusion file with findings and next actions, and "
        "(2) a host/repo profile file with durable observations, discovered settings, and known issues so future agents can understand "
        "the device/repo quickly. Summarize key nodes and SSH/RemoteOps commands first."
    )
    preamble = (
        "Dashburg Orchestration Agent\\n"
        "- This terminal is the main orchestration agent.\\n"
        "- Use delegated_runner jobs for multi-node work.\\n"
        "- Keep LocalOps as the existing direct/manual process.\\n"
        "- Read MEM.md and docs/ORCHESTRATION.md before large runs.\\n"
        "- Prefer remoteops node-local runners over direct SSH execution.\\n"
        "- Preferred terminal node for orchestration is devwork.\\n"
    )
    command = (
        "bash -lc '"
        "clear; "
        f"printf \"%b\" \"{preamble}\"; "
        "mkdir -p ~/runner/orchestration; "
        "printf \"%b\" \"Dashburg Orchestration\\npreferred_mode=delegated_runner\\nlocalops=current_direct_process\\n\" > ~/runner/orchestration/session-context.txt; "
        f"exec codex {json.dumps(codex_prompt)}'"
    )
    return {
        "node_id": node_id,
        "cwd": "/srv/repos/dashgithub",
        "command": command,
        "injected_label": "Launch Main Orchestration Agent",
    }
