from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.db.session import get_session
from app.models.localops import LocalOpsRun, LocalOpsThread
from app.modules.localops.service import (
    _now,
    _as_int_or_none,
    _normalize_provider_id,
    approve_tool_call_and_continue,
    cancel_run,
    create_message,
    create_or_update_agent_pack,
    create_provider,
    create_run,
    create_thread,
    delete_thread,
    delete_provider,
    ensure_dirs,
    ensure_settings,
    get_run,
    get_thread,
    list_openai_models,
    list_ollama_models,
    list_providers,
    list_threads,
    openai_api_key_status,
    set_openai_api_key,
    clear_openai_api_key,
    provider_to_dict,
    run_broker,
    run_tool_calls,
    settings_to_dict,
    start_run_task,
    test_ollama,
    thread_messages,
    update_provider,
    update_settings,
    list_agent_packs,
    list_agent_sessions,
    create_agent_session,
    get_agent_session,
    run_agent_session,
    update_agent_session,
    read_agent_session_file,
    write_agent_session_file,
)
from app.modules.localops.memory import ensure_localops_mem_file
from app.modules.localops.terminal import get_local_terminal_manager
from app.schemas.localops import (
    LocalOpsAgentSessionCreateRequest,
    LocalOpsAgentSessionUpdateRequest,
    LocalOpsAgentPackUpsertRequest,
    LocalOpsAgentSessionRunRequest,
    LocalOpsAgentFileWriteRequest,
    LocalOpsApproveToolRequest,
    LocalOpsTerminalCreateRequest,
    OpenAiApiKeyStatus,
    LocalOpsPostMessage,
    LocalOpsProviderCreate,
    LocalOpsProviderUpdate,
    LocalOpsSettingsUpdate,
    LocalOpsThreadCreate,
    OllamaTestRequest,
)

router = APIRouter(prefix="/api/localops", tags=["localops"])


def _require_localops_token(
    request: Request,
    token: str | None = Header(default=None, alias="X-LocalOps-Token"),
    token_qs: str | None = Query(default=None, alias="token"),
) -> None:
    expected = str(os.getenv("LOCALOPS_ADMIN_TOKEN", "")).strip()
    if not expected:
        return
    supplied = token or token_qs or request.query_params.get("localops_token")
    if supplied != expected:
        raise HTTPException(status_code=401, detail="missing or invalid localops token")


