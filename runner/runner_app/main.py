from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse

from runner_app.auth import verify_signed_request
from runner_app.config import RunnerConfig, load_config
from runner_app.executor import JobExecutor
from runner_app.storage import JobStore

cfg: RunnerConfig = load_config()
store = JobStore(cfg.data_dir)
executor = JobExecutor(cfg, store)

app = FastAPI(title="Dashburg Runner", version="0.1.0")

CRON_LINE_RE = re.compile(r"^[0-9*/,\-]+\s+[0-9*/,\-]+\s+[0-9*/,\-]+\s+[0-9*/,\-]+\s+[0-9*/,\-]+$")
SCHEDULEOPS_CRON_PATH = Path("/etc/cron.d/dashburg-runner-scheduleops")


def _scheduleops_dir() -> Path:
    return Path(cfg.data_dir).expanduser().resolve() / "scheduleops"


def _scheduleops_config_path() -> Path:
    return _scheduleops_dir() / "config.json"


def _scheduleops_rendered_path() -> Path:
    return _scheduleops_dir() / "rendered.cron"


def _runner_home_guess() -> Path:
    # Prefer ~/runner layout, fallback to package-relative path.
    home = Path.home() / "runner"
    if home.exists():
        return home.resolve()
    return Path(__file__).resolve().parents[2]


def _safe_entry_id(value: str) -> str:
    raw = str(value or "").strip().lower()
    safe = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in raw)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")[:80] or "entry"


