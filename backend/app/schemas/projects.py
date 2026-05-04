from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class ProjectRead(BaseModel):
    id: int
    title: str
    description: str
    priority_rank: int | None = None
    created_at: datetime
    updated_at: datetime


class ProjectPage(BaseModel):
    blocks: list[dict[str, Any]] = Field(default_factory=list)


class ProjectTopTask(BaseModel):
    id: str
    content: str
    status: str
    priority: str
    created_at: str = ""


class ProjectDashboardRead(ProjectRead):
    notes_preview: str = ""
    top_tasks: list[ProjectTopTask] = Field(default_factory=list)


class ProjectReorderRequest(BaseModel):
    orderedProjectIds: list[int] = Field(default_factory=list)


class TaskPatchRequest(BaseModel):
    project_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    completed: bool | None = None


class ProjectWorkspace(BaseModel):
    project_id: int
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    active_sessions: list[dict[str, Any]] = Field(default_factory=list)
    credential_status: list[dict[str, Any]] = Field(default_factory=list)


class ProjectWorkspacePutRequest(BaseModel):
    blocks: list[dict[str, Any]] = Field(default_factory=list)


class ProjectTabOpenRequest(BaseModel):
    node_id: str | None = None
    timeout_seconds: int = Field(default=120, ge=5, le=600)


class ProjectTabCloseRequest(BaseModel):
    node_id: str | None = None
    timeout_seconds: int = Field(default=60, ge=5, le=600)


class ProjectCredentialUpsertRequest(BaseModel):
    username: str = Field(default="", max_length=240)
    password: str | None = None
    token: str | None = None
    cookie_bundle: str | None = None


class ProjectCredentialStatus(BaseModel):
    tab_id: str
    has_credentials: bool = False
    kinds: list[str] = Field(default_factory=list)
    username: str = ""
    updated_at: str = ""
