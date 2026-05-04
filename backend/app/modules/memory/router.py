from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlmodel import Session

from app.db.session import get_session
from app.modules.remote_ops.service import ensure_settings as ensure_remote_settings
from app.modules.memory.service import (
    build_memory_brief,
    compact_memory,
    list_candidates,
    list_relationships,
    list_sessions,
    memory_health,
    memory_settings,
    search_memory,
)
from app.schemas.memory import (
    MemoryBriefRequest,
    MemoryBriefResponse,
    MemoryCompactRequest,
    MemoryCompactResponse,
    MemoryHealthResponse,
    MemoryListResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySettingsResponse,
)

router = APIRouter(prefix="/api/memory", tags=["memory"])


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


@router.get("/health", response_model=MemoryHealthResponse)
def get_memory_health(_: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    return memory_health()


@router.get("/settings", response_model=MemorySettingsResponse)
def get_memory_settings(_: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    return memory_settings()


@router.post("/search", response_model=MemorySearchResponse)
def post_memory_search(payload: MemorySearchRequest, _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    return search_memory(payload.model_dump())


@router.post("/brief", response_model=MemoryBriefResponse)
def post_memory_brief(payload: MemoryBriefRequest, _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    return build_memory_brief(payload.model_dump())


@router.get("/sessions", response_model=MemoryListResponse)
def get_memory_sessions(
    limit: int = Query(default=100, ge=1, le=500),
    q: str = Query(default=""),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    return {"items": list_sessions(limit=limit, q=q)}


@router.get("/candidates", response_model=MemoryListResponse)
def get_memory_candidates(
    limit: int = Query(default=100, ge=1, le=500),
    q: str = Query(default=""),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    return {"items": list_candidates(limit=limit, q=q)}


@router.get("/relationships", response_model=MemoryListResponse)
def get_memory_relationships(
    limit: int = Query(default=100, ge=1, le=500),
    q: str = Query(default=""),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    return {"items": list_relationships(limit=limit, q=q)}


@router.post("/compact", response_model=MemoryCompactResponse)
def post_memory_compact(payload: MemoryCompactRequest, _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    return compact_memory(payload.model_dump(), limit=payload.limit, promote=payload.promote)
