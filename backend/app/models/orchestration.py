from __future__ import annotations

from datetime import datetime

from sqlmodel import Column, DateTime, Field, SQLModel


class OrchestrationSettings(SQLModel, table=True):
    __tablename__ = "orchestration_settings"

    id: int | None = Field(default=1, primary_key=True)
    preferred_terminal_node_id: str = Field(default="devwork", max_length=120)
    preferred_execution_mode: str = Field(default="delegated_runner", max_length=40)
    default_codex_mode: str = Field(default="workspace-write", max_length=40)
    default_timeout_seconds: int = Field(default=3600)
    global_max_active_jobs: int = Field(default=8)
    default_max_retries: int = Field(default=1)
    scheduler_poll_seconds: int = Field(default=5)
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))


class OrchestrationJob(SQLModel, table=True):
    __tablename__ = "orchestration_jobs"

    id: str = Field(primary_key=True, max_length=64)
    title: str = Field(default="", max_length=200)
    task_type: str = Field(default="codex_task", index=True, max_length=120)
    target_node: str = Field(index=True, max_length=120)
    repo_path: str = Field(default="", max_length=400)
    workspace_path: str = Field(default="", max_length=400)
    prompt: str = Field(default="")
    instructions: str = Field(default="")
    execution_mode: str = Field(default="delegated_runner", max_length=40)
    codex_mode: str = Field(default="workspace-write", max_length=40)
    priority: int = Field(default=100, index=True)
    timeout_seconds: int = Field(default=3600)
    dependencies_json: str = Field(default="[]")
    status: str = Field(default="queued", index=True, max_length=50)
    runner_job_id: str = Field(default="", index=True, max_length=120)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=1)
    assigned_runner: str = Field(default="", max_length=200)
    logs_url: str = Field(default="", max_length=400)
    result_summary: str = Field(default="")
    changed_files_json: str = Field(default="[]")
    artifacts_json: str = Field(default="[]")
    metadata_json: str = Field(default="{}")
    last_error: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