def _default_schedule_config() -> dict[str, Any]:
    node = str(getattr(cfg, "node_id", "") or socket.gethostname()).strip()
    return {
        "version": 1,
        "node_id": node,
        "timezone": "UTC",
        "notes": "ScheduleOps managed cron entries for runner and agent mailbox dispatch.",
        "entries": [
            {
                "id": "mailbox-runner-hourly",
                "label": "Mailbox Runner Hourly",
                "kind": "mailbox_dispatch",
                "enabled": True,
                "cron": "7 * * * *",
                "recipient_kind": "runner",
                "limit": 200,
            },
            {
                "id": "mailbox-agents-hourly",
                "label": "Mailbox Agents Hourly",
                "kind": "mailbox_dispatch",
                "enabled": True,
                "cron": "11 * * * *",
                "recipient_kind": "agent",
                "limit": 200,
            },
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_schedule_config() -> dict[str, Any]:
    path = _scheduleops_config_path()
    if not path.exists():
        payload = _default_schedule_config()
        _save_schedule_config(payload)
        return payload
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        loaded = _default_schedule_config()
    if not isinstance(loaded, dict):
        loaded = _default_schedule_config()
    loaded.setdefault("version", 1)
    loaded.setdefault("node_id", str(getattr(cfg, "node_id", "") or socket.gethostname()))
    loaded.setdefault("timezone", "UTC")
    loaded.setdefault("notes", "")
    loaded["entries"] = loaded.get("entries") if isinstance(loaded.get("entries"), list) else []
    loaded.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    return loaded


def _save_schedule_config(payload: dict[str, Any]) -> dict[str, Any]:
    data = _default_schedule_config()
    data.update({
        "version": int(payload.get("version") or 1),
        "node_id": str(payload.get("node_id") or data["node_id"]).strip() or data["node_id"],
        "timezone": str(payload.get("timezone") or data["timezone"]).strip() or "UTC",
        "notes": str(payload.get("notes") or ""),
    })
    entries_in = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    entries: list[dict[str, Any]] = []
    for index, row in enumerate(entries_in):
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "mailbox_dispatch").strip().lower()
        cron = str(row.get("cron") or "").strip()
        if not cron or not CRON_LINE_RE.match(cron):
            continue
        recipient_kind = str(row.get("recipient_kind") or "any").strip().lower()
        if recipient_kind not in {"any", "runner", "agent"}:
            recipient_kind = "any"
        entries.append(
            {
                "id": _safe_entry_id(str(row.get("id") or f"entry-{index+1}")),
                "label": str(row.get("label") or f"Entry {index+1}").strip()[:120],
                "kind": kind if kind in {"mailbox_dispatch", "shell_command"} else "mailbox_dispatch",
                "enabled": bool(row.get("enabled", True)),
                "cron": cron,
                "recipient_kind": recipient_kind,
                "recipient": str(row.get("recipient") or "").strip(),
                "limit": max(1, min(int(row.get("limit") or 200), 500)),
                "command": str(row.get("command") or "").strip(),
            }
        )
    data["entries"] = entries
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    out_dir = _scheduleops_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    _scheduleops_config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def _render_schedule_cron(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    runner_home = _runner_home_guess()
    python_bin = runner_home / ".venv" / "bin" / "python"
    worker = runner_home / "scripts" / "mailbox_hourly_worker.py"
    config_path = Path("/etc/dashburg-runner/config.yaml")
    node_id = str(payload.get("node_id") or getattr(cfg, "node_id", "") or socket.gethostname()).strip()
    timezone_name = str(payload.get("timezone") or "UTC").strip() or "UTC"
    lines = [
        "# Dashburg ScheduleOps managed file.",
        "SHELL=/bin/bash",
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"TZ={timezone_name}",
    ]
    warnings: list[str] = []
    for row in payload.get("entries", []):
        if not isinstance(row, dict) or not bool(row.get("enabled")):
            continue
        cron = str(row.get("cron") or "").strip()
        if not CRON_LINE_RE.match(cron):
            warnings.append(f"skip_invalid_cron:{row.get('id')}")
            continue
        kind = str(row.get("kind") or "mailbox_dispatch").strip().lower()
        if kind == "mailbox_dispatch":
            cmd_parts = [
                str(python_bin),
                str(worker),
                "--config",
                str(config_path),
                "--limit",
                str(max(1, min(int(row.get("limit") or 200), 500))),
            ]
            recipient_kind = str(row.get("recipient_kind") or "any").strip().lower()
            if recipient_kind in {"runner", "agent"}:
                cmd_parts.extend(["--recipient-kind", recipient_kind])
            recipient = str(row.get("recipient") or "").strip()
            if recipient:
                cmd_parts.extend(["--recipient", recipient])
            cmd = " ".join(cmd_parts)
        else:
            command = str(row.get("command") or "").strip()
            if not command:
                warnings.append(f"skip_empty_command:{row.get('id')}")
                continue
            cmd = command
        log_name = _safe_entry_id(str(row.get("id") or "entry"))
        log_file = f"/var/log/dashburg-scheduleops-{log_name}.log"
        lines.append(f"{cron} root {cmd} >> {log_file} 2>&1")
    if len(lines) == 4:
        lines.append("# no enabled entries")
    lines.append("")
    # Keep a deterministic rendered file for audit/debug.
    rendered = "\n".join(lines)
    _scheduleops_dir().mkdir(parents=True, exist_ok=True)
    _scheduleops_rendered_path().write_text(rendered, encoding="utf-8")
    return lines, warnings


def _apply_schedule_cron(lines: list[str]) -> dict[str, Any]:
    cron_content = "\n".join(lines)
    tmp = Path("/tmp") / f"dashburg-scheduleops-{int(time.time())}.cron"
    tmp.write_text(cron_content, encoding="utf-8")
    dest = Path("/etc/cron.d/dashburg-runner-scheduleops")
    cmd_install = ["sudo", "-n", "install", "-D", "-m", "644", str(tmp), str(dest)]
    cmd_reload = ["sudo", "-n", "systemctl", "reload", "cron"]
    install_rc = subprocess.run(cmd_install, capture_output=True, text=True, check=False)
    reload_rc = subprocess.run(cmd_reload, capture_output=True, text=True, check=False)
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass
    ok = install_rc.returncode == 0
    return {
        "ok": ok,
        "dest_path": str(dest),
        "install_rc": install_rc.returncode,
        "install_stdout": (install_rc.stdout or "").strip(),
        "install_stderr": (install_rc.stderr or "").strip(),
        "reload_rc": reload_rc.returncode,
        "reload_stdout": (reload_rc.stdout or "").strip(),
        "reload_stderr": (reload_rc.stderr or "").strip(),
    }


def _process_cmdline(proc: psutil.Process) -> str:
    try:
        cmdline = proc.cmdline()
        if cmdline:
            return " ".join(str(part) for part in cmdline if part)
    except Exception:
        pass
    try:
        return str(proc.name() or "")
    except Exception:
        return ""


def _entry_running_pids(entry: dict[str, Any]) -> list[int]:
    kind = str(entry.get("kind") or "mailbox_dispatch").strip().lower()
    command = str(entry.get("command") or "").strip()
    recipient_kind = str(entry.get("recipient_kind") or "").strip().lower()
    recipient = str(entry.get("recipient") or "").strip()
    matches: list[int] = []
    for proc in psutil.process_iter(["pid", "cmdline", "name"]):
        cmd = _process_cmdline(proc).lower()
        if not cmd:
            continue
        is_match = False
        if kind == "mailbox_dispatch":
            if "mailbox_hourly_worker.py" in cmd:
                is_match = True
                if recipient_kind in {"runner", "agent"} and f"--recipient-kind {recipient_kind}" not in cmd:
                    is_match = False
                if recipient and f"--recipient {recipient.lower()}" not in cmd:
                    is_match = False
        elif command and command.lower() in cmd:
            is_match = True
        if is_match:
            try:
                matches.append(int(proc.pid))
            except Exception:
                continue
    return matches


def _entry_log_status(entry_id: str) -> tuple[str, str | None]:
    log_path = f"/var/log/dashburg-scheduleops-{_safe_entry_id(entry_id)}.log"
    path = Path(log_path)
    if not path.exists():
        return log_path, None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        return log_path, mtime
    except Exception:
        return log_path, None


def _schedule_install_status() -> dict[str, Any]:
    out = {
        "path": str(SCHEDULEOPS_CRON_PATH),
        "installed": False,
        "managed_header": False,
        "line_count": 0,
        "error": None,
    }
    try:
        if not SCHEDULEOPS_CRON_PATH.exists():
            return out
        content = SCHEDULEOPS_CRON_PATH.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        out["installed"] = True
        out["line_count"] = len(lines)
        out["managed_header"] = bool(lines and "Dashburg ScheduleOps managed file." in lines[0])
        return out
    except Exception as exc:
        out["error"] = str(exc)
        return out


def _entry_status(entry: dict[str, Any], install_content: str) -> dict[str, Any]:
    entry_id = _safe_entry_id(str(entry.get("id") or "entry"))
    enabled = bool(entry.get("enabled"))
    log_path, last_seen_at = _entry_log_status(entry_id)
    matching_pids = _entry_running_pids(entry) if enabled else []
    installed_line_present = f"dashburg-scheduleops-{entry_id}.log" in install_content
    state = "disabled"
    if enabled:
        if matching_pids:
            state = "running"
        elif last_seen_at:
            state = "idle"
        elif installed_line_present:
            state = "scheduled"
        else:
            state = "missing"
    return {
        "id": entry_id,
        "label": str(entry.get("label") or entry_id),
        "kind": str(entry.get("kind") or "mailbox_dispatch"),
        "enabled": enabled,
        "cron": str(entry.get("cron") or ""),
        "recipient_kind": str(entry.get("recipient_kind") or "any"),
        "recipient": str(entry.get("recipient") or ""),
        "limit": int(entry.get("limit") or 0),
        "command": str(entry.get("command") or ""),
        "log_path": log_path,
        "last_seen_at": last_seen_at,
        "running_now": bool(matching_pids),
        "matching_pids": matching_pids[:8],
        "installed_line_present": installed_line_present,
        "status": state,
    }


def _job_artifact_root(job: dict[str, Any]) -> Path:
    result = json.loads(job.get("result_json") or "{}")
    artifact_dir = result.get("artifact_dir")
    if isinstance(artifact_dir, str) and artifact_dir.strip():
        return Path(artifact_dir).expanduser().resolve()
    if str(job.get("type", "")) == "webagent.run":
        return (Path(cfg.data_dir).expanduser().resolve() / "webagent" / "runs" / str(job.get("id") or ""))
    return Path(cfg.data_dir).expanduser().resolve()


def _relative_files(root: Path, max_files: int = 1000) -> list[dict[str, Any]]:
    if not root.exists() or not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        items.append({"path": rel, "size_bytes": path.stat().st_size})
        if len(items) >= max_files:
            break
    return items


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    body = await request.body()
    try:
        verify_signed_request(request, cfg, body)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    async def _receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(request.scope, _receive)
    return await call_next(request)


@app.get("/v1/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "time": int(time.time()),
        "hostname": os.uname().nodename,
        "codex_enabled": cfg.codex_enabled,
        "codex_installed": shutil.which("codex") is not None,
        "max_concurrent_jobs": cfg.max_concurrent_jobs,
        "roles": cfg.roles,
    }


@app.get("/v1/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        "hostname": os.uname().nodename,
        "roles": cfg.roles,
        "max_concurrency": cfg.max_concurrent_jobs,
        "mailbox": {
            "enabled": True,
            "storage": "sqlite+filesystem",
            "root": str(Path(cfg.data_dir).expanduser().resolve() / "mailbox"),
            "directions": ["inbox", "outbox", "archive"],
        },
        "has_python": shutil.which("python3") is not None,
        "has_node": shutil.which("node") is not None,
        "has_gpu": shutil.which("nvidia-smi") is not None,
        "has_ollama": bool(_run(["bash", "-lc", "ss -ltn | grep -q ':11434' && echo yes || true"], timeout=1.0)),
        "has_comfyui": bool(_run(["bash", "-lc", "ss -ltn | grep -q ':8188' && echo yes || true"], timeout=1.0)),
        **cfg.capabilities,
    }


@app.get("/v1/metrics")
def metrics() -> dict[str, Any]:
    disk = psutil.disk_usage("/")
    out: dict[str, Any] = {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": disk.percent,
        "loadavg": list(os.getloadavg()) if hasattr(os, "getloadavg") else [0, 0, 0],
        "uptime_seconds": int(time.time() - psutil.boot_time()),
    }
    if shutil.which("nvidia-smi"):
        try:
            result = subprocess.check_output(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"], text=True)
            out["gpu"] = [line.strip() for line in result.splitlines() if line.strip()]
        except Exception:
            out["gpu"] = []
    return out


@app.get("/v1/services")
def services() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for svc in cfg.allowed_services:
        state = "unknown"
        try:
            # Some hosts have intermittent systemd/dbus stalls; bound each probe.
            result = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True,
                text=True,
                check=False,
                timeout=2.0,
            )
            state = (result.stdout or result.stderr).strip()
        except subprocess.TimeoutExpired:
            state = "timeout"
        except Exception as exc:
            state = f"error: {exc}"
        rows.append({"name": svc, "state": state})
    return {"items": rows}


def _run(cmd: list[str], timeout: float = 2.0) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        return out.strip()
    except Exception:
        return ""


def _safe_service_base_url(base_url: str | None, default: str) -> str:
    raw = (base_url or default).strip().rstrip("/")
    if not raw:
        raw = default
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="invalid base_url")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="base_url auth is not allowed")
    return raw


