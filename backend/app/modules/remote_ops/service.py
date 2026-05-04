from __future__ import annotations

import json
import os
import secrets
import uuid
import getpass
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from sqlmodel import Session, select

from app.core.paths import remoteops_data_dir, remoteops_inventory_path
from app.models.remoteops import RemoteOpsJob, RemoteOpsNode, RemoteOpsNodeKey, RemoteOpsSettings, RemoteOpsTerminalSession
from app.modules.remote_ops.runner_client import RunnerClient, RunnerClientError


ROOT_DIR = Path(__file__).resolve().parents[4]
REMOTEOPS_DIR = remoteops_data_dir()
SECRETS_PATH = REMOTEOPS_DIR / "secrets.json"
BOOTSTRAP_INVENTORY_PATHS = [remoteops_inventory_path(), ROOT_DIR / "examples" / "servers.yaml"]
REMOTE_HEALTH_TTL_SECONDS = int(os.getenv("REMOTEOPS_HEALTH_TTL_SECONDS", "15"))
REMOTE_HEALTH_TIMEOUT_SECONDS = float(os.getenv("REMOTEOPS_HEALTH_TIMEOUT_SECONDS", "2.0"))
REMOTE_HEALTH_SLOW_MS = int(os.getenv("REMOTEOPS_HEALTH_SLOW_MS", "600"))
REMOTE_HOST_MONITOR_TTL_SECONDS = int(os.getenv("REMOTEOPS_HOST_MONITOR_TTL_SECONDS", "15"))
# Host-monitor payload collection can take several seconds on slower nodes.
# Keep default generous to avoid false "down" from timeout/fallback to legacy daemon.
REMOTE_HOST_MONITOR_TIMEOUT_SECONDS = float(os.getenv("REMOTEOPS_HOST_MONITOR_TIMEOUT_SECONDS", "8.0"))
REMOTE_HOST_MONITOR_SCHEME = os.getenv("REMOTEOPS_HOST_MONITOR_SCHEME", "http").strip() or "http"
REMOTE_HOST_MONITOR_PORT = int(os.getenv("REMOTEOPS_HOST_MONITOR_PORT", "19444"))
REMOTE_HOST_MONITOR_TOKEN = os.getenv("REMOTEOPS_HOST_MONITOR_TOKEN", os.getenv("HOST_MONITOR_TOKEN", "")).strip()
REMOTE_CHECK_MAX_WORKERS = max(1, int(os.getenv("REMOTEOPS_CHECK_MAX_WORKERS", "6")))
REMOTE_NODE_SERVICE_TIMEOUT_SECONDS = float(os.getenv("REMOTEOPS_NODE_SERVICE_TIMEOUT_SECONDS", "1.5"))
REMOTE_OLLAMA_DEFAULT_PORT = int(os.getenv("REMOTEOPS_OLLAMA_PORT", "11434"))
REMOTE_COMFYUI_DEFAULT_PORT = int(os.getenv("REMOTEOPS_COMFYUI_PORT", "8188"))

_health_cache: dict[str, dict[str, Any]] = {}
_health_cache_all: dict[str, Any] | None = None
_host_monitor_cache: dict[str, dict[str, Any]] = {}
_host_monitor_cache_all: dict[str, Any] | None = None


class RemoteOpsError(Exception):
    def __init__(self, status: int, detail: str | dict[str, Any]):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


@dataclass
class SecretKey:
    key_id: str
    secret: str
    created_at: str
    disabled_at: str | None = None


