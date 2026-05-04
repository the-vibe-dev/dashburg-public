from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlmodel import Session

from app.db.session import get_session
from app.modules.orchestration.service import (
    acknowledge_mailbox_item,
    archive_mailbox_item,
    build_overview,
    cancel_job,
    create_mailbox_note,
    create_job,
    create_jobs,
    ensure_settings,
    get_job,
    get_job_logs,
    get_job_result,
    list_mailbox_items,
    list_jobs,
    orchestration_job_to_payload,
    reconcile_jobs,
    retry_job,
    send_mail_message,
    settings_to_dict,
    terminal_launch_payload,
    update_settings,
)
from app.modules.remote_ops.service import ensure_settings as ensure_remote_settings
from app.schemas.orchestration import (
    OrchestrationJobBatchCreate,
    OrchestrationJobCreate,
    OrchestrationMailSend,
    OrchestrationMailboxCreate,
    OrchestrationSettingsUpdate,
)

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


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


@router.get("/settings")
def get_settings(session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    return settings_to_dict(ensure_settings(session))


@router.put("/settings")
def put_settings(payload: OrchestrationSettingsUpdate, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    return settings_to_dict(update_settings(session, payload.model_dump()))


@router.get("/overview")
def get_overview(session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    return build_overview(session)


@router.get("/nodes")
def get_nodes(session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> list[dict[str, Any]]:
    return build_overview(session)["nodes"]


@router.get("/terminal/launch")
def get_terminal_launch(session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    return terminal_launch_payload(session)


@router.post("/jobs")
def post_job(payload: OrchestrationJobCreate, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    row = create_job(session, payload.model_dump())
    reconcile_jobs(session)
    row = get_job(session, row.id) or row
    return orchestration_job_to_payload(row)


@router.post("/jobs/batch")
def post_jobs(payload: OrchestrationJobBatchCreate, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    rows = create_jobs(session, [row.model_dump() for row in payload.jobs])
    return {"items": [orchestration_job_to_payload(row) for row in rows]}


@router.get("/jobs")
def get_jobs(status: str | None = Query(default=None), session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> list[dict[str, Any]]:
    rows = reconcile_jobs(session)
    if status:
        wanted = {part.strip() for part in status.split(",") if part.strip()}
        rows = [row for row in rows if row.status in wanted]
    return [orchestration_job_to_payload(row) for row in rows]


@router.get("/jobs/{job_id}")
def get_job_detail(job_id: str, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    reconcile_jobs(session)
    row = get_job(session, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return get_job_result(session, row)


@router.post("/jobs/{job_id}/cancel")
def post_cancel(job_id: str, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    row = get_job(session, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    row = cancel_job(session, row)
    return {"ok": True, "job": orchestration_job_to_payload(row)}


@router.post("/jobs/{job_id}/retry")
def post_retry(job_id: str, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    row = get_job(session, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    row = retry_job(session, row)
    return {"ok": True, "job": orchestration_job_to_payload(row)}


@router.get("/jobs/{job_id}/logs")
def get_logs(job_id: str, offset: int = 0, max_lines: int = 200, session: Session = Depends(get_session), _: None = Depends(_allow_client_or_admin)) -> dict[str, Any]:
    row = get_job(session, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return get_job_logs(session, row, offset=offset, max_lines=max_lines)


@router.get("/mailbox")
def get_mailbox(
    node_id: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    return {"items": list_mailbox_items(session, direction=direction, node_id=node_id, job_id=job_id, include_archived=include_archived, limit=limit)}


@router.post("/nodes/{node_id}/mailbox/inbox")
def post_mailbox_note(
    node_id: str,
    payload: OrchestrationMailboxCreate,
    session: Session = Depends(get_session),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    try:
        return create_mailbox_note(session, node_id, payload.model_dump(by_alias=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mail/send")
def post_mail_send(
    payload: OrchestrationMailSend,
    session: Session = Depends(get_session),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    try:
        return {"message": send_mail_message(session, payload.model_dump(by_alias=True))}
    except ValueError as exc:
        code = 404 if "node not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/nodes/{node_id}/mailbox/{item_id}/ack")
def post_mailbox_ack(
    node_id: str,
    item_id: str,
    session: Session = Depends(get_session),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    try:
        return acknowledge_mailbox_item(session, node_id, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/nodes/{node_id}/mailbox/{item_id}/archive")
def post_mailbox_archive(
    node_id: str,
    item_id: str,
    session: Session = Depends(get_session),
    _: None = Depends(_allow_client_or_admin),
) -> dict[str, Any]:
    try:
        return archive_mailbox_item(session, node_id, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