def _fetch_json(url: str, timeout: float = 1.5) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            if not isinstance(parsed, dict):
                raise HTTPException(status_code=502, detail="invalid upstream json shape")
            return parsed
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"upstream_unreachable:{exc}") from exc


def _top_processes() -> list[dict[str, Any]]:
    out = _run(["ps", "-eo", "pid,pcpu,pmem,args", "--sort=-pcpu"], timeout=2.0)
    rows = out.splitlines()[1:13]
    data: list[dict[str, Any]] = []
    for row in rows:
        parts = row.strip().split(None, 3)
        if len(parts) < 4:
            continue
        data.append(
            {
                "pid": int(parts[0]),
                "cpu_percent": float(parts[1]),
                "mem_percent": float(parts[2]),
                "command": parts[3][:180],
            }
        )
    return data


def _gpu_status() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    q = "index,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw"
    out = _run(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"], timeout=2.0)
    gpus: list[dict[str, Any]] = []
    for line in out.splitlines():
        cols = [c.strip() for c in line.split(",")]
        if len(cols) != 8:
            continue
        gpus.append(
            {
                "index": int(cols[0] or 0),
                "name": cols[1],
                "util_gpu": float(cols[2] or 0),
                "util_mem": float(cols[3] or 0),
                "memory_used_mib": float(cols[4] or 0),
                "memory_total_mib": float(cols[5] or 0),
                "temperature_c": float(cols[6] or 0),
                "power_w": float(cols[7] or 0),
            }
        )

    pout = _run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_memory,process_name",
            "--format=csv,noheader,nounits",
        ],
        timeout=2.0,
    )
    gpu_procs: list[dict[str, Any]] = []
    for line in pout.splitlines():
        cols = [c.strip() for c in line.split(",")]
        if len(cols) != 3:
            continue
        gpu_procs.append(
            {
                "pid": int(cols[0] or 0),
                "cpu_percent": 0.0,
                "mem_percent": float(cols[1] or 0.0),
                "command": cols[2][:180],
            }
        )
    return gpus, gpu_procs