def _utcnow() -> datetime:
    return datetime.utcnow()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jloads_dict(text: str | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not text:
        return fallback or {}
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else (fallback or {})
    except json.JSONDecodeError:
        return fallback or {}


def _jloads_list(text: str | None) -> list[str]:
    if not text:
        return []
    try:
        val = json.loads(text)
        if isinstance(val, list):
            return [str(v) for v in val]
    except json.JSONDecodeError:
        pass
    return []


def _jdumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def ensure_remoteops_data_dir() -> None:
    REMOTEOPS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        REMOTEOPS_DIR.chmod(0o700)
    except OSError:
        pass


def _load_secrets_file() -> dict[str, Any]:
    ensure_remoteops_data_dir()
    if not SECRETS_PATH.exists():
        data = {"nodes": {}}
        SECRETS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            SECRETS_PATH.chmod(0o600)
        except OSError:
            pass
        return data
    try:
        raw = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        raw = {"nodes": {}}
    if not isinstance(raw, dict):
        raw = {"nodes": {}}
    if not isinstance(raw.get("nodes"), dict):
        raw["nodes"] = {}
    return raw


def _save_secrets_file(data: dict[str, Any]) -> None:
    ensure_remoteops_data_dir()
    SECRETS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        SECRETS_PATH.chmod(0o600)
    except OSError:
        pass


def _active_secret_for_node(node_id: str, key_id: str | None = None) -> str | None:
    data = _load_secrets_file()
    node = data.get("nodes", {}).get(node_id, {})
    keys = node.get("keys", []) if isinstance(node, dict) else []
    if not isinstance(keys, list):
        return None

    preferred = None
    for item in keys:
        if not isinstance(item, dict):
            continue
        if item.get("disabledAt"):
            continue
        if key_id and item.get("keyId") == key_id:
            return str(item.get("secret", ""))
        preferred = str(item.get("secret", ""))
    return preferred


def _set_node_secret(node_id: str, key_id: str, secret: str, disable_previous: bool = False) -> None:
    data = _load_secrets_file()
    nodes = data.setdefault("nodes", {})
    node = nodes.setdefault(node_id, {"keys": []})
    keys = node.setdefault("keys", [])
    if disable_previous:
        for item in keys:
            if isinstance(item, dict) and not item.get("disabledAt"):
                item["disabledAt"] = _now_iso()
    keys.append({"keyId": key_id, "secret": secret, "createdAt": _now_iso(), "disabledAt": None})
    _save_secrets_file(data)


def _disable_key_secret(node_id: str, key_id: str) -> None:
    data = _load_secrets_file()
    keys = data.get("nodes", {}).get(node_id, {}).get("keys", [])
    changed = False
    for item in keys:
        if isinstance(item, dict) and item.get("keyId") == key_id and not item.get("disabledAt"):
            item["disabledAt"] = _now_iso()
            changed = True
    if changed:
        _save_secrets_file(data)


def _delete_node_secrets(node_id: str) -> None:
    data = _load_secrets_file()
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return
    if node_id in nodes:
        nodes.pop(node_id, None)
        _save_secrets_file(data)


def _parse_node_id(raw: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")


def _gen_key_id(node_id: str) -> str:
    return f"{node_id}-{uuid.uuid4().hex[:8]}"


def _gen_secret() -> str:
    return secrets.token_urlsafe(32)


def ensure_settings(session: Session) -> RemoteOpsSettings:
    row = session.get(RemoteOpsSettings, 1)
    if row:
        return row
    row = RemoteOpsSettings(id=1)
    row.client_token = secrets.token_urlsafe(24)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def settings_to_dict(row: RemoteOpsSettings) -> dict[str, Any]:
    return {
        "main_llm_provider": row.main_llm_provider,
        "main_llm_model": row.main_llm_model,
        "main_llm_base_url": row.main_llm_base_url,
        "main_llm_api_key_ref": row.main_llm_api_key_ref,
        "chat_enabled": row.chat_enabled,
        "execution_mode": row.execution_mode,
        "default_target_node_id": row.default_target_node_id,
        "job_timeouts": _jloads_dict(row.job_timeouts_json),
        "log_retention_days": row.log_retention_days,
        "allow_codex_jobs": row.allow_codex_jobs,
        "allow_system_actions": row.allow_system_actions,
        "allow_apt_upgrade": row.allow_apt_upgrade,
        "max_concurrent_jobs_per_node": row.max_concurrent_jobs_per_node,
        "max_concurrent_jobs_global": row.max_concurrent_jobs_global,
        "terminal_enabled": row.terminal_enabled,
        "terminal_idle_timeout_minutes": row.terminal_idle_timeout_minutes,
        "terminal_max_sessions": row.terminal_max_sessions,
        "terminal_recording_enabled": row.terminal_recording_enabled,
        "chat_client_token": row.client_token,
    }


def update_settings(session: Session, payload: dict[str, Any]) -> RemoteOpsSettings:
    row = ensure_settings(session)
    row.main_llm_provider = str(payload.get("main_llm_provider", row.main_llm_provider))
    row.main_llm_model = str(payload.get("main_llm_model", row.main_llm_model))
    row.main_llm_base_url = str(payload.get("main_llm_base_url", row.main_llm_base_url))
    row.main_llm_api_key_ref = str(payload.get("main_llm_api_key_ref", row.main_llm_api_key_ref))
    row.chat_enabled = bool(payload.get("chat_enabled", row.chat_enabled))
    row.execution_mode = str(payload.get("execution_mode", row.execution_mode))
    row.default_target_node_id = str(payload.get("default_target_node_id", row.default_target_node_id))
    row.job_timeouts_json = _jdumps(payload.get("job_timeouts", _jloads_dict(row.job_timeouts_json)))
    row.log_retention_days = int(payload.get("log_retention_days", row.log_retention_days))
    row.allow_codex_jobs = bool(payload.get("allow_codex_jobs", row.allow_codex_jobs))
    row.allow_system_actions = bool(payload.get("allow_system_actions", row.allow_system_actions))
    row.allow_apt_upgrade = bool(payload.get("allow_apt_upgrade", row.allow_apt_upgrade))
    row.max_concurrent_jobs_per_node = int(payload.get("max_concurrent_jobs_per_node", row.max_concurrent_jobs_per_node))
    row.max_concurrent_jobs_global = int(payload.get("max_concurrent_jobs_global", row.max_concurrent_jobs_global))
    row.terminal_enabled = bool(payload.get("terminal_enabled", row.terminal_enabled))
    row.terminal_idle_timeout_minutes = int(payload.get("terminal_idle_timeout_minutes", row.terminal_idle_timeout_minutes))
    row.terminal_max_sessions = int(payload.get("terminal_max_sessions", row.terminal_max_sessions))
    row.terminal_recording_enabled = bool(payload.get("terminal_recording_enabled", row.terminal_recording_enabled))
    token = str(payload.get("chat_client_token", row.client_token)).strip()
    row.client_token = token or row.client_token
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _node_keys(session: Session, node_id: str) -> list[RemoteOpsNodeKey]:
    stmt = select(RemoteOpsNodeKey).where(RemoteOpsNodeKey.node_id == node_id).order_by(RemoteOpsNodeKey.created_at.desc())
    return list(session.exec(stmt).all())


def node_to_dict(session: Session, node: RemoteOpsNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "enabled": node.enabled,
        "label": node.label,
        "base_url": node.base_url,
        "supports_codex": node.supports_codex,
        "supports_terminal": node.supports_terminal,
        "max_concurrent_jobs": getattr(node, "max_concurrent_jobs", 1),
        "capabilities": _jloads_dict(getattr(node, "capabilities_json", "{}")),
        "allowed_job_types": _jloads_list(node.allowed_job_types_json),
        "allowed_repos": _jloads_list(node.allowed_repos_json),
        "allowed_services": _jloads_list(node.allowed_services_json),
        "notes": node.notes,
        "key_id": node.key_id,
        "last_seen_at": node.last_seen_at,
        "created_at": node.created_at,
        "updated_at": node.updated_at,
        "keys": [
            {
                "key_id": k.key_id,
                "created_at": k.created_at,
                "disabled_at": k.disabled_at,
            }
            for k in _node_keys(session, node.id)
        ],
    }


def list_nodes(session: Session) -> list[dict[str, Any]]:
    rows = session.exec(select(RemoteOpsNode).order_by(RemoteOpsNode.label.asc(), RemoteOpsNode.id.asc())).all()
    return [node_to_dict(session, n) for n in rows]


def get_node(session: Session, node_id: str) -> RemoteOpsNode | None:
    return session.get(RemoteOpsNode, node_id)


def create_node(session: Session, payload: dict[str, Any]) -> tuple[RemoteOpsNode, str]:
    node_id = _parse_node_id(str(payload.get("id", "")))
    if not node_id:
        raise RemoteOpsError(400, "Node id is required")
    if get_node(session, node_id):
        raise RemoteOpsError(409, "Node id already exists")

    key_id = _gen_key_id(node_id)
    secret = _gen_secret()
    now = _utcnow()
    node = RemoteOpsNode(
        id=node_id,
        enabled=bool(payload.get("enabled", True)),
        label=str(payload.get("label", node_id)),
        base_url=str(payload.get("base_url", "")).rstrip("/"),
        supports_codex=bool(payload.get("supports_codex", False)),
        supports_terminal=bool(payload.get("supports_terminal", False)),
        max_concurrent_jobs=int(payload.get("max_concurrent_jobs", 1)),
        capabilities_json=_jdumps(payload.get("capabilities", {})),
        allowed_job_types_json=_jdumps(payload.get("allowed_job_types", [])),
        allowed_repos_json=_jdumps(payload.get("allowed_repos", [])),
        allowed_services_json=_jdumps(payload.get("allowed_services", [])),
        notes=str(payload.get("notes", "")),
        key_id=key_id,
        created_at=now,
        updated_at=now,
    )
    session.add(node)
    session.add(
        RemoteOpsNodeKey(
            node_id=node_id,
            key_id=key_id,
            secret_ref=f"secret:{node_id}:{key_id}",
            created_at=now,
        )
    )
    _set_node_secret(node_id, key_id, secret, disable_previous=False)
    session.commit()
    session.refresh(node)
    return node, secret


def update_node(session: Session, node: RemoteOpsNode, payload: dict[str, Any]) -> RemoteOpsNode:
    node.enabled = bool(payload.get("enabled", node.enabled))
    node.label = str(payload.get("label", node.label))
    node.base_url = str(payload.get("base_url", node.base_url)).rstrip("/")
    node.supports_codex = bool(payload.get("supports_codex", node.supports_codex))
    node.supports_terminal = bool(payload.get("supports_terminal", node.supports_terminal))
    node.max_concurrent_jobs = int(payload.get("max_concurrent_jobs", getattr(node, "max_concurrent_jobs", 1)))
    node.capabilities_json = _jdumps(payload.get("capabilities", _jloads_dict(getattr(node, "capabilities_json", "{}"))))
    node.allowed_job_types_json = _jdumps(payload.get("allowed_job_types", _jloads_list(node.allowed_job_types_json)))
    node.allowed_repos_json = _jdumps(payload.get("allowed_repos", _jloads_list(node.allowed_repos_json)))
    node.allowed_services_json = _jdumps(payload.get("allowed_services", _jloads_list(node.allowed_services_json)))
    node.notes = str(payload.get("notes", node.notes))
    node.updated_at = _utcnow()
    session.add(node)
    session.commit()
    session.refresh(node)
    return node


def delete_node(session: Session, node: RemoteOpsNode) -> None:
    for key in _node_keys(session, node.id):
        session.delete(key)
    jobs = session.exec(select(RemoteOpsJob).where(RemoteOpsJob.node_id == node.id)).all()
    for job in jobs:
        session.delete(job)
    sess_rows = session.exec(select(RemoteOpsTerminalSession).where(RemoteOpsTerminalSession.node_id == node.id)).all()
    for row in sess_rows:
        session.delete(row)
    session.delete(node)
    session.commit()
    _delete_node_secrets(node.id)


def rotate_node_key(session: Session, node: RemoteOpsNode, disable_previous: bool = False) -> tuple[RemoteOpsNode, str, str]:
    now = _utcnow()
    new_key = _gen_key_id(node.id)
    new_secret = _gen_secret()

    if disable_previous and node.key_id:
        for key in _node_keys(session, node.id):
            if key.key_id == node.key_id and key.disabled_at is None:
                key.disabled_at = now
                session.add(key)
        _disable_key_secret(node.id, node.key_id)

    node.key_id = new_key
    node.updated_at = now
    session.add(node)
    session.add(
        RemoteOpsNodeKey(
            node_id=node.id,
            key_id=new_key,
            secret_ref=f"secret:{node.id}:{new_key}",
            created_at=now,
        )
    )
    _set_node_secret(node.id, new_key, new_secret, disable_previous=disable_previous)
    session.commit()
    session.refresh(node)
    return node, new_key, new_secret


def disable_node_key(session: Session, node: RemoteOpsNode, key_id: str) -> None:
    target = None
    for key in _node_keys(session, node.id):
        if key.key_id == key_id:
            target = key
            break
    if target is None:
        raise RemoteOpsError(404, "key not found")
    if node.key_id == key_id:
        raise RemoteOpsError(400, "cannot disable active key")
    target.disabled_at = _utcnow()
    session.add(target)
    session.commit()
    _disable_key_secret(node.id, key_id)


def _runner_client_for_node(node: RemoteOpsNode, timeout: float | None = None) -> RunnerClient:
    secret = _active_secret_for_node(node.id, node.key_id)
    if not secret:
        raise RemoteOpsError(500, f"No active secret for node {node.id}")
    return RunnerClient(base_url=node.base_url, key_id=node.key_id, secret=secret, timeout=timeout or 8.0)


def node_health(session: Session, node: RemoteOpsNode) -> dict[str, Any]:
    try:
        health = _runner_client_for_node(node).health()
        node.last_seen_at = _utcnow()
        session.add(node)
        session.commit()
        return {"status": "online", "health": health}
    except RunnerClientError as exc:
        return {"status": "offline", "error": exc.detail, "upstream_status": exc.status}
    except Exception as exc:
        return {"status": "offline", "error": str(exc)}


def _classify_health(ok: bool, latency_ms: int | None) -> str:
    if not ok:
        return "down"
    if latency_ms is not None and latency_ms >= REMOTE_HEALTH_SLOW_MS:
        return "slow"
    return "healthy"


def _host_for_node(node: RemoteOpsNode) -> str:
    parsed = urllib.parse.urlparse(node.base_url)
    if parsed.hostname:
        return parsed.hostname
    fallback = node.base_url.split("://", 1)[-1].split("/", 1)[0]
    fallback = fallback.split(":", 1)[0].strip()
    if not fallback:
        raise RemoteOpsError(500, f"Unable to derive host for node {node.id}")
    return fallback


def _host_monitor_base_url(node: RemoteOpsNode) -> str:
    host = _host_for_node(node)
    return f"{REMOTE_HOST_MONITOR_SCHEME}://{host}:{REMOTE_HOST_MONITOR_PORT}"


def _host_monitor_request(node: RemoteOpsNode, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    base = _host_monitor_base_url(node)
    url = f"{base}{path}"
    headers = {"Accept": "application/json"}
    if REMOTE_HOST_MONITOR_TOKEN:
        headers["X-Host-Monitor-Token"] = REMOTE_HOST_MONITOR_TOKEN
    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=REMOTE_HOST_MONITOR_TIMEOUT_SECONDS) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _runner_host_monitor_fallback(node: RemoteOpsNode) -> dict[str, Any]:
    """Build a minimal host-monitor payload from signed runner endpoints."""
    client = _runner_client_for_node(node, timeout=REMOTE_HOST_MONITOR_TIMEOUT_SECONDS)
    base_url = node.base_url.rstrip("/")

    def _fetch(path: str, signed_call: Any) -> tuple[dict[str, Any], str]:
        try:
            payload = signed_call()
            return payload if isinstance(payload, dict) else {}, "signed"
        except Exception:
            try:
                payload = _http_get_json(f"{base_url}{path}", timeout=REMOTE_HOST_MONITOR_TIMEOUT_SECONDS)
                return payload if isinstance(payload, dict) else {}, "unsigned"
            except Exception:
                return {}, "unavailable"

    health, health_source = _fetch("/v1/health", client.health)
    metrics, metrics_source = _fetch("/v1/metrics", client.metrics)
    services, services_source = _fetch("/v1/services", client.services)

    if not health and not metrics and not services:
        raise RuntimeError("runner fallback endpoints unavailable")

    loadavg_raw = metrics.get("loadavg") if isinstance(metrics.get("loadavg"), list) else []
    loadavg = [float(v) for v in loadavg_raw[:3] if isinstance(v, (int, float))]
    while len(loadavg) < 3:
        loadavg.append(0.0)

    cpu_percent = float(metrics.get("cpu_percent") or 0.0)
    memory_percent = float(metrics.get("memory_percent") or 0.0)
    disk_percent = float(metrics.get("disk_percent") or 0.0)
    uptime_seconds = int(metrics.get("uptime_seconds") or 0)

    host = str(health.get("hostname") or _host_for_node(node))
    return {
        "ok": True,
        "timestamp": _now_iso(),
        "host": host,
        "health": {"status": "healthy", "issues": []},
        "cpu": {"usage_percent": cpu_percent, "load1": loadavg[0], "load5": loadavg[1], "load15": loadavg[2]},
        "memory": {"used_gib": 0.0, "total_gib": 0.0, "used_percent": memory_percent},
        "swap": {"used_gib": 0.0, "total_gib": 0.0, "used_percent": 0.0},
        "disk": {"mount": "/", "used_gib": 0.0, "total_gib": 0.0, "used_percent": disk_percent},
        "ollama": {
            "enabled": False,
            "status": "disabled",
            "process_count": 0,
            "listening_11434": False,
            "models_count": 0,
            "error": None,
            "services": {"branding": "unknown", "translate": "unknown", "vision": "unknown"},
        },
        "gpus": [],
        "top_processes": [],
        "gpu_processes": [],
        "top_snapshot": [],
        "services": services.get("items") if isinstance(services.get("items"), list) else [],
        "runner_fallback": {
            "source": f"{base_url}/v1/health|/v1/metrics|/v1/services",
            "health_source": health_source,
            "metrics_source": metrics_source,
            "services_source": services_source,
            "uptime_seconds": uptime_seconds,
        },
    }


def _check_node_host_monitor_live(node: RemoteOpsNode) -> dict[str, Any]:
    started = time.perf_counter()
    checked_at = _utcnow().isoformat() + "Z"
    monitor_url = _host_monitor_base_url(node)
    try:
        payload: dict[str, Any] | None = None
        client = _runner_client_for_node(node, timeout=REMOTE_HOST_MONITOR_TIMEOUT_SECONDS)
        # Preferred path: query monitoring payload directly from runner API.
        try:
            payload = client.host_monitor_status()
            monitor_url = f"{node.base_url.rstrip('/')}/v1/host-monitor/status"
        except RunnerClientError as exc:
            # Compatibility fallback for older runners (for example some Windows nodes)
            # that expose signed health/metrics but not host-monitor endpoints.
            if exc.status in {401, 403, 404, 405, 501}:
                payload = _runner_host_monitor_fallback(node)
                monitor_url = f"{node.base_url.rstrip('/')}/v1/health"
            else:
                raise
        except Exception:
            # Backward-compatible fallback: legacy direct host-monitor daemon on :19444.
            payload = _host_monitor_request(node, "/status")
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "node_id": node.id,
            "label": node.label,
            "monitor_base_url": monitor_url,
            "ok": True,
            "latency_ms": latency_ms,
            "status": _classify_health(True, latency_ms),
            "checked_at": checked_at,
            "error": None,
            "payload": payload or {},
        }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
        return {
            "node_id": node.id,
            "label": node.label,
            "monitor_base_url": monitor_url,
            "ok": False,
            "latency_ms": None,
            "status": "down",
            "checked_at": checked_at,
            "error": f"HTTP {exc.code}: {raw or str(exc)}",
            "payload": {},
        }
    except urllib.error.URLError as exc:
        return {
            "node_id": node.id,
            "label": node.label,
            "monitor_base_url": monitor_url,
            "ok": False,
            "latency_ms": None,
            "status": "down",
            "checked_at": checked_at,
            "error": f"Host monitor unavailable: {exc}",
            "payload": {},
        }
    except json.JSONDecodeError as exc:
        return {
            "node_id": node.id,
            "label": node.label,
            "monitor_base_url": monitor_url,
            "ok": False,
            "latency_ms": None,
            "status": "down",
            "checked_at": checked_at,
            "error": f"Invalid host monitor JSON: {exc}",
            "payload": {},
        }
    except Exception as exc:
        return {
            "node_id": node.id,
            "label": node.label,
            "monitor_base_url": monitor_url,
            "ok": False,
            "latency_ms": None,
            "status": "down",
            "checked_at": checked_at,
            "error": str(exc),
            "payload": {},
        }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _service_hints(node: RemoteOpsNode) -> dict[str, dict[str, Any]]:
    allowed = [str(v).strip() for v in _jloads_list(node.allowed_services_json) if str(v).strip()]
    hints: dict[str, dict[str, Any]] = {
        "ollama": {"configured": False, "urls": []},
        "comfyui": {"configured": False, "urls": []},
        "comfyui_wrapper": {"configured": False, "urls": []},
        "gpu_audio_wrapper": {"configured": False, "urls": []},
    }

    try:
        notes_obj = json.loads(node.notes) if str(node.notes or "").strip().startswith("{") else {}
    except Exception:
        notes_obj = {}
    notes_obj = notes_obj if isinstance(notes_obj, dict) else {}
    caps = notes_obj.get("capabilities", {}) if isinstance(notes_obj.get("capabilities"), dict) else {}
    endpoints = notes_obj.get("endpoints", {}) if isinstance(notes_obj.get("endpoints"), dict) else {}

    for key in ("ollama", "comfyui", "comfyui_wrapper", "gpu_audio_wrapper"):
        has_flag = caps.get(f"has_{key}")
        if isinstance(has_flag, bool):
            hints[key]["configured"] = has_flag
        endpoint = endpoints.get(key) or notes_obj.get(f"{key}_url")
        if isinstance(endpoint, str) and endpoint.strip():
            hints[key]["urls"].append(endpoint.strip())

    for raw in allowed:
        entry = raw.strip()
        lower = entry.lower()
        if lower in {"ollama", "comfyui", "comfy"}:
            hints["ollama" if lower == "ollama" else "comfyui"]["configured"] = True
            continue
        if lower in {"comfyui_wrapper", "comfy_wrapper"}:
            hints["comfyui_wrapper"]["configured"] = True
            continue
        if lower in {"gpu_audio_wrapper", "audio_wrapper"}:
            hints["gpu_audio_wrapper"]["configured"] = True
            continue
        for key, aliases in (
            ("ollama", ("ollama",)),
            ("comfyui", ("comfyui", "comfy")),
            ("comfyui_wrapper", ("comfyui_wrapper", "comfy_wrapper")),
            ("gpu_audio_wrapper", ("gpu_audio_wrapper", "audio_wrapper")),
        ):
            for alias in aliases:
                pref = f"{alias}="
                pref_alt = f"{alias}:"
                if lower.startswith(pref) or lower.startswith(pref_alt):
                    hints[key]["configured"] = True
                    url = entry.split("=", 1)[1] if "=" in entry else entry.split(":", 1)[1]
                    if url.strip():
                        hints[key]["urls"].append(url.strip())
                    break

    host = _host_for_node(node)
    defaults = {
        "ollama": f"http://{host}:{REMOTE_OLLAMA_DEFAULT_PORT}",
        "comfyui": f"http://{host}:{REMOTE_COMFYUI_DEFAULT_PORT}",
        "comfyui_wrapper": f"http://{host}:8190",
        "gpu_audio_wrapper": f"http://{host}:9910",
    }
    for key in ("ollama", "comfyui", "comfyui_wrapper", "gpu_audio_wrapper"):
        deduped: list[str] = []
        seen: set[str] = set()
        for url in [*hints[key]["urls"], defaults[key]]:
            normalized = str(url).strip().rstrip("/")
            if not normalized:
                continue
            if not normalized.startswith(("http://", "https://")):
                normalized = f"http://{normalized}"
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        hints[key]["urls"] = deduped

    return hints


def _http_get_json(url: str, *, timeout: float = REMOTE_NODE_SERVICE_TIMEOUT_SECONDS) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw) if raw else {}
    return parsed if isinstance(parsed, dict) else {}


