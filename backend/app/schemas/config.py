from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigResponse(BaseModel):
    runs_directory: str
    poll_interval_seconds: int = Field(ge=1, le=300)
    monitor_source_url: str
    topic_base_url: str


class ConfigUpdate(BaseModel):
    runs_directory: str | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=1, le=300)
    monitor_source_url: str | None = None
    topic_base_url: str | None = None