def _ollama_health() -> dict[str, Any]:
    process_count = 0
    for p in psutil.process_iter(attrs=["name", "cmdline"]):
        try:
            cmdline = " ".join(p.info.get("cmdline") or [])
            if "ollama serve" in cmdline:
                process_count += 1
        except Exception:
            continue

    listening = bool(_run(["bash", "-lc", "ss -ltn | grep -q ':11434' && echo yes || true"], timeout=1.0))
    models_count = 0
    error = ""
    tags_raw = _run(["curl", "-sS", "--max-time", "1.5", "http://127.0.0.1:11434/api/tags"], timeout=2.0)
    if tags_raw:
        try:
            parsed = json.loads(tags_raw)
            models_count = len(parsed.get("models", [])) if isinstance(parsed, dict) else 0
        except Exception as exc:
            error = f"invalid_tags_json:{exc}"
    else:
        error = "tags_unreachable"

    svc_branding = _run(["systemctl", "is-active", "ollama-branding.service"], timeout=1.0)
    svc_translate = _run(["systemctl", "is-active", "ollama-translate.service"], timeout=1.0)
    svc_vision = _run(["systemctl", "is-active", "ollama-vision.service"], timeout=1.0)

    def _svc_exists(state: str) -> bool:
        s = state.strip().lower()
        if not s:
            return False
        if "not-found" in s or "could not be found" in s or "loaded: not-found" in s:
            return False
        return True

    any_ollama_service = _svc_exists(svc_branding) or _svc_exists(svc_translate) or _svc_exists(svc_vision)
    enabled = bool(process_count > 0 or listening or any_ollama_service)
    status = "disabled"
    if enabled:
        status = "healthy"
        if not listening or error or svc_branding not in {"", "active"}:
            status = "degraded"
        if svc_translate not in {"", "active", "inactive"}:
            status = "degraded"
        if svc_vision not in {"", "active", "inactive"}:
            status = "degraded"

    return {
        "enabled": enabled,
        "status": status,
        "process_count": process_count,
        "listening_11434": listening,
        "models_count": models_count,
        "error": error,
        "services": {
            "branding": svc_branding or "unknown",
            "translate": svc_translate or "unknown",
            "vision": svc_vision or "unknown",
        },
    }


