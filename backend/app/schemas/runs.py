from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RunRead(BaseModel):
    id: str
    repo_name: str
    monitor_name: str
    status: str
    stage: str
    topic: str
    timer_unit: str
    run_kind: str
    started_at: datetime | None
    ended_at: datetime | None
    updated_at: datetime


class RunEventRead(BaseModel):
    id: int
    run_id: str
    event_key: str
    event_type: str
    ts: datetime
    message: str
    payload: dict[str, Any]


class RunLogsResponse(BaseModel):
    run_id: str
    logs: str


class ArtifactItem(BaseModel):
    name: str
    path: str
    size_bytes: int


class VideoOverviewResponse(BaseModel):
    generated_at: datetime
    summary: dict[str, Any]
    rollup: dict[str, Any]
    repos: list[dict[str, Any]]
    running: list[dict[str, Any]]