@router.get("/settings")
def get_localops_settings(session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    ensure_dirs()
    row = ensure_settings(session)
    get_local_terminal_manager().configure(idle_timeout_seconds=row.terminal_idle_timeout_minutes * 60)
    return settings_to_dict(row)


@router.put("/settings")
def put_localops_settings(payload: LocalOpsSettingsUpdate, session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    row = update_settings(session, payload.model_dump())
    get_local_terminal_manager().configure(idle_timeout_seconds=row.terminal_idle_timeout_minutes * 60)
    return settings_to_dict(row)


@router.get("/providers")
def get_providers(session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return {"providers": list_providers(session)}


@router.post("/providers")
def post_provider(payload: LocalOpsProviderCreate, session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return create_provider(session, payload.model_dump())


@router.put("/providers/{provider_id}")
def put_provider(provider_id: int, payload: LocalOpsProviderUpdate, session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return update_provider(session, provider_id, payload.model_dump())


@router.delete("/providers/{provider_id}")
def del_provider(provider_id: int, session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    delete_provider(session, provider_id)
    return {"ok": True}


@router.post("/providers/ollama/test")
def post_ollama_test(payload: OllamaTestRequest, _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    try:
        return test_ollama(payload.base_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ollama test failed: {exc}") from exc


@router.get("/providers/ollama/models")
def get_ollama_models(base_url: str = Query(...), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    try:
        return {"models": list_ollama_models(base_url)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ollama models failed: {exc}") from exc


@router.get("/providers/openai/models")
def get_openai_models(_: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return {"models": list_openai_models()}


@router.get("/openai/key/status", response_model=OpenAiApiKeyStatus)
def openai_key_status(_: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return openai_api_key_status()


@router.post("/openai/key")
def openai_key_set(payload: dict[str, Any], _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return set_openai_api_key(str(payload.get("api_key", "")))


@router.post("/openai/key/clear")
def openai_key_clear(_: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return clear_openai_api_key()


@router.get("/chat-ui/config")
def chat_ui_config(_: None = Depends(_require_localops_token)) -> dict[str, Any]:
    url = str(os.getenv("LOCALOPS_CHAT_UI_URL", "")).strip()
    return {"enabled": bool(url), "url": url}


@router.post("/memory/refresh")
def refresh_localops_memory(session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    path = ensure_localops_mem_file(session)
    return {"ok": True, "path": path}


@router.post("/threads")
def post_thread(payload: LocalOpsThreadCreate, session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    row = create_thread(session, payload.model_dump())
    return row.model_dump()


@router.get("/threads")
def get_threads(session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return {"threads": [t.model_dump() for t in list_threads(session)]}


@router.delete("/threads/{thread_id}")
def delete_thread_route(thread_id: str, session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    ok = delete_thread(session, thread_id)
    if not ok:
        raise HTTPException(status_code=404, detail="thread not found")
    return {"ok": True}


@router.get("/threads/{thread_id}")
def get_thread_detail(thread_id: str, session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    thread = get_thread(session, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="thread not found")
    messages = thread_messages(session, thread_id)
    return {
        "thread": thread.model_dump(),
        "messages": [
            {
                **m.model_dump(),
                "meta": json.loads(m.meta_json or "{}"),
            }
            for m in messages
        ],
    }


@router.post("/threads/{thread_id}/messages")
async def post_message(thread_id: str, payload: LocalOpsPostMessage, session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    thread = get_thread(session, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="thread not found")
    thread.provider_id = payload.provider_id
    thread.provider_id = _normalize_provider_id(thread.provider_id)
    thread.provider_endpoint_id = _as_int_or_none(payload.provider_endpoint_id)
    thread.model = payload.model
    thread.execution_mode = payload.execution_mode
    thread.updated_at = _now()
    session.add(thread)
    session.commit()

    run = create_run(session, thread, payload.model_dump())
    create_message(session, thread_id, run.id, "user", payload.content, {})
    start_run_task(run.id)
    return {"run_id": run.id}


@router.get("/runs/{run_id}")
def get_run_detail(run_id: str, session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    run = get_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    tc = run_tool_calls(session, run_id)
    return {
        "run": {
            **run.model_dump(),
            "telemetry": json.loads(run.telemetry_json or "{}"),
        },
        "tool_calls": [
            {
                **row.model_dump(),
                "args": json.loads(row.args_json or "{}"),
                "result": json.loads(row.result_json or "{}"),
            }
            for row in tc
        ],
    }


@router.get("/runs/{run_id}/stream")
async def run_stream(run_id: str, request: Request, _: None = Depends(_require_localops_token)) -> StreamingResponse:
    async def event_generator():
        async for chunk in run_broker.stream(run_id):
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/runs/{run_id}/cancel")
def cancel_run_route(run_id: str, session: Session = Depends(get_session), _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    row = session.get(LocalOpsRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    canceled = cancel_run(run_id)
    row.status = "canceled"
    row.llm_status = "cancelled"
    row.finished_at = row.finished_at or _now()
    row.updated_at = _now()
    session.add(row)
    session.commit()
    return {"ok": True, "canceled": canceled}


@router.post("/runs/{run_id}/approveToolCall")
async def approve_tool(run_id: str, payload: LocalOpsApproveToolRequest, _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return await approve_tool_call_and_continue(run_id, payload.tool_call_id)


@router.get("/agents/packs")
def get_agent_packs(_: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return {"agents": list_agent_packs()}


@router.post("/agents/packs")
def upsert_agent_pack(payload: LocalOpsAgentPackUpsertRequest, _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return create_or_update_agent_pack(
        slug=payload.slug,
        title=payload.title,
        instructions=payload.instructions,
        tooling=payload.tooling,
        skill_md=payload.skill_md,
    )


@router.get("/agents/sessions")
def get_agent_sessions(_: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return {"sessions": list_agent_sessions()}


@router.post("/agents/sessions")
def post_agent_session(payload: LocalOpsAgentSessionCreateRequest, _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    session = create_agent_session(
        payload.agent_slug,
        title=payload.title,
        seed_markdown=payload.seed_markdown,
        agent_name=payload.agent_name,
        workspace_root=payload.workspace_root,
        codex_model=payload.codex_model,
    )
    updates = {
        "target_node_id": payload.target_node_id,
        "target_repo_path": payload.target_repo_path,
        "target_repo_purpose": payload.target_repo_purpose,
    }
    if any(str(v or "").strip() for v in updates.values()):
        session = update_agent_session(session["id"], updates)
    return session


@router.get("/agents/sessions/{session_id}")
def get_agent_session_detail(session_id: str, _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    return get_agent_session(session_id)


@router.put("/agents/sessions/{session_id}")
def put_agent_session_detail(
    session_id: str,
    payload: LocalOpsAgentSessionUpdateRequest,
    _: None = Depends(_require_localops_token),
) -> dict[str, Any]:
    return update_agent_session(session_id, payload.model_dump(exclude_unset=True))


@router.post("/agents/sessions/{session_id}/run")
def run_agent_session_route(
    session_id: str,
    payload: LocalOpsAgentSessionRunRequest,
    _: None = Depends(_require_localops_token),
) -> dict[str, Any]:
    return run_agent_session(session_id, task=payload.task, sandbox_mode=payload.sandbox_mode, timeout_s=payload.timeout_s)


@router.get("/agents/sessions/{session_id}/files/{file_key}")
def get_agent_session_file(
    session_id: str,
    file_key: str,
    _: None = Depends(_require_localops_token),
) -> dict[str, Any]:
    return read_agent_session_file(session_id, file_key)


@router.put("/agents/sessions/{session_id}/files/{file_key}")
def put_agent_session_file(
    session_id: str,
    file_key: str,
    payload: LocalOpsAgentFileWriteRequest,
    _: None = Depends(_require_localops_token),
) -> dict[str, Any]:
    return write_agent_session_file(session_id, file_key, payload.content)


@router.get("/terminal/sessions/active")
def get_active_local_terminal_session(_: None = Depends(_require_localops_token)) -> dict[str, Any]:
    manager = get_local_terminal_manager()
    sid = manager.find_active_session()
    if not sid:
        return {"session_id": None}
    return {"session_id": sid, "session": manager.session_payload(sid)}


@router.post("/terminal/sessions")
async def post_local_terminal_session(
    payload: LocalOpsTerminalCreateRequest,
    session: Session = Depends(get_session),
    _: None = Depends(_require_localops_token),
) -> dict[str, Any]:
    ensure_localops_mem_file(session)
    settings = ensure_settings(session)
    get_local_terminal_manager().configure(idle_timeout_seconds=settings.terminal_idle_timeout_minutes * 60)
    manager = get_local_terminal_manager()
    if not payload.force_new:
        existing = manager.find_active_session()
        if existing:
            return {"session_id": existing, "reused": True, "session": manager.session_payload(existing)}
    session_id = os.urandom(12).hex()
    await manager.create(session_id=session_id, cwd=payload.cwd, command=payload.command)
    return {"session_id": session_id, "reused": False, "session": manager.session_payload(session_id)}


@router.post("/terminal/sessions/{session_id}/kill")
async def kill_local_terminal_session(session_id: str, _: None = Depends(_require_localops_token)) -> dict[str, Any]:
    manager = get_local_terminal_manager()
    ok = await manager.kill(session_id)
    return {"ok": ok, "session_id": session_id}


@router.websocket("/terminal/sessions/{session_id}/ws")
async def local_terminal_ws(websocket: WebSocket, session_id: str) -> None:
    expected = str(os.getenv("LOCALOPS_ADMIN_TOKEN", "")).strip()
    supplied = (
        websocket.headers.get("x-localops-token")
        or websocket.query_params.get("token")
        or websocket.query_params.get("localops_token")
        or ""
    )
    if expected and supplied != expected:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    manager = get_local_terminal_manager()
    await manager.attach(session_id, websocket)