def _comfyui_health() -> dict[str, Any]:
    process_count = 0
    for p in psutil.process_iter(attrs=["name", "cmdline"]):
        try:
            cmdline = " ".join(p.info.get("cmdline") or []).lower()
            if "comfyui" in cmdline or "main.py --listen" in cmdline:
                process_count += 1
        except Exception:
            continue
    listening = bool(_run(["bash", "-lc", "ss -ltn | grep -q ':8188' && echo yes || true"], timeout=1.0))
    enabled = bool(process_count > 0 or listening)
    status = "healthy" if enabled else "disabled"
    return {
        "enabled": enabled,
        "status": status,
        "process_count": process_count,
        "listening_8188": listening,
        "error": "",
    }


def _wrapper_health(default_base: str, *, port: int) -> dict[str, Any]:
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    listening = bool(_run(["bash", "-lc", f"ss -ltn | grep -q ':{port}' && echo yes || true"], timeout=1.0))
    base = _safe_service_base_url(None, default_base)
    source_url = f"{base}/health"
    payload: dict[str, Any] = {}
    reachable = False
    error = ""
    try:
        payload = _fetch_json(source_url, timeout=1.8)
        reachable = True
    except HTTPException as exc:
        error = str(exc.detail)

    queue = payload.get("queue") if isinstance(payload.get("queue"), dict) else {}
    queue_waiting = _to_int(payload.get("queue_size"), _to_int(queue.get("jobs_waiting"), 0))
    queue_active = _to_int(payload.get("active_jobs"), 1 if queue.get("active_job") else 0)
    queued_seconds = _to_int(queue.get("queued_seconds"), 0)
    max_queue_depth = payload.get("max_queue_depth")
    max_queue_seconds = queue.get("max_queue_seconds")
    endpoints = payload.get("endpoints") if isinstance(payload.get("endpoints"), list) else []

    enabled = bool(listening or reachable)
    if reachable:
        status = "busy" if (queue_waiting + queue_active) > 0 else "ok"
    elif enabled:
        status = "unreachable"
    else:
        status = "disabled"

    return {
        "enabled": enabled,
        "status": status,
        "reachable": reachable,
        "listening": listening,
        "queue_waiting": queue_waiting,
        "queue_active": queue_active,
        "queued_seconds": queued_seconds,
        "max_queue_depth": max_queue_depth,
        "max_queue_seconds": max_queue_seconds,
        "endpoints": endpoints,
        "source_url": source_url,
        "error": error if error else None,
        "details": payload if payload else {},
    }


