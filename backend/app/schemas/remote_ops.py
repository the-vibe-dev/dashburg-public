from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RemoteOpsSettingsRead(BaseModel):
    main_llm_provider: Literal["openai", "ollama", "custom_http"] = "ollama"
    main_llm_model: str = ""
    main_llm_base_url: str = ""
    main_llm_api_key_ref: str = ""
    chat_enabled: bool = False
    execution_mode: Literal["propose_only", "require_confirm", "auto_execute_allowlisted"] = "require_confirm"
    default_target_node_id: str = ""
    job_timeouts: dict[str, int] = Field(default_factory=dict)
    log_retention_days: int = 14
    allow_codex_jobs: bool = True
    allow_system_actions: bool = True
    allow_apt_upgrade: bool = False
    max_concurrent_jobs_per_node: int = 1
    max_concurrent_jobs_global: int = 8
    terminal_enabled: bool = True
    terminal_idle_timeout_minutes: int = 5
    terminal_max_sessions: int = 2
    terminal_recording_enabled: bool = False
    chat_client_token: str = ""


class RemoteOpsSettingsUpdate(BaseModel):
    main_llm_provider: Literal["openai", "ollama", "custom_http"] = "ollama"
    main_llm_model: str = ""
    main_llm_base_url: str = ""
    main_llm_api_key_ref: str = ""
    chat_enabled: bool = False
    execution_mode: Literal["propose_only", "require_confirm", "auto_execute_allowlisted"] = "require_confirm"
    default_target_node_id: str = ""
    job_timeouts: dict[str, int] = Field(default_factory=dict)
    log_retention_days: int = Field(default=14, ge=1, le=3650)
    allow_codex_jobs: bool = True
    allow_system_actions: bool = True
    allow_apt_upgrade: bool = False
    max_concurrent_jobs_per_node: int = Field(default=1, ge=1, le=32)
    max_concurrent_jobs_global: int = Field(default=8, ge=1, le=256)
    terminal_enabled: bool = True
    terminal_idle_timeout_minutes: int = Field(default=5, ge=1, le=720)
    terminal_max_sessions: int = Field(default=2, ge=1, le=32)
    terminal_recording_enabled: bool = False
    chat_client_token: str = ""


class NodeKeyRead(BaseModel):
    key_id: str
    created_at: datetime
    disabled_at: datetime | None = None


class NodeRead(BaseModel):
    id: str
    enabled: bool
    label: str
    base_url: str
    supports_codex: bool
    supports_terminal: bool
    max_concurrent_jobs: int = 1
    capabilities: dict[str, Any] = Field(default_factory=dict)
    allowed_job_types: list[str] = Field(default_factory=list)
    allowed_repos: list[str] = Field(default_factory=list)
    allowed_services: list[str] = Field(default_factory=list)
    notes: str = ""
    key_id: str = ""
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    keys: list[NodeKeyRead] = Field(default_factory=list)


class NodeCreate(BaseModel):
    id: str = Field(min_length=2, max_length=120)
    enabled: bool = True
    label: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=8, max_length=400)
    supports_codex: bool = False
    supports_terminal: bool = False
    max_concurrent_jobs: int = Field(default=1, ge=1, le=32)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    allowed_job_types: list[str] = Field(default_factory=list)
    allowed_repos: list[str] = Field(default_factory=list)
    allowed_services: list[str] = Field(default_factory=list)
    notes: str = ""


class NodeUpdate(BaseModel):
    enabled: bool = True
    label: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=8, max_length=400)
    supports_codex: bool = False
    supports_terminal: bool = False
    max_concurrent_jobs: int = Field(default=1, ge=1, le=32)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    allowed_job_types: list[str] = Field(default_factory=list)
    allowed_repos: list[str] = Field(default_factory=list)
    allowed_services: list[str] = Field(default_factory=list)
    notes: str = ""


class NodeRotateKeyRequest(BaseModel):
    disable_previous: bool = False


class NodeRotateKeyResponse(BaseModel):
    node_id: str
    key_id: str
    secret: str


class RunnerInstallSnippet(BaseModel):
    node_id: str
    key_id: str
    secret: str
    config_yaml: str
    install_commands: str
    main_terminal_commands: str = ""


class RemoteJobCreate(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class RemoteJobRead(BaseModel):
    id: str
    node_id: str
    runner_job_id: str
    job_type: str
    status: str
    params: dict[str, Any]
    result: dict[str, Any]
    created_by: str
    log_offset: int
    merged_label: bool
    archived: bool
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    runner_detail: dict[str, Any] | None = None


class RemoteJobPatch(BaseModel):
    merged_label: bool | None = None
    archived: bool | None = None


class TerminalSessionCreate(BaseModel):
    node_id: str
    cwd: str | None = None
    command: str | None = None
    forceNew: bool = False


class TerminalSessionRead(BaseModel):
    id: str
    node_id: str
    status: str
    created_by: str
    record_io: bool
    last_activity_at: datetime
    created_at: datetime
    closed_at: datetime | None


class TerminalSessionCreateResponse(BaseModel):
    session_id: str
    session: TerminalSessionRead
    reused: bool = False


class TerminalKillResponse(BaseModel):
    ok: bool
    session_id: str
