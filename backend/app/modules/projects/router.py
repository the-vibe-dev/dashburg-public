from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.project import Project
from app.schemas.projects import (
    ProjectCreate,
    ProjectDashboardRead,
    ProjectPage,
    ProjectRead,
    ProjectReorderRequest,
    ProjectTopTask,
    ProjectUpdate,
    ProjectWorkspace,
    ProjectWorkspacePutRequest,
    TaskPatchRequest,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])
tasks_router = APIRouter(prefix="/api/projects/tasks", tags=["projects"])
legacy_tasks_router = APIRouter(prefix="/api/tasks", tags=["projects"])


def _now() -> datetime:
    return datetime.utcnow()


def _parse_blocks(project: Project) -> list[dict[str, Any]]:
    try:
        blocks = json.loads(project.page_blocks or "[]")
    except json.JSONDecodeError:
        blocks = []
    return blocks if isinstance(blocks, list) else []


def _write_blocks(project: Project, blocks: list[dict[str, Any]]) -> None:
    project.page_blocks = json.dumps(blocks)
    project.updated_at = _now()


def _require_project(session: Session, project_id: int) -> Project:
    row = session.get(Project, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


def _priority_value(project: Project) -> int:
    return project.priority_rank if project.priority_rank is not None else 10_000_000


def _priority_sort_key(project: Project) -> tuple[int, datetime]:
    return (_priority_value(project), project.created_at)


def _normalize_priority_ranks(session: Session) -> None:
    rows = list(session.exec(select(Project)).all())
    changed = False
    for idx, row in enumerate(sorted(rows, key=_priority_sort_key)):
        if row.priority_rank != idx:
            row.priority_rank = idx
            row.updated_at = _now()
            session.add(row)
            changed = True
    if changed:
        session.commit()


def _task_priority_rank(priority: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(priority or "medium"), 4)


def _project_top_tasks(project: Project, limit: int = 3) -> list[ProjectTopTask]:
    tasks = [
        block
        for block in _parse_blocks(project)
        if isinstance(block, dict) and block.get("type") == "task" and str(block.get("status", "todo")) != "done"
    ]
    tasks.sort(key=lambda task: (_task_priority_rank(str(task.get("priority", "medium"))), str(task.get("created_at", ""))))
    return [
        ProjectTopTask(
            id=str(task.get("id", "")),
            content=str(task.get("content", "")),
            status=str(task.get("status", "todo")),
            priority=str(task.get("priority", "medium")),
            created_at=str(task.get("created_at", "")),
        )
        for task in tasks[: max(1, limit)]
    ]


def _project_notes_preview(project: Project, limit_chars: int = 180) -> str:
    notes = [
        str(block.get("content", "")).strip()
        for block in _parse_blocks(project)
        if isinstance(block, dict) and block.get("type") in {"note", "heading"} and str(block.get("content", "")).strip()
    ]
    text = " ".join(notes).strip()
    return text if len(text) <= limit_chars else text[:limit_chars].rstrip() + "..."


def _project_read(project: Project) -> ProjectRead:
    return ProjectRead.model_validate(project.model_dump())


def _project_dashboard_read(project: Project) -> ProjectDashboardRead:
    base = project.model_dump()
    base["notes_preview"] = _project_notes_preview(project)
    base["top_tasks"] = [task.model_dump() for task in _project_top_tasks(project)]
    return ProjectDashboardRead.model_validate(base)


@router.get("")
def list_projects(
    order: str = Query(default="priority"),
    limit: int | None = Query(default=None, ge=1, le=500),
    include_top_tasks: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = list(session.exec(select(Project)).all())
    if order == "priority":
        rows.sort(key=_priority_sort_key)
    else:
        rows.sort(key=lambda row: row.updated_at, reverse=True)
    if limit is not None:
        rows = rows[:limit]
    if include_top_tasks:
        return [_project_dashboard_read(row).model_dump() for row in rows]
    return [_project_read(row).model_dump() for row in rows]


@router.post("", response_model=ProjectRead)
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)) -> ProjectRead:
    row = Project(title=payload.title.strip(), description=payload.description.strip(), created_at=_now(), updated_at=_now())
    session.add(row)
    session.commit()
    session.refresh(row)
    _normalize_priority_ranks(session)
    session.refresh(row)
    return _project_read(row)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, session: Session = Depends(get_session)) -> ProjectRead:
    return _project_read(_require_project(session, project_id))


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, session: Session = Depends(get_session)) -> ProjectRead:
    row = _require_project(session, project_id)
    if payload.title is not None:
        row.title = payload.title.strip()
    if payload.description is not None:
        row.description = payload.description.strip()
    row.updated_at = _now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _project_read(row)