def collect_host_monitor_status() -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    load1, load5, load15 = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    gpus, gpu_procs = _gpu_status()
    ollama = _ollama_health()
    comfyui = _comfyui_health()
    comfyui_wrapper = _wrapper_health("http://127.0.0.1:8190", port=8190)
    gpu_audio_wrapper = _wrapper_health("http://127.0.0.1:9910", port=9910)
    top = _top_processes()
    top_snapshot = _run(["bash", "-lc", "top -b -n 1 | head -n 18"], timeout=2.0).splitlines()
    issues: list[str] = []
    if vm.percent > 92:
        issues.append("memory_pressure_high")
    if ollama.get("status") == "degraded":
        issues.append("ollama_degraded")
    health = "healthy" if not issues else "degraded"

    gib = float(1024 ** 3)
    return {
        "ok": True,
        "timestamp": now,
        "host": socket.gethostname(),
        "health": {"status": health, "issues": issues},
        "cpu": {"usage_percent": psutil.cpu_percent(interval=0.2), "load1": load1, "load5": load5, "load15": load15},
        "memory": {"used_gib": vm.used / gib, "total_gib": vm.total / gib, "used_percent": vm.percent},
        "swap": {"used_gib": sm.used / gib, "total_gib": sm.total / gib, "used_percent": sm.percent},
        "disk": {"mount": "/", "used_gib": disk.used / gib, "total_gib": disk.total / gib, "used_percent": disk.percent},
        "ollama": ollama,
        "comfyui": comfyui,
        "comfyui_wrapper": comfyui_wrapper,
        "gpu_audio_wrapper": gpu_audio_wrapper,
        "gpus": gpus,
        "top_processes": top,
        "gpu_processes": gpu_procs,
        "top_snapshot": top_snapshot,
    }


@app.get("/v1/host-monitor/status")
def host_monitor_status() -> dict[str, Any]:
    return collect_host_monitor_status()


@app.get("/v1/host-monitor/ollama/ps")
def host_monitor_ollama_ps(base_url: str | None = Query(default=None)) -> dict[str, Any]:
    base = _safe_service_base_url(base_url, "http://127.0.0.1:11434")
    payload = _fetch_json(f"{base}/api/ps", timeout=1.8)
    payload.setdefault("source_url", f"{base}/api/ps")
    return payload


@app.get("/v1/host-monitor/comfyui/queue")
def host_monitor_comfyui_queue(base_url: str | None = Query(default=None)) -> dict[str, Any]:
    base = _safe_service_base_url(base_url, "http://127.0.0.1:8188")
    payload = _fetch_json(f"{base}/queue", timeout=1.8)
    payload.setdefault("source_url", f"{base}/queue")
    return payload


