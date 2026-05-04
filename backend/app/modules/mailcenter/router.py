from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db.session import get_session
from app.modules.mailcenter.service import build_recipients, get_message_detail, get_overview, list_messages, list_threads, send_message

router = APIRouter(prefix="/api/mailcenter", tags=["mailcenter"])


@router.get("/overview")
def mailcenter_overview(session: Session = Depends(get_session)) -> dict:
    return get_overview(session)


@router.get("/messages")
def mailcenter_messages(
    folder: str | None = Query(default="all"),
    status: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    account: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    recipient_node_id: str | None = Query(default=None),
    recipient_agent_slug: str | None = Query(default=None),
    unread_only: bool = Query(default=False),
    q: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict:
    return {
        "items": list_messages(
            session,
            folder=folder,
            status=status,
            direction=direction,
            account=account,
            tag=tag,
            recipient_node_id=recipient_node_id,
            recipient_agent_slug=recipient_agent_slug,
            unread_only=unread_only,
            query=q,
            limit=limit,
        )
    }


@router.get("/recipients")
def mailcenter_recipients(session: Session = Depends(get_session)) -> dict:
    return build_recipients(session)


@router.post("/send")
def mailcenter_send(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        return {"message": send_message(session, payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/messages/{message_id}")
def mailcenter_message_detail(message_id: str, session: Session = Depends(get_session)) -> dict:
    payload = get_message_detail(session, message_id)
    if not payload:
        raise HTTPException(status_code=404, detail="message not found")
    return payload


@router.get("/threads")
def mailcenter_threads(
    folder: str | None = Query(default="all"),
    q: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=300),
    session: Session = Depends(get_session),
) -> dict:
    return {"items": list_threads(session, folder=folder, query=q, limit=limit)}