def _node_ollama_ps(node: RemoteOpsNode, base_url: str) -> dict[str, Any]:
    try:
        return _runner_client_for_node(node, timeout=REMOTE_NODE_SERVICE_TIMEOUT_SECONDS).host_monitor_ollama_ps(base_url=base_url)
    except Exception:
        return _http_get_json(f"{base_url.rstrip('/')}/api/ps")


def _node_comfyui_queue(node: RemoteOpsNode, base_url: str) -> dict[str, Any]:
    try:
        return _runner_client_for_node(node, timeout=REMOTE_NODE_SERVICE_TIMEOUT_SECONDS).host_monitor_comfyui_queue(base_url=base_url)
    except Exception:
        return _http_get_json(f"{base_url.rstrip('/')}/queue")


def _node_wrapper_health(node: RemoteOpsNode, base_url: str) -> dict[str, Any]:
    try:
        return _runner_client_for_node(node, timeout=REMOTE_NODE_SERVICE_TIMEOUT_SECONDS).host_monitor_wrapper_health(base_url=base_url)
    except Exception:
        return _http_get_json(f"{base_url.rstrip('/')}/health")


def _normalize_ollama_model(row: dict[str, Any]) -> dict[str, Any]:
    details = row.get("details") if isinstance(row.get("details"), dict) else {}
    name = str(row.get("name") or row.get("model") or "").strip()
    return {
        "name": name,
        "model": str(row.get("model") or name),
        "size": _safe_int(row.get("size"), 0) or None,
        "size_vram": _safe_int(row.get("size_vram"), 0) or None,
        "context_length": _safe_int(details.get("context_length"), 0) or None,
        "expires_at": row.get("expires_at"),
    }