@app.get("/v1/host-monitor/wrapper/health")
def host_monitor_wrapper_health(base_url: str | None = Query(default=None)) -> dict[str, Any]:
    base = _safe_service_base_url(base_url, "http://127.0.0.1:9910")
    payload = _fetch_json(f"{base}/health", timeout=1.8)
    payload.setdefault("source_url", f"{base}/health")
    return payload


@app.post("/v1/host-monitor/reboot")
def host_monitor_reboot(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    reason = str((payload or {}).get("reason") or "dashburg_remote_ops")
    cmd = ["sudo", "-n", "reboot"]
    try:
        subprocess.Popen(cmd)
        return {"ok": True, "detail": "reboot_requested", "command": " ".join(cmd), "reason": reason}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"reboot_failed:{exc}") from exc


@app.get("/v1/schedules")
def get_schedules() -> dict[str, Any]:
    payload = _load_schedule_config()
    lines, warnings = _render_schedule_cron(payload)
    return {
        "config": payload,
        "rendered": {"lines": lines, "warnings": warnings, "path": str(_scheduleops_rendered_path())},
    }


@app.get("/v1/schedules/status")
def get_schedules_status() -> dict[str, Any]:
    payload = _load_schedule_config()
    install = _schedule_install_status()
    install_content = ""
    if install["installed"]:
        try:
            install_content = SCHEDULEOPS_CRON_PATH.read_text(encoding="utf-8", errors="replace")
        except Exception:
            install_content = ""
    entries_in = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    entries = [_entry_status(row, install_content) for row in entries_in if isinstance(row, dict)]
    return {
        "node_id": str(payload.get("node_id") or getattr(cfg, "node_id", "") or socket.gethostname()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_updated_at": payload.get("updated_at"),
        "install": install,
        "entries": entries,
    }


@app.put("/v1/schedules")
def put_schedules(payload: dict[str, Any]) -> dict[str, Any]:
    saved = _save_schedule_config(payload if isinstance(payload, dict) else {})
    lines, warnings = _render_schedule_cron(saved)
    return {
        "config": saved,
        "rendered": {"lines": lines, "warnings": warnings, "path": str(_scheduleops_rendered_path())},
    }


@app.post("/v1/schedules/apply")
def apply_schedules(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    _ = payload
    cfg_payload = _load_schedule_config()
    lines, warnings = _render_schedule_cron(cfg_payload)
    result = _apply_schedule_cron(lines)
    return {
        "config": cfg_payload,
        "rendered": {"lines": lines, "warnings": warnings, "path": str(_scheduleops_rendered_path())},
        "apply": result,
    }


@app.post("/v1/jobs")
def create_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_type = str(payload.get("type", "")).strip()
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="params must be an object")
    try:
        return executor.submit(job_type, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/jobs")
def list_jobs(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    return {"items": store.list_recent_jobs(limit=limit)}


@app.get("/v1/jobs/{job_id}")
def job_detail(job_id: str) -> dict[str, Any]:
    row = store.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    row["params"] = json.loads(row.get("params_json") or "{}")
    row["result"] = json.loads(row.get("result_json") or "{}")
    return row


@app.post("/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    row = executor.cancel(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    row["params"] = json.loads(row.get("params_json") or "{}")
    row["result"] = json.loads(row.get("result_json") or "{}")
    return row


@app.get("/v1/jobs/{job_id}/artifacts")
def job_artifacts(job_id: str) -> dict[str, Any]:
    row = store.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    root = _job_artifact_root(row)
    return {
        "job_id": job_id,
        "artifact_root": str(root),
        "items": _relative_files(root),
    }


@app.get("/v1/jobs/{job_id}/artifacts/content")
def job_artifact_content(job_id: str, path: str = Query(min_length=1)) -> FileResponse:
    row = store.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    root = _job_artifact_root(row)
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid artifact path") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    media_type, _ = mimetypes.guess_type(str(candidate))
    return FileResponse(path=str(candidate), media_type=media_type or "application/octet-stream", filename=candidate.name)


@app.get("/v1/jobs/{job_id}/logs")
async def job_logs(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    max_lines: int = Query(default=200, ge=1, le=1000),
    stream: bool = Query(default=False),
):
    if not store.get_job(job_id):
        raise HTTPException(status_code=404, detail="job not found")

    if not stream:
        return store.get_logs(job_id, offset=offset, max_lines=max_lines)

    async def event_stream():
        current = offset
        while True:
            payload = store.get_logs(job_id, offset=current, max_lines=max_lines)
            current = int(payload.get("offset", current))
            for line in payload.get("lines", []):
                yield f"event: log\ndata: {json.dumps({'line': line, 'offset': current})}\n\n"

            detail = store.get_job(job_id) or {}
            yield f"event: status\ndata: {json.dumps({'status': detail.get('status', 'unknown')})}\n\n"
            if detail.get("status") in {"completed", "failed", "cancelled", "canceled"}:
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/v1/mailbox/inbox")
def mailbox_inbox(
    limit: int = Query(default=100, ge=1, le=500),
    include_archived: bool = Query(default=False),
    job_id: str | None = Query(default=None),
) -> dict[str, Any]:
    return {"items": store.list_mailbox_items(direction="inbox", include_archived=include_archived, job_id=job_id, limit=limit)}


@app.get("/v1/mailbox/outbox")
def mailbox_outbox(
    limit: int = Query(default=100, ge=1, le=500),
    include_archived: bool = Query(default=False),
    job_id: str | None = Query(default=None),
) -> dict[str, Any]:
    return {"items": store.list_mailbox_items(direction="outbox", include_archived=include_archived, job_id=job_id, limit=limit)}


@app.get("/v1/mailbox/archive")
def mailbox_archive(limit: int = Query(default=100, ge=1, le=500), job_id: str | None = Query(default=None)) -> dict[str, Any]:
    return {"items": store.list_mailbox_items(include_archived=True, job_id=job_id, limit=limit)}


@app.get("/v1/mailbox/{item_id}")
def mailbox_item_detail(item_id: str) -> dict[str, Any]:
    item = store.get_mailbox_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="mailbox item not found")
    return item


@app.post("/v1/mailbox/inbox")
def create_mailbox_inbox_item(payload: dict[str, Any]) -> dict[str, Any]:
    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not subject:
        raise HTTPException(status_code=400, detail="subject is required")
    if not body:
        raise HTTPException(status_code=400, detail="body is required")
    item = store.create_mailbox_item(
        item_id=os.urandom(16).hex(),
        node_id=os.uname().nodename,
        direction="inbox",
        msg_type=str(payload.get("type") or "note").strip() or "note",
        subject=subject,
        body=body,
        job_id=str(payload.get("job_id") or "").strip(),
        run_id=str(payload.get("run_id") or "").strip(),
        severity=str(payload.get("severity") or "info").strip() or "info",
        status="new",
        sender=str(payload.get("from") or "dashburg-operator").strip() or "dashburg-operator",
        recipient=str(payload.get("to") or f"runner@{os.uname().nodename}").strip() or f"runner@{os.uname().nodename}",
        attachments=payload.get("attachments") if isinstance(payload.get("attachments"), list) else [],
        tags=[str(tag) for tag in payload.get("tags", [])] if isinstance(payload.get("tags"), list) else [],
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        now_iso=datetime.now(timezone.utc).isoformat(),
    )
    return item


@app.post("/v1/mailbox/{item_id}/ack")
def acknowledge_mailbox_item(item_id: str) -> dict[str, Any]:
    item = store.acknowledge_mailbox_item(item_id, datetime.now(timezone.utc).isoformat())
    if not item:
        raise HTTPException(status_code=404, detail="mailbox item not found")
    return item


@app.post("/v1/mailbox/{item_id}/archive")
def archive_mailbox_item(item_id: str) -> dict[str, Any]:
    item = store.archive_mailbox_item(item_id, datetime.now(timezone.utc).isoformat())
    if not item:
        raise HTTPException(status_code=404, detail="mailbox item not found")
    return item
