from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.db.session import get_session
from app.modules.chat.service import (
    append_message,
    attach_discord,
    create_session,
    get_chat_session,
    list_messages,
    list_sessions,
    stream_assistant_reply,
    sync_messages,
)
from app.modules.remote_ops.service import ensure_settings as ensure_remote_settings
from app.schemas.chat import (
    ChatMessageCreateRequest,
    ChatSessionAttachDiscordRequest,
    ChatSessionCreateRequest,
    ChatSessionSyncRequest,
    ChatStreamRequest,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _allow_client_or_admin(
    admin_token: str | None = Header(default=None, alias="X-RemoteOps-Admin-Token"),
    client_token: str | None = Header(default=None, alias="X-RemoteOps-Client-Token"),
    admin_token_q: str | None = Query(default=None, alias="admin_token"),
    client_token_q: str | None = Query(default=None, alias="client_token"),
    session: Session = Depends(get_session),
) -> None:
    expected_admin = os.getenv("REMOTEOPS_ADMIN_TOKEN", "").strip()
    if not expected_admin:
        return
    provided_admin = admin_token or admin_token_q
    provided_client = client_token or client_token_q
    if provided_admin == expected_admin:
        return
    remote_settings = ensure_remote_settings(session)
    if remote_settings.client_token and provided_client == remote_settings.client_token:
        return
    raise HTTPException(status_code=401, detail="missing or invalid token")


@router.get("/sessions")
def get_chat_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    return list_sessions(limit=limit)


@router.post("/sessions")
def post_chat_session(
    payload: ChatSessionCreateRequest,
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    return create_session(payload.model_dump())


@router.get("/sessions/{session_id}")
def get_chat_session_detail(session_id: str, _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    return get_chat_session(session_id)


@router.get("/sessions/{session_id}/messages")
def get_chat_session_messages(
    session_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    return list_messages(session_id, limit=limit)


@router.post("/sessions/{session_id}/messages")
def post_chat_message(
    session_id: str,
    payload: ChatMessageCreateRequest,
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    return append_message(session_id, payload.model_dump())


@router.post("/sessions/{session_id}/stream")
async def post_chat_stream(
    session_id: str,
    payload: ChatStreamRequest,
    session: Session = Depends(get_session),
    _: None = Depends(_allow_client_or_admin),
) -> StreamingResponse:
    async def event_stream():
        async for chunk in stream_assistant_reply(session, session_id, payload.model_dump()):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/attach-discord")
def post_chat_attach_discord(
    session_id: str,
    payload: ChatSessionAttachDiscordRequest,
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    return attach_discord(session_id, payload.model_dump())


@router.post("/sessions/{session_id}/sync")
def post_chat_sync(
    session_id: str,
    payload: ChatSessionSyncRequest,
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    return sync_messages(session_id, payload.model_dump())
