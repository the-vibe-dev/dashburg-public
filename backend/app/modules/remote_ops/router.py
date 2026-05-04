from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.db.session import get_session
from app.db.session import engine
from app.modules.remote_ops.service import (
    RemoteOpsError,
    bootstrap_nodes_if_empty,
    build_runner_install_snippet,
    close_terminal_session_row,
    create_node,
    create_remote_job,
    create_terminal_session_row,
    delete_node,
    disable_node_key,
    ensure_settings,
    fetch_remote_logs,
    get_node,
    get_node_health_status,
    get_nodes_host_monitor_status,
    get_nodes_health_status,
    get_remote_job,
    get_terminal_session_row,
    job_to_payload,
    list_nodes,
    list_open_terminal_sessions,
    list_remote_jobs,
    list_servers_with_status,
    node_health,
    node_metrics,
    node_services,
    node_ssh_target,
    node_to_dict,
    patch_remote_job,
    reboot_node_host_monitor,
    rotate_node_key,
    settings_to_dict,
    sync_remote_job_status,
    terminal_session_to_payload,
    test_node_connection,
    touch_terminal_session_row,
    update_node,
    update_settings,
)
from app.modules.remote_ops.terminal import get_terminal_manager
from app.schemas.remote_ops import (
    NodeCreate,
    NodeRotateKeyRequest,
    NodeRotateKeyResponse,
    NodeUpdate,
    RemoteJobCreate,
    RemoteJobPatch,
    RemoteOpsSettingsUpdate,
    TerminalSessionCreate,
    TerminalSessionCreateResponse,
    TerminalKillResponse,
)

router = APIRouter(prefix="/api/remote", tags=["remote-ops"])


def _require_admin(admin_token: str | None = Header(default=None, alias="X-RemoteOps-Admin-Token")) -> None:
    expected = os.getenv("REMOTEOPS_ADMIN_TOKEN", "").strip()
    if not expected:
        return
    if admin_token != expected:
        raise HTTPException(status_code=401, detail="missing or invalid admin token")


def _allow_client_or_admin(
    admin_token: str | None = Header(default=None, alias="X-RemoteOps-Admin-Token"),
    client_token: str | None = Header(default=None, alias="X-RemoteOps-Client-Token"),
    admin_token_q: str | None = Query(default=None, alias="admin_token"),
    client_token_q: str | None = Query(default=None, alias="client_token"),
    session: Session = Depends(get_session),
) -> None:
    expected_admin = os.getenv("REMOTEOPS_ADMIN_TOKEN", "").strip()
    # If admin auth is not configured, keep browser UX open for local/LAN usage.
    # Client token remains useful for helper CLI, but is not mandatory for UI reads/writes.
    if not expected_admin:
        return
    provided_admin = admin_token or admin_token_q
    provided_client = client_token or client_token_q
    if provided_admin == expected_admin:
        return
    settings = ensure_settings(session)
    if settings.client_token and provided_client == settings.client_token:
        return
    raise HTTPException(status_code=401, detail="missing or invalid token")