def _dedupe_ollama_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for model in models:
        key = "|".join(
            [
                str(model.get("name") or ""),
                str(model.get("model") or ""),
                str(model.get("expires_at") or ""),
                str(model.get("endpoint_url") or ""),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(model)
    return out


def _normalize_comfy_queue(raw: dict[str, Any]) -> tuple[int, int, list[str], list[str]]:
    running = raw.get("queue_running") if isinstance(raw.get("queue_running"), list) else []
    pending = raw.get("queue_pending") if isinstance(raw.get("queue_pending"), list) else []
    if not running and isinstance(raw.get("running"), list):
        running = raw.get("running")  # type: ignore[assignment]
    if not pending and isinstance(raw.get("pending"), list):
        pending = raw.get("pending")  # type: ignore[assignment]

    def _extract_ids(items: list[Any], limit: int = 3) -> list[str]:
        out: list[str] = []
        for item in items[:limit]:
            prompt_id = ""
            if isinstance(item, list) and len(item) >= 2:
                prompt_id = str(item[1] or "").strip()
            elif isinstance(item, dict):
                prompt_id = str(item.get("prompt_id") or item.get("id") or "").strip()
            elif item is not None:
                prompt_id = str(item).strip()
            if prompt_id:
                out.append(prompt_id)
        return out

    running_count = _safe_int(raw.get("running_count"), len(running))
    pending_count = _safe_int(raw.get("pending_count"), len(pending))
    return running_count, pending_count, _extract_ids(running), _extract_ids(pending)


def _normalize_wrapper_health(raw: dict[str, Any]) -> tuple[int, int, int, int | None]:
    queue = raw.get("queue") if isinstance(raw.get("queue"), dict) else {}
    queue_waiting = _safe_int(raw.get("queue_size"), _safe_int(queue.get("jobs_waiting"), 0))
    queue_active = _safe_int(raw.get("active_jobs"), 1 if queue.get("active_job") else 0)
    queued_seconds = _safe_int(queue.get("queued_seconds"), 0)
    max_queue_depth = _safe_int(raw.get("max_queue_depth"), 0) or None
    return queue_waiting, queue_active, queued_seconds, max_queue_depth


def _augment_host_monitor_row(node: RemoteOpsNode, row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    payload = out.get("payload")
    payload = dict(payload) if isinstance(payload, dict) else {}
    legacy_ollama = payload.get("ollama") if isinstance(payload.get("ollama"), dict) else {}
    legacy_comfy = payload.get("comfyui") if isinstance(payload.get("comfyui"), dict) else {}
    legacy_comfy_wrapper = payload.get("comfyui_wrapper") if isinstance(payload.get("comfyui_wrapper"), dict) else {}
    legacy_audio_wrapper = payload.get("gpu_audio_wrapper") if isinstance(payload.get("gpu_audio_wrapper"), dict) else {}
    hints = _service_hints(node)

    ollama_process_count = _safe_int(legacy_ollama.get("process_count"), 0)
    ollama_enabled = bool(legacy_ollama.get("enabled") or legacy_ollama.get("listening_11434") or ollama_process_count > 0)
    should_probe_ollama = bool(hints["ollama"]["configured"] or ollama_enabled)
    ollama_models: list[dict[str, Any]] = []
    ollama_reachable = False
    ollama_error: str | None = None
    ollama_source_url: str | None = None
    ollama_endpoints: list[dict[str, Any]] = []
    if should_probe_ollama:
        for base in hints["ollama"]["urls"]:
            url = f"{base.rstrip('/')}/api/ps"
            try:
                ps_payload = _node_ollama_ps(node, base)
                models = ps_payload.get("models") if isinstance(ps_payload.get("models"), list) else []
                normalized_models = [_normalize_ollama_model(item) for item in models if isinstance(item, dict)]
                for model in normalized_models:
                    model["endpoint_url"] = str(ps_payload.get("source_url") or url)
                ollama_models.extend(normalized_models)
                ollama_reachable = True
                ollama_source_url = ollama_source_url or url
                ollama_endpoints.append(
                    {
                        "url": str(ps_payload.get("source_url") or url),
                        "reachable": True,
                        "model_count": len(normalized_models),
                        "status": "healthy" if normalized_models else "empty",
                        "error": None,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                ollama_error = str(exc)
                ollama_endpoints.append({"url": url, "reachable": False, "model_count": 0, "status": "unreachable", "error": str(exc)})

    ollama_models = _dedupe_ollama_models(ollama_models)

    ollama_model_count = len(ollama_models) if ollama_reachable else _safe_int(legacy_ollama.get("models_count"), 0)
    ollama_status = "disabled"
    if should_probe_ollama:
        if ollama_reachable:
            ollama_status = "healthy" if ollama_model_count > 0 else "empty"
        else:
            # Backward-compat fallback: keep legacy runner health when probing cannot
            # enrich models (for example older runner without proxy endpoint).
            if ollama_enabled and not hints["ollama"]["configured"]:
                ollama_status = str(legacy_ollama.get("status") or "healthy")
                ollama_error = None
            else:
                ollama_status = "unreachable"
    elif legacy_ollama:
        ollama_status = str(legacy_ollama.get("status") or "unknown")

    comfy_enabled = bool(
        legacy_comfy.get("enabled")
        or legacy_comfy.get("listening_8188")
        or _safe_int(legacy_comfy.get("process_count"), 0) > 0
        or str(legacy_comfy.get("status") or "").lower() in {"healthy", "ok", "empty", "degraded"}
    )
    comfy_configured = bool(hints["comfyui"]["configured"] or comfy_enabled)
    should_probe_comfy = comfy_configured
    comfy_reachable = False
    comfy_running = _safe_int(legacy_comfy.get("queue_running"), 0)
    comfy_pending = _safe_int(legacy_comfy.get("queue_pending"), 0)
    comfy_running_items = legacy_comfy.get("running_items") if isinstance(legacy_comfy.get("running_items"), list) else []
    comfy_pending_items = legacy_comfy.get("pending_items") if isinstance(legacy_comfy.get("pending_items"), list) else []
    comfy_error: str | None = None
    comfy_source_url: str | None = None
    if should_probe_comfy:
        for base in hints["comfyui"]["urls"]:
            url = f"{base.rstrip('/')}/queue"
            try:
                queue_payload = _node_comfyui_queue(node, base)
                comfy_running, comfy_pending, comfy_running_items, comfy_pending_items = _normalize_comfy_queue(queue_payload)
                comfy_reachable = True
                comfy_source_url = str(queue_payload.get("source_url") or url)
                comfy_error = None
                break
            except Exception as exc:  # noqa: BLE001
                comfy_error = str(exc)

    def _wrapper_payload(legacy: dict[str, Any], key: str) -> dict[str, Any]:
        configured = bool(hints[key]["configured"] or legacy.get("enabled") or legacy.get("reachable"))
        should_probe = configured
        reachable = bool(legacy.get("reachable"))
        queue_waiting = _safe_int(legacy.get("queue_waiting"), 0)
        queue_active = _safe_int(legacy.get("queue_active"), 0)
        queued_seconds = _safe_int(legacy.get("queued_seconds"), 0)
        max_queue_depth = _safe_int(legacy.get("max_queue_depth"), 0) or None
        source_url = legacy.get("source_url")
        error = str(legacy.get("error") or "") or None
        details = legacy.get("details") if isinstance(legacy.get("details"), dict) else {}
        endpoints = legacy.get("endpoints") if isinstance(legacy.get("endpoints"), list) else []
        if should_probe:
            for base in hints[key]["urls"]:
                url = f"{base.rstrip('/')}/health"
                try:
                    health = _node_wrapper_health(node, base)
                    queue_waiting, queue_active, queued_seconds, max_queue_depth = _normalize_wrapper_health(health)
                    source_url = str(health.get("source_url") or url)
                    details = health
                    endpoints = health.get("endpoints") if isinstance(health.get("endpoints"), list) else endpoints
                    reachable = True
                    error = None
                    break
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)

        status = "disabled"
        if reachable:
            status = "busy" if (queue_waiting + queue_active) > 0 else "ok"
        elif configured:
            status = "unreachable"

        return {
            **legacy,
            "status": status,
            "reachable": reachable,
            "enabled": bool(configured),
            "queue_waiting": queue_waiting,
            "queue_active": queue_active,
            "queued_seconds": queued_seconds,
            "max_queue_depth": max_queue_depth,
            "endpoints": endpoints,
            "source_url": source_url,
            "error": error,
            "details": details,
        }

    comfyui_wrapper = _wrapper_payload(legacy_comfy_wrapper, "comfyui_wrapper")
    gpu_audio_wrapper = _wrapper_payload(legacy_audio_wrapper, "gpu_audio_wrapper")

    comfy_status = "disabled"
    if comfy_reachable:
        comfy_status = "ok" if (comfy_running + comfy_pending) > 0 else "empty"
    elif comfy_configured:
        if comfy_enabled and not hints["comfyui"]["configured"]:
            comfy_status = str(legacy_comfy.get("status") or "healthy")
            comfy_error = None
        else:
            comfy_status = "unreachable"
    else:
        comfy_error = None

    has_gpu = bool(payload.get("gpus")) and isinstance(payload.get("gpus"), list) and len(payload.get("gpus", [])) > 0
    has_ollama = bool(hints["ollama"]["configured"] or ollama_enabled or ollama_reachable)
    has_comfyui = bool(hints["comfyui"]["configured"] or comfy_enabled or comfy_reachable)
    has_comfyui_wrapper = bool(comfyui_wrapper.get("enabled") or comfyui_wrapper.get("reachable"))
    has_gpu_audio_wrapper = bool(gpu_audio_wrapper.get("enabled") or gpu_audio_wrapper.get("reachable"))

    payload["capabilities"] = {
        "has_gpu": has_gpu,
        "has_ollama": has_ollama,
        "has_comfyui": has_comfyui,
        "has_comfyui_wrapper": has_comfyui_wrapper,
        "has_gpu_audio_wrapper": has_gpu_audio_wrapper,
    }
    payload["ollama"] = {
        **legacy_ollama,
        "status": ollama_status,
        "reachable": ollama_reachable,
        "service_present": bool(hints["ollama"]["configured"] or ollama_enabled),
        "service_running": bool(legacy_ollama.get("status") in {"healthy", "degraded"} or ollama_process_count > 0),
        "models": ollama_models,
        "model_count": ollama_model_count,
        "error": ollama_error or (str(legacy_ollama.get("error")) if legacy_ollama.get("error") else None),
        "source_url": ollama_source_url,
        "endpoints": ollama_endpoints,
    }
    payload["comfyui"] = {
        **legacy_comfy,
        "status": comfy_status,
        "reachable": comfy_reachable,
        "queue_running": comfy_running,
        "queue_pending": comfy_pending,
        "running_items": comfy_running_items,
        "pending_items": comfy_pending_items,
        "error": comfy_error or (str(legacy_comfy.get("error")) if legacy_comfy.get("error") else None),
        "source_url": comfy_source_url,
    }
    payload["comfyui_wrapper"] = comfyui_wrapper
    payload["gpu_audio_wrapper"] = gpu_audio_wrapper
    out["payload"] = payload
    return out


def _trim_host_monitor_payload(
    row: dict[str, Any],
    *,
    include_processes: bool,
    include_gpu_processes: bool,
) -> dict[str, Any]:
    out = dict(row)
    payload = out.get("payload")
    if not isinstance(payload, dict):
        return out
    next_payload = dict(payload)
    if not include_processes:
        next_payload.pop("top_processes", None)
    if not include_gpu_processes:
        next_payload.pop("gpu_processes", None)
    out["payload"] = next_payload
    return out


def _node_host_monitor_cached(node: RemoteOpsNode, force: bool = False) -> dict[str, Any]:
    now = time.time()
    cached = _host_monitor_cache.get(node.id)
    if not force and cached and float(cached.get("_cache_until", 0)) > now:
        out = dict(cached)
        out.pop("_cache_until", None)
        return out
    result = _check_node_host_monitor_live(node)
    normalized = _augment_host_monitor_row(node, result)
    cache_row = dict(normalized)
    cache_row["_cache_until"] = now + REMOTE_HOST_MONITOR_TTL_SECONDS
    _host_monitor_cache[node.id] = cache_row
    return normalized


def get_nodes_host_monitor_status(
    session: Session,
    force: bool = False,
    *,
    include_processes: bool = True,
    include_gpu_processes: bool = True,
) -> dict[str, Any]:
    global _host_monitor_cache_all
    now = time.time()
    nodes = session.exec(select(RemoteOpsNode).where(RemoteOpsNode.enabled == True).order_by(RemoteOpsNode.label.asc())).all()  # noqa: E712
    node_by_id = {node.id: node for node in nodes}
    if not force and _host_monitor_cache_all and float(_host_monitor_cache_all.get("_cache_until", 0)) > now:
        cached_out = dict(_host_monitor_cache_all)
        cached_out.pop("_cache_until", None)
        cached_nodes: list[dict[str, Any]] = []
        for row in cached_out.get("nodes", []):
            if not isinstance(row, dict):
                continue
            node_id = str(row.get("node_id") or "")
            node = node_by_id.get(node_id)
            normalized = _augment_host_monitor_row(node, row) if node else row
            cached_nodes.append(
                _trim_host_monitor_payload(
                    normalized,
                    include_processes=include_processes,
                    include_gpu_processes=include_gpu_processes,
                )
            )
        cached_out["nodes"] = cached_nodes
        return cached_out
    full_by_id: dict[str, dict[str, Any]] = {}
    stale_nodes: list[RemoteOpsNode] = []

    for node in nodes:
        if force:
            stale_nodes.append(node)
            continue
        cached = _host_monitor_cache.get(node.id)
        if cached and float(cached.get("_cache_until", 0)) > now:
            out = dict(cached)
            out.pop("_cache_until", None)
            full_by_id[node.id] = _augment_host_monitor_row(node, out)
            continue
        stale_nodes.append(node)

    if stale_nodes:
        workers = max(1, min(REMOTE_CHECK_MAX_WORKERS, len(stale_nodes)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_check_node_host_monitor_live, node): node for node in stale_nodes}
            for future in as_completed(futures):
                node = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    result = {
                        "node_id": node.id,
                        "label": node.label,
                        "monitor_base_url": _host_monitor_base_url(node),
                        "ok": False,
                        "latency_ms": None,
                        "status": "down",
                        "checked_at": _utcnow().isoformat() + "Z",
                        "error": str(exc),
                        "payload": {},
                    }
                normalized = _augment_host_monitor_row(node, result)
                full_by_id[node.id] = normalized
                cache_row = dict(normalized)
                cache_row["_cache_until"] = now + REMOTE_HOST_MONITOR_TTL_SECONDS
                _host_monitor_cache[node.id] = cache_row

    full_results = [
        full_by_id.get(
            node.id,
            {
                "node_id": node.id,
                "label": node.label,
                "monitor_base_url": _host_monitor_base_url(node),
                "ok": False,
                "latency_ms": None,
                "status": "down",
                "checked_at": _utcnow().isoformat() + "Z",
                "error": "missing host monitor result",
                "payload": {},
            },
        )
        for node in nodes
    ]
    seen_any = False
    seen_at = _utcnow()
    for node in nodes:
        row = full_by_id.get(node.id)
        if row and row.get("ok"):
            node.last_seen_at = seen_at
            session.add(node)
            seen_any = True
    if seen_any:
        session.commit()

    results = [
        _trim_host_monitor_payload(
            result,
            include_processes=include_processes,
            include_gpu_processes=include_gpu_processes,
        )
        for result in full_results
    ]
    payload = {"ttl_seconds": REMOTE_HOST_MONITOR_TTL_SECONDS, "nodes": results}
    cached_payload = dict(payload)
    cached_payload["nodes"] = full_results
    cached_payload["_cache_until"] = now + REMOTE_HOST_MONITOR_TTL_SECONDS
    _host_monitor_cache_all = cached_payload
    return payload


def reboot_node_host_monitor(node: RemoteOpsNode, reason: str = "dashburg_remote_ops") -> dict[str, Any]:
    try:
        payload = _runner_client_for_node(node, timeout=REMOTE_HOST_MONITOR_TIMEOUT_SECONDS).host_monitor_reboot(reason=reason)
        payload.setdefault("proxy_ok", True)
        payload.setdefault("proxy_source", f"{node.base_url.rstrip('/')}/v1/host-monitor/reboot")
        return payload
    except Exception:
        # Backward-compatible fallback for legacy nodes still using direct host-monitor daemon.
        payload = _host_monitor_request(node, "/reboot", method="POST", payload={"reason": reason})
        payload.setdefault("proxy_ok", True)
        payload.setdefault("proxy_source", _host_monitor_base_url(node))
        return payload


def _check_node_health_live(node: RemoteOpsNode) -> dict[str, Any]:
    started = time.perf_counter()
    checked_at = _utcnow().isoformat() + "Z"
    try:
        client = _runner_client_for_node(node, timeout=REMOTE_HEALTH_TIMEOUT_SECONDS)
        # Runner client enforces its own timeout; keep classification focused on latency and connectivity.
        client.health()
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "node_id": node.id,
            "ok": True,
            "latency_ms": latency_ms,
            "status": _classify_health(True, latency_ms),
            "checked_at": checked_at,
            "error": None,
        }
    except RunnerClientError as exc:
        return {
            "node_id": node.id,
            "ok": False,
            "latency_ms": None,
            "status": "down",
            "checked_at": checked_at,
            "error": str(exc.detail),
        }
    except Exception as exc:
        return {
            "node_id": node.id,
            "ok": False,
            "latency_ms": None,
            "status": "down",
            "checked_at": checked_at,
            "error": str(exc),
        }


def _node_health_cached(node: RemoteOpsNode, force: bool = False) -> dict[str, Any]:
    now = time.time()
    cached = _health_cache.get(node.id)
    if not force and cached and float(cached.get("_cache_until", 0)) > now:
        out = dict(cached)
        out.pop("_cache_until", None)
        return out

    result = _check_node_health_live(node)
    cache_row = dict(result)
    cache_row["_cache_until"] = now + REMOTE_HEALTH_TTL_SECONDS
    _health_cache[node.id] = cache_row
    return result


def get_node_health_status(session: Session, node: RemoteOpsNode, force: bool = False) -> dict[str, Any]:
    result = _node_health_cached(node, force=force)
    if result.get("ok"):
        node.last_seen_at = _utcnow()
        session.add(node)
        session.commit()
    return result


def get_nodes_health_status(session: Session, force: bool = False) -> dict[str, Any]:
    global _health_cache_all
    now = time.time()
    if not force and _health_cache_all and float(_health_cache_all.get("_cache_until", 0)) > now:
        cached_out = dict(_health_cache_all)
        cached_out.pop("_cache_until", None)
        return cached_out

    nodes = session.exec(select(RemoteOpsNode).order_by(RemoteOpsNode.label.asc())).all()
    by_id: dict[str, dict[str, Any]] = {}
    stale_nodes: list[RemoteOpsNode] = []
    for node in nodes:
        if force:
            stale_nodes.append(node)
            continue
        cached = _health_cache.get(node.id)
        if cached and float(cached.get("_cache_until", 0)) > now:
            out = dict(cached)
            out.pop("_cache_until", None)
            by_id[node.id] = out
            continue
        stale_nodes.append(node)

    if stale_nodes:
        workers = max(1, min(REMOTE_CHECK_MAX_WORKERS, len(stale_nodes)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_check_node_health_live, node): node for node in stale_nodes}
            for future in as_completed(futures):
                node = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    result = {
                        "node_id": node.id,
                        "ok": False,
                        "latency_ms": None,
                        "status": "down",
                        "checked_at": _utcnow().isoformat() + "Z",
                        "error": str(exc),
                    }
                by_id[node.id] = result
                cache_row = dict(result)
                cache_row["_cache_until"] = now + REMOTE_HEALTH_TTL_SECONDS
                _health_cache[node.id] = cache_row

    seen_any = False
    seen_at = _utcnow()
    for node in nodes:
        row = by_id.get(node.id)
        if row and row.get("ok"):
            node.last_seen_at = seen_at
            session.add(node)
            seen_any = True
    if seen_any:
        session.commit()

    results = [
        by_id.get(
            node.id,
            {
                "node_id": node.id,
                "ok": False,
                "latency_ms": None,
                "status": "down",
                "checked_at": _utcnow().isoformat() + "Z",
                "error": "missing health result",
            },
        )
        for node in nodes
    ]
    payload = {"ttl_seconds": REMOTE_HEALTH_TTL_SECONDS, "nodes": results}
    cached_payload = dict(payload)
    cached_payload["_cache_until"] = now + REMOTE_HEALTH_TTL_SECONDS
    _health_cache_all = cached_payload
    return payload


def node_metrics(node: RemoteOpsNode) -> dict[str, Any]:
    return _runner_client_for_node(node).metrics()


def node_services(node: RemoteOpsNode) -> dict[str, Any]:
    return _runner_client_for_node(node).services()


def list_servers_with_status(session: Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in session.exec(select(RemoteOpsNode).order_by(RemoteOpsNode.label.asc())).all():
        try:
            h = node_health(session, node)
        except Exception as exc:
            h = {"status": "offline", "error": str(exc)}
        out.append(
            {
                "id": node.id,
                "label": node.label,
                "base_url": node.base_url,
                "supports_codex": node.supports_codex,
                "supports_terminal": node.supports_terminal,
                "enabled": node.enabled,
                "repos": _jloads_list(node.allowed_repos_json),
                "last_seen_at": node.last_seen_at,
                "status": h.get("status", "unknown"),
                "health": h.get("health", {}),
                "error": h.get("error"),
            }
        )
    return out


def _enforce_job_permissions(settings: RemoteOpsSettings, node: RemoteOpsNode, job_type: str, params: dict[str, Any]) -> None:
    allow_types = _jloads_list(node.allowed_job_types_json)
    if allow_types and job_type not in allow_types:
        # Backward-compatible shortcut: nodes that already allow webagent.run can execute
        # related webagent.* job types (interactive session actions).
        if not (job_type.startswith("webagent.") and "webagent.run" in allow_types):
            raise RemoteOpsError(403, f"Job type {job_type} is not allowed for this node")

    if job_type == "codex.exec" and (not node.supports_codex or not settings.allow_codex_jobs):
        raise RemoteOpsError(403, "Codex jobs are disabled")

    if job_type in {"systemd.restart", "docker.compose.up", "apt.upgrade"} and not settings.allow_system_actions:
        raise RemoteOpsError(403, "System actions are disabled")

    if job_type == "apt.upgrade" and not settings.allow_apt_upgrade:
        raise RemoteOpsError(403, "apt.upgrade disabled in hub settings")

    if job_type == "systemd.restart" and _jloads_list(node.allowed_services_json):
        svc = str(params.get("service_name", ""))
        if svc not in _jloads_list(node.allowed_services_json):
            raise RemoteOpsError(400, "service_name is not allowlisted for node")

    repo = str(params.get("repo_path", "")).strip()
    if repo and _jloads_list(node.allowed_repos_json) and repo not in _jloads_list(node.allowed_repos_json):
        raise RemoteOpsError(400, "repo_path is not allowlisted for node")


def create_remote_job(session: Session, node: RemoteOpsNode, job_type: str, params: dict[str, Any], created_by: str = "ui") -> RemoteOpsJob:
    settings = ensure_settings(session)
    _enforce_job_permissions(settings, node, job_type, params)

    try:
        response = _runner_client_for_node(node).create_job(job_type, params)
    except RunnerClientError as exc:
        raise RemoteOpsError(exc.status, {"message": "Runner request failed", "detail": exc.detail}) from exc

    runner_job_id = str(response.get("job_id") or response.get("id") or "").strip()
    if not runner_job_id:
        raise RemoteOpsError(502, "Runner did not return job id")

    now = _utcnow()
    row = RemoteOpsJob(
        id=uuid.uuid4().hex,
        node_id=node.id,
        runner_job_id=runner_job_id,
        job_type=job_type,
        status=str(response.get("status", "queued")),
        params_json=_jdumps(params),
        result_json=_jdumps(response),
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_remote_jobs(session: Session) -> list[RemoteOpsJob]:
    return list(session.exec(select(RemoteOpsJob).order_by(RemoteOpsJob.created_at.desc())).all())


def get_remote_job(session: Session, job_id: str) -> RemoteOpsJob | None:
    return session.get(RemoteOpsJob, job_id)


def patch_remote_job(session: Session, row: RemoteOpsJob, merged_label: bool | None, archived: bool | None) -> RemoteOpsJob:
    if merged_label is not None:
        row.merged_label = merged_label
    if archived is not None:
        row.archived = archived
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def sync_remote_job_status(session: Session, row: RemoteOpsJob) -> tuple[RemoteOpsJob, dict[str, Any]]:
    node = get_node(session, row.node_id)
    if not node:
        return row, {"error": "node missing"}
    try:
        detail = _runner_client_for_node(node).get_job(row.runner_job_id)
    except RunnerClientError as exc:
        return row, {"error": exc.detail, "status": exc.status}
    except Exception as exc:
        return row, {"error": str(exc)}

    row.status = str(detail.get("status", row.status))
    row.result_json = _jdumps(detail)
    row.updated_at = _utcnow()
    if row.status in {"completed", "failed", "cancelled"} and row.finished_at is None:
        row.finished_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row, detail


def fetch_remote_logs(session: Session, row: RemoteOpsJob, max_lines: int = 200) -> dict[str, Any]:
    node = get_node(session, row.node_id)
    if not node:
        return {"offset": row.log_offset, "lines": [], "error": "node missing"}

    try:
        payload = _runner_client_for_node(node).get_logs(row.runner_job_id, offset=row.log_offset, max_lines=max_lines)
    except RunnerClientError as exc:
        return {"offset": row.log_offset, "lines": [], "error": exc.detail, "status": exc.status}
    except Exception as exc:
        return {"offset": row.log_offset, "lines": [], "error": str(exc)}

    next_offset = int(payload.get("offset", row.log_offset))
    if next_offset > row.log_offset:
        row.log_offset = next_offset
        row.updated_at = _utcnow()
        session.add(row)
        session.commit()
    return payload


def fetch_remote_artifacts(session: Session, row: RemoteOpsJob) -> dict[str, Any]:
    node = get_node(session, row.node_id)
    if not node:
        return {"job_id": row.runner_job_id, "artifact_root": "", "items": [], "error": "node missing"}
    try:
        payload = _runner_client_for_node(node).get_artifacts(row.runner_job_id)
        return payload if isinstance(payload, dict) else {"job_id": row.runner_job_id, "artifact_root": "", "items": []}
    except RunnerClientError as exc:
        return {"job_id": row.runner_job_id, "artifact_root": "", "items": [], "error": exc.detail, "status": exc.status}
    except Exception as exc:
        return {"job_id": row.runner_job_id, "artifact_root": "", "items": [], "error": str(exc)}


def fetch_remote_artifact_content(session: Session, row: RemoteOpsJob, artifact_path: str) -> tuple[bytes | None, str | None]:
    node = get_node(session, row.node_id)
    if not node:
        return None, "node missing"
    try:
        content = _runner_client_for_node(node).get_artifact_content(row.runner_job_id, artifact_path)
        return content, None
    except RunnerClientError as exc:
        return None, str(exc.detail)
    except Exception as exc:
        return None, str(exc)


def job_to_payload(row: RemoteOpsJob) -> dict[str, Any]:
    return {
        "id": row.id,
        "node_id": row.node_id,
        "runner_job_id": row.runner_job_id,
        "job_type": row.job_type,
        "status": row.status,
        "params": _jloads_dict(row.params_json),
        "result": _jloads_dict(row.result_json),
        "created_by": row.created_by,
        "log_offset": row.log_offset,
        "merged_label": row.merged_label,
        "archived": row.archived,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "finished_at": row.finished_at,
    }


def create_terminal_session_row(session: Session, node_id: str, created_by: str = "ui", record_io: bool = False) -> RemoteOpsTerminalSession:
    now = _utcnow()
    row = RemoteOpsTerminalSession(
        id=uuid.uuid4().hex,
        node_id=node_id,
        status="open",
        created_by=created_by,
        record_io=record_io,
        last_activity_at=now,
        created_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_terminal_session_row(session: Session, session_id: str) -> RemoteOpsTerminalSession | None:
    return session.get(RemoteOpsTerminalSession, session_id)


def list_open_terminal_sessions(session: Session) -> list[RemoteOpsTerminalSession]:
    stmt = select(RemoteOpsTerminalSession).where(RemoteOpsTerminalSession.status == "open")
    return list(session.exec(stmt).all())


def close_terminal_session_row(session: Session, row: RemoteOpsTerminalSession) -> RemoteOpsTerminalSession:
    if row.status == "open":
        row.status = "closed"
        row.closed_at = _utcnow()
        row.last_activity_at = _utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def touch_terminal_session_row(session: Session, row: RemoteOpsTerminalSession) -> None:
    row.last_activity_at = _utcnow()
    session.add(row)
    session.commit()


def terminal_session_to_payload(row: RemoteOpsTerminalSession) -> dict[str, Any]:
    return {
        "id": row.id,
        "node_id": row.node_id,
        "status": row.status,
        "created_by": row.created_by,
        "record_io": row.record_io,
        "last_activity_at": row.last_activity_at,
        "created_at": row.created_at,
        "closed_at": row.closed_at,
    }


def build_runner_install_snippet(node: RemoteOpsNode, key_id: str, secret: str) -> dict[str, Any]:
    config_yaml = {
        "host": "0.0.0.0",
        "port": 8844,
        "key_id": key_id,
        "shared_secret": secret,
        "auth_required": True,
        "auth_max_skew_seconds": 60,
        "data_dir": "/var/lib/dashburg-runner",
        "apt_upgrade_enabled": False,
        "codex_enabled": bool(node.supports_codex),
        "allowed_repos": _jloads_list(node.allowed_repos_json),
        "allowed_services": _jloads_list(node.allowed_services_json),
        "allowed_compose_dirs": [],
    }
    runner_install = "\n".join(
        [
            "# on target node",
            "git clone <dashburg-repo-or-runner-package> /opt/dashburg-runner-src",
            "cd /opt/dashburg-runner-src/runner",
            "sudo mkdir -p /etc/dashburg-runner",
            "cat <<'YAML' | sudo tee /etc/dashburg-runner/config.yaml >/dev/null",
            yaml.safe_dump(config_yaml, sort_keys=False).rstrip(),
            "YAML",
            "sudo ./scripts/install_runner.sh",
        ]
    )

    main_install = ""
    if node.supports_terminal:
        main_install = "\n".join(
            [
                "# on main node",
                "cd /opt/dashburg-runner-src/runner",
                "sudo ./scripts/install_dashterm_main.sh --hub-url http://hub.example.local:8431 --token-file /etc/dashburg/remoteops-client-token",
            ]
        )

    return {
        "node_id": node.id,
        "key_id": key_id,
        "secret": secret,
        "config_yaml": yaml.safe_dump(config_yaml, sort_keys=False),
        "install_commands": runner_install,
        "main_terminal_commands": main_install,
    }


def test_node_connection(session: Session, node: RemoteOpsNode) -> dict[str, Any]:
    status = node_health(session, node)
    return {
        "node_id": node.id,
        "status": status.get("status", "unknown"),
        "health": status.get("health", {}),
        "error": status.get("error"),
        "upstream_status": status.get("upstream_status"),
    }


def _extract_host(base_url: str) -> str:
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    return host


def node_ssh_target(node: RemoteOpsNode) -> str:
    host = _extract_host(node.base_url)
    if not host:
        raise RemoteOpsError(400, "Node base_url has no hostname")
    caps = _jloads_dict(getattr(node, "capabilities_json", "{}"))
    per_node_user = str(caps.get("ssh_user", "")).strip() if isinstance(caps, dict) else ""
    ssh_user = (
        per_node_user
        or os.getenv("REMOTEOPS_SSH_USER", "").strip()
        or os.getenv("USER", "").strip()
        or getpass.getuser()
        or "dashterm"
    )
    return f"{ssh_user}@{host}"


def bootstrap_nodes_if_empty(session: Session) -> None:
    existing = session.exec(select(RemoteOpsNode)).first()
    if existing:
        return

    source: Path | None = None
    for candidate in BOOTSTRAP_INVENTORY_PATHS:
        if candidate.exists():
            source = candidate
            break
    if source is None:
        return

    try:
        parsed = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return

    rows = parsed.get("servers", []) if isinstance(parsed, dict) else []
    if not isinstance(rows, list):
        return

    for raw in rows:
        if not isinstance(raw, dict):
            continue
        node_id = _parse_node_id(str(raw.get("id", "")))
        base_url = str(raw.get("base_url", "")).rstrip("/")
        if not node_id or not base_url:
            continue
        if get_node(session, node_id):
            continue

        key_id = str(raw.get("key_id", "")).strip() or _gen_key_id(node_id)
        secret = ""
        secret_env = str(raw.get("secret_env", "")).strip()
        if secret_env:
            secret = str(os.getenv(secret_env, "")).strip()
        if not secret:
            secret = str(raw.get("secret", "")).strip() or _gen_secret()

        now = _utcnow()
        node = RemoteOpsNode(
            id=node_id,
            enabled=True,
            label=str(raw.get("name", node_id)),
            base_url=base_url,
            supports_codex=bool(raw.get("codex_enabled", False)),
            supports_terminal=bool(raw.get("supports_terminal", False)),
            allowed_job_types_json=_jdumps(raw.get("allowed_job_types", [])),
            allowed_repos_json=_jdumps(raw.get("repos", [])),
            allowed_services_json=_jdumps(raw.get("allowed_services", [])),
            notes="imported from bootstrap inventory",
            key_id=key_id,
            created_at=now,
            updated_at=now,
        )
        session.add(node)
        session.add(RemoteOpsNodeKey(node_id=node_id, key_id=key_id, secret_ref=f"secret:{node_id}:{key_id}", created_at=now))
        _set_node_secret(node_id, key_id, secret)

    session.commit()
    ensure_settings(session)
