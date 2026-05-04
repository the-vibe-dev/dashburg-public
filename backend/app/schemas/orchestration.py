from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


OrchestrationStatus = Literal[
    "queued",
    "dispatched",
    "accepted",
    "preparing",
    "running",
    "waiting_dependency",
    "succeeded",
    "failed",
    "canceled",
    "timed_out",
]


class OrchestrationSettingsRead(BaseModel):
    preferred_terminal_node_id: str = "devwork"
    preferred_execution_mode: Literal["delegated_runner", "direct_ssh"] = "delegated_runner"
    default_codex_mode: Literal["read-only", "workspace-write", "danger-full-access"] = "workspace-write"
    default_timeout_seconds: int = 3600
    global_max_active_jobs: int = 8
    default_max_retries: int = 1
    scheduler_poll_seconds: int = 5


class OrchestrationSettingsUpdate(OrchestrationSettingsRead):
    default_timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    global_max_active_jobs: int = Field(default=8, ge=1, le=256)
    default_max_retries: int = Field(default=1, ge=0, le=10)
    scheduler_poll_seconds: int = Field(default=5, ge=1, le=300)


class OrchestrationJobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    task_type: str = Field(default="codex_task", min_length=1, max_length=120)
    target_node: str = Field(min_length=1, max_length=120)
    repo_path: str = Field(min_length=1, max_length=400)
    workspace_path: str = ""
    prompt: str = Field(min_length=1)
    instructions: str = ""
    execution_mode: Literal["delegated_runner", "direct_ssh"] = "delegated_runner"
    codex_mode: Literal["read-only", "workspace-write", "danger-full-access"] = "workspace-write"
    priority: int = Field(default=100, ge=1, le=1000)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    dependencies: list[str] = Field(default_factory=list)
    max_retries: int = Field(default=1, ge=0, le=10)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestrationJobBatchCreate(BaseModel):
    jobs: list[OrchestrationJobCreate] = Field(default_factory=list)


class OrchestrationJobRead(BaseModel):
    id: str
    title: str
    task_type: str
    target_node: str
    repo_path: str
    workspace_path: str
    prompt: str
    instructions: str
    execution_mode: str
    codex_mode: str
    priority: int
    timeout_seconds: int
    dependencies: list[str] = Field(default_factory=list)
    status: OrchestrationStatus
    runner_job_id: str = ""
    retry_count: int = 0
    max_retries: int = 1
    assigned_runner: str = ""
    logs_url: str = ""
    result_summary: str = ""
    changed_files: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    dependency_state: list[dict[str, Any]] = Field(default_factory=list)
    last_error: str = ""
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime
    runner_detail: dict[str, Any] | None = None


class OrchestrationJobActionResponse(BaseModel):
    ok: bool = True
    job: OrchestrationJobRead


class OrchestrationNodeSummary(BaseModel):
    id: str
    label: str
    base_url: str
    enabled: bool
    supports_codex: bool
    supports_terminal: bool
    max_concurrent_jobs: int
    running_jobs: int = 0
    queued_jobs: int = 0
    health_status: str = "unknown"
    capabilities: dict[str, Any] = Field(default_factory=dict)
    repos: list[str] = Field(default_factory=list)
    mailbox_counts: dict[str, int] = Field(default_factory=dict)


class OrchestrationMailboxItem(BaseModel):
    id: str
    node_id: str
    direction: Literal["inbox", "outbox"] | str
    type: str
    subject: str
    body: str
    job_id: str = ""
    run_id: str = ""
    severity: str = "info"
    status: str = "new"
    created_at: datetime | str
    updated_at: datetime | str | None = None
    from_: str = Field(alias="from")
    to: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    acknowledged: bool = False
    acknowledged_at: datetime | str | None = None
    archived: bool = False
    archived_at: datetime | str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestrationMailboxCreate(BaseModel):
    type: str = "note"
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    job_id: str = ""
    run_id: str = ""
    severity: str = "info"
    from_: str = Field(default="dashburg-operator", alias="from")
    to: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestrationMailSend(BaseModel):
    type: str = "note"
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    target_node_id: str = ""
    node_id: str = ""
    to: str = ""
    severity: str = "info"
    from_: str = Field(default="orchestration@dashburg.local", alias="from")
    job_id: str = ""
    run_id: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestrationOverview(BaseModel):
    localops_mode: str
    orchestration_mode: str
    settings: OrchestrationSettingsRead
    nodes: list[OrchestrationNodeSummary] = Field(default_factory=list)
    running_jobs: list[OrchestrationJobRead] = Field(default_factory=list)
    queued_jobs: list[OrchestrationJobRead] = Field(default_factory=list)
    recent_jobs: list[OrchestrationJobRead] = Field(default_factory=list)
    dependency_edges: list[dict[str, Any]] = Field(default_factory=list)
    mailbox: list[OrchestrationMailboxItem] = Field(default_factory=list)


class OrchestrationTerminalLaunch(BaseModel):
    node_id: str
    cwd: str
    command: str
    injected_label: str