@router.get("/{project_id}/page", response_model=ProjectPage)
def get_project_page(project_id: int, session: Session = Depends(get_session)) -> ProjectPage:
    row = _require_project(session, project_id)
    return ProjectPage(blocks=_parse_blocks(row))


@router.put("/{project_id}/page", response_model=ProjectPage)
def put_project_page(project_id: int, payload: ProjectPage, session: Session = Depends(get_session)) -> ProjectPage:
    row = _require_project(session, project_id)
    _write_blocks(row, payload.blocks)
    session.add(row)
    session.commit()
    return ProjectPage(blocks=_parse_blocks(row))


@router.get("/{project_id}/top-tasks", response_model=list[ProjectTopTask])
def get_project_top_tasks(project_id: int, limit: int = Query(default=5, ge=1, le=20), session: Session = Depends(get_session)) -> list[ProjectTopTask]:
    row = _require_project(session, project_id)
    return _project_top_tasks(row, limit=limit)


@router.post("/reorder")
def reorder_projects(payload: ProjectReorderRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = list(session.exec(select(Project)).all())
    by_id = {row.id: row for row in rows if row.id is not None}
    rank = 0
    for project_id in payload.orderedProjectIds:
        row = by_id.get(project_id)
        if not row:
            continue
        row.priority_rank = rank
        row.updated_at = _now()
        session.add(row)
        rank += 1
    for row in sorted(rows, key=_priority_sort_key):
        if row.id in payload.orderedProjectIds:
            continue
        row.priority_rank = rank
        row.updated_at = _now()
        session.add(row)
        rank += 1
    session.commit()
    return {"ok": True}


@router.get("/{project_id}/workspace", response_model=ProjectWorkspace)
def get_project_workspace(project_id: int, session: Session = Depends(get_session)) -> ProjectWorkspace:
    row = _require_project(session, project_id)
    return ProjectWorkspace(project_id=project_id, blocks=_parse_blocks(row), active_sessions=[], credential_status=[])


@router.put("/{project_id}/workspace", response_model=ProjectWorkspace)
def put_project_workspace(project_id: int, payload: ProjectWorkspacePutRequest, session: Session = Depends(get_session)) -> ProjectWorkspace:
    row = _require_project(session, project_id)
    _write_blocks(row, payload.blocks)
    session.add(row)
    session.commit()
    return ProjectWorkspace(project_id=project_id, blocks=_parse_blocks(row), active_sessions=[], credential_status=[])


@router.post("/{project_id}/tabs/{tab_id}/close")
def close_project_tab(project_id: int, tab_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_project(session, project_id)
    return {"ok": True, "project_id": project_id, "tab_id": tab_id, "closed": True}


@router.post("/{project_id}/tabs/{tab_id}/credentials")
def save_project_tab_credentials(project_id: int, tab_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_project(session, project_id)
    return {"ok": True, "project_id": project_id, "tab_id": tab_id, "stored": False}


@router.delete("/{project_id}/tabs/{tab_id}/credentials")
def delete_project_tab_credentials(project_id: int, tab_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_project(session, project_id)
    return {"ok": True, "project_id": project_id, "tab_id": tab_id, "deleted": True}


def _patch_task_impl(task_id: str, payload: TaskPatchRequest, session: Session) -> dict[str, Any]:
    if payload.project_id is None:
        raise HTTPException(status_code=400, detail="project_id is required")
    row = _require_project(session, payload.project_id)
    blocks = _parse_blocks(row)
    updated = False
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "task" or str(block.get("id", "")) != task_id:
            continue
        if payload.title is not None:
            block["content"] = payload.title.strip()
        if payload.completed is not None:
            block["status"] = "done" if payload.completed else (str(block.get("status") or "todo") if str(block.get("status") or "todo") != "done" else "todo")
        updated = True
        break
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    _write_blocks(row, blocks)
    session.add(row)
    session.commit()
    return {"ok": True, "task_id": task_id}


@tasks_router.patch("/{task_id}")
def patch_project_task(task_id: str, payload: TaskPatchRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    return _patch_task_impl(task_id, payload, session)


@legacy_tasks_router.patch("/{task_id}")
def patch_project_task_legacy(task_id: str, payload: TaskPatchRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    return _patch_task_impl(task_id, payload, session)