def _apply_bootstrap(session: Session) -> None:
    bootstrap_nodes_if_empty(session)


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RemoteOpsError):
        return HTTPException(status_code=exc.status, detail=exc.detail)
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/settings")
def get_settings(session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    row = ensure_settings(session)
    get_terminal_manager().configure(idle_timeout_seconds=row.terminal_idle_timeout_minutes * 60)
    return settings_to_dict(row)


@router.put("/settings")
def put_settings(payload: RemoteOpsSettingsUpdate, session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    row = update_settings(session, payload.model_dump())
    get_terminal_manager().configure(idle_timeout_seconds=row.terminal_idle_timeout_minutes * 60)
    return settings_to_dict(row)


@router.get("/nodes")
def get_nodes(session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> list[dict[str, Any]]:
    _apply_bootstrap(session)
    return list_nodes(session)


@router.post("/nodes")
def post_nodes(payload: NodeCreate, session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    try:
        node, secret = create_node(session, payload.model_dump())
    except Exception as exc:
        raise _map_error(exc) from exc

    body = node_to_dict(session, node)
    body["install"] = build_runner_install_snippet(node, node.key_id, secret)
    return body


@router.get("/nodes/health")
def nodes_health(session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    try:
        return get_nodes_health_status(session)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/nodes/host-monitor")
def nodes_host_monitor(
    include_processes: bool = Query(default=True),
    include_gpu_processes: bool = Query(default=True),
    session: Session = Depends(get_session),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    _apply_bootstrap(session)
    try:
        return get_nodes_host_monitor_status(
            session,
            include_processes=include_processes,
            include_gpu_processes=include_gpu_processes,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/nodes/{node_id}")
def get_node_detail(node_id: str, session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    return node_to_dict(session, node)


@router.put("/nodes/{node_id}")
def put_node(node_id: str, payload: NodeUpdate, session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    row = update_node(session, node, payload.model_dump())
    return node_to_dict(session, row)


@router.delete("/nodes/{node_id}")
def delete_node_route(node_id: str, session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    delete_node(session, node)
    return {"ok": True}


@router.post("/nodes/{node_id}/rotate-key", response_model=NodeRotateKeyResponse)
def rotate_key(node_id: str, payload: NodeRotateKeyRequest, session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        _node, key_id, secret = rotate_node_key(session, node, disable_previous=payload.disable_previous)
    except Exception as exc:
        raise _map_error(exc) from exc
    return {"node_id": node_id, "key_id": key_id, "secret": secret}


@router.post("/nodes/{node_id}/disable-key/{key_id}")
def disable_key(node_id: str, key_id: str, session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        disable_node_key(session, node, key_id)
    except Exception as exc:
        raise _map_error(exc) from exc
    return {"ok": True}


@router.get("/nodes/{node_id}/test")
def test_node(node_id: str, session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    return test_node_connection(session, node)


@router.get("/nodes/{node_id}/health")
def node_health_route(node_id: str, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        return get_node_health_status(session, node)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/nodes/{node_id}/host-monitor/reboot")
def node_host_monitor_reboot(
    node_id: str,
    payload: dict[str, Any] | None = None,
    session: Session = Depends(get_session),
    _: None = Depends(_require_admin),
) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    reason = str((payload or {}).get("reason") or "dashburg_remote_ops")
    try:
        return reboot_node_host_monitor(node, reason=reason)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/nodes/{node_id}/metrics")
def node_metrics_route(node_id: str, session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        return node_metrics(node)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/nodes/{node_id}/services")
def node_services_route(node_id: str, session: Session = Depends(get_session), _: None = Depends(_require_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        return node_services(node)
    except Exception as exc:
        raise _map_error(exc) from exc


# Legacy-compatible server endpoints for current UI + helper CLI.
@router.get("/servers")
def get_servers(session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> list[dict[str, Any]]:
    _apply_bootstrap(session)
    try:
        rows = list_servers_with_status(session)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Remote servers listing failed: {exc}") from exc
    return [
        {
            "id": r["id"],
            "name": r["label"],
            "base_url": r["base_url"],
            "codex_enabled": r["supports_codex"],
            "supports_terminal": r["supports_terminal"],
            "enabled": r["enabled"],
            "status": r["status"],
            "health": r.get("health", {}),
            "last_seen_at": r.get("last_seen_at"),
            "tags": [],
            "repos": r.get("repos", []),
        }
        for r in rows
    ]


@router.get("/servers/{server_id}")
def get_server(server_id: str, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, server_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")

    h = node_health(session, node)
    metrics: dict[str, Any] = {}
    services: dict[str, Any] = {}
    if h.get("status") == "online":
        try:
            metrics = node_metrics(node)
            services = node_services(node)
        except Exception:
            pass
    return {
        "server": {
            "id": node.id,
            "name": node.label,
            "base_url": node.base_url,
            "codex_enabled": node.supports_codex,
            "supports_terminal": node.supports_terminal,
            "tags": [],
            "repos": json.loads(node.allowed_repos_json or "[]"),
        },
        "health": h,
        "metrics": metrics,
        "services": services,
    }


@router.post("/servers/{server_id}/jobs")
def post_server_job(server_id: str, payload: RemoteJobCreate, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    node = get_node(session, server_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    try:
        row = create_remote_job(session, node, payload.type, payload.params, created_by="ui")
    except Exception as exc:
        raise _map_error(exc) from exc
    return job_to_payload(row)


@router.get("/jobs")
def get_jobs(session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> list[dict[str, Any]]:
    _apply_bootstrap(session)
    return [job_to_payload(r) for r in list_remote_jobs(session)]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    row = get_remote_job(session, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    row, detail = sync_remote_job_status(session, row)
    body = job_to_payload(row)
    body["runner_detail"] = detail
    return body


@router.patch("/jobs/{job_id}")
def patch_job(job_id: str, payload: RemoteJobPatch, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    row = get_remote_job(session, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    row = patch_remote_job(session, row, payload.merged_label, payload.archived)
    return job_to_payload(row)


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> StreamingResponse:
    _apply_bootstrap(session)
    row = get_remote_job(session, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_stream():
        while True:
            current = get_remote_job(session, job_id)
            if not current:
                yield "event: error\ndata: job_missing\n\n"
                break

            current, detail = sync_remote_job_status(session, current)
            logs = fetch_remote_logs(session, current, max_lines=200)
            for line in logs.get("lines", []) or []:
                payload = json.dumps({"line": str(line), "offset": logs.get("offset", current.log_offset)})
                yield f"event: log\ndata: {payload}\n\n"

            status_payload = json.dumps({"status": current.status, "job": job_to_payload(current), "runner_detail": detail}, default=str)
            yield f"event: status\ndata: {status_payload}\n\n"

            if current.status in {"completed", "failed", "cancelled"}:
                break

            await asyncio.sleep(1.0)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/terminal/sessions", response_model=TerminalSessionCreateResponse)
async def create_terminal_session(
    payload: TerminalSessionCreate,
    session: Session = Depends(get_session),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    _apply_bootstrap(session)
    settings = ensure_settings(session)
    manager = get_terminal_manager()
    manager.configure(idle_timeout_seconds=settings.terminal_idle_timeout_minutes * 60)
    if not settings.terminal_enabled:
        raise HTTPException(status_code=403, detail="terminal is disabled")

    node = get_node(session, payload.node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    if not node.supports_terminal:
        raise HTTPException(status_code=400, detail="node does not support terminal")

    for row in list_open_terminal_sessions(session):
        if not manager.is_open(row.id):
            close_terminal_session_row(session, row)

    if not payload.forceNew:
        existing_sid = manager.find_active_session(node_id=node.id)
        if existing_sid:
            existing_row = get_terminal_session_row(session, existing_sid)
            if existing_row:
                touch_terminal_session_row(session, existing_row)
                return {"session_id": existing_row.id, "session": terminal_session_to_payload(existing_row), "reused": True}

    if manager.active_count() >= settings.terminal_max_sessions:
        await manager.reclaim_oldest()
    if manager.active_count() >= settings.terminal_max_sessions:
        raise HTTPException(status_code=429, detail="terminal_max_sessions exceeded; kill an old session and retry")

    row = create_terminal_session_row(session, node_id=node.id, created_by="ui", record_io=settings.terminal_recording_enabled)
    try:
        await manager.create(row.id, node.id, node_ssh_target(node), cwd=payload.cwd, command=payload.command)
    except Exception as exc:
        close_terminal_session_row(session, row)
        raise HTTPException(status_code=502, detail=f"Failed to create terminal session: {exc}") from exc

    return {"session_id": row.id, "session": terminal_session_to_payload(row), "reused": False}


@router.get("/terminal/sessions/active")
def get_active_terminal_session(
    node_id: str | None = None,
    session: Session = Depends(get_session),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    _apply_bootstrap(session)
    manager = get_terminal_manager()
    settings = ensure_settings(session)
    manager.configure(idle_timeout_seconds=settings.terminal_idle_timeout_minutes * 60)
    sid = manager.find_active_session(node_id=node_id)
    if not sid:
        return {"session_id": None, "session": None}
    row = get_terminal_session_row(session, sid)
    if not row:
        return {"session_id": None, "session": None}
    return {"session_id": row.id, "session": terminal_session_to_payload(row)}


@router.get("/terminal/sessions")
def list_terminal_sessions(session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    manager = get_terminal_manager()
    settings = ensure_settings(session)
    manager.configure(idle_timeout_seconds=settings.terminal_idle_timeout_minutes * 60)
    rows = []
    for row in list_open_terminal_sessions(session):
        rows.append(
            {
                **terminal_session_to_payload(row),
                "runtime_open": manager.is_open(row.id),
            }
        )
    return {
        "items": rows,
        "active_runtime": manager.list_active(),
    }


@router.websocket("/terminal/sessions/{session_id}/ws")
async def terminal_ws(websocket: WebSocket, session_id: str):
    expected_admin = os.getenv("REMOTEOPS_ADMIN_TOKEN", "").strip()
    provided_admin = websocket.query_params.get("admin_token", "")
    provided_client = websocket.query_params.get("client_token", "")
    if expected_admin:
        allow = provided_admin == expected_admin
        if not allow:
            with Session(engine) as db:
                settings = ensure_settings(db)
                allow = bool(settings.client_token and provided_client == settings.client_token)
        if not allow:
            await websocket.close(code=1008)
            return
    await websocket.accept()
    with Session(engine) as db:
        row = get_terminal_session_row(db, session_id)
        if not row:
            await websocket.send_json({"type": "exit", "code": 404})
            await websocket.close(code=1008)
            return
        touch_terminal_session_row(db, row)

    manager = get_terminal_manager()
    if not manager.is_open(session_id):
        restored = False
        with Session(engine) as db:
            row = get_terminal_session_row(db, session_id)
            if row and row.status == "open":
                node = get_node(db, row.node_id)
                if node:
                    restored = await manager.restore(session_id=row.id, node_id=node.id, ssh_target=node_ssh_target(node))
        if not restored:
            await websocket.send_json({"type": "exit", "code": 410})
            await websocket.close(code=1008)
            return

    try:
        await manager.attach(session_id, websocket)
    except WebSocketDisconnect:
        return
    finally:
        with Session(engine) as db:
            row = get_terminal_session_row(db, session_id)
            if row and not manager.is_open(session_id):
                close_terminal_session_row(db, row)


@router.post("/terminal/sessions/{session_id}/kill", response_model=TerminalKillResponse)
async def kill_terminal_session(session_id: str, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    _apply_bootstrap(session)
    row = get_terminal_session_row(session, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="session not found")

    manager = get_terminal_manager()
    ok = await manager.kill(session_id)
    close_terminal_session_row(session, row)
    return {"ok": ok, "session_id": session_id}
