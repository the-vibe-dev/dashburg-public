from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ExecutionMode = Literal["propose_only", "require_confirm", "auto_execute_allowlisted"]
ProviderId = Literal["openai", "ollama", "openai_oauth"]


class LocalOpsSettingsRead(BaseModel):
    default_provider_id: ProviderId = "openai"
    default_model: str = "gpt-4o-mini"
    execution_mode: ExecutionMode = "require_confirm"
    max_tool_steps_per_run: int = 8
    max_run_seconds: int = 600
    max_concurrent_runs: int = 2
    terminal_idle_timeout_minutes: int = 30
    allow_shell_exec: bool = False
    shell_allowlist: list[str] = Field(default_factory=list)


class LocalOpsSettingsUpdate(BaseModel):
    default_provider_id: ProviderId = "openai"
    default_model: str = "gpt-4o-mini"
    execution_mode: ExecutionMode = "require_confirm"
    max_tool_steps_per_run: int = Field(default=8, ge=1, le=64)
    max_run_seconds: int = Field(default=600, ge=30, le=7200)
    max_concurrent_runs: int = Field(default=2, ge=1, le=16)
    terminal_idle_timeout_minutes: int = Field(default=30, ge=1, le=720)
    allow_shell_exec: bool = False
    shell_allowlist: list[str] = Field(default_factory=list)


class LocalOpsProviderRead(BaseModel):
    id: int
    provider_id: ProviderId
    name: str
    base_url: str
    enabled: bool
    default_for_agents: bool
    extra: dict[str, Any] = Field(default_factory=dict)


class LocalOpsProviderCreate(BaseModel):
    provider_id: ProviderId
    name: str
    base_url: str
    api_key: str = ""
    enabled: bool = True
    default_for_agents: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class LocalOpsProviderUpdate(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    enabled: bool = True
    default_for_agents: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class LocalOpsThreadCreate(BaseModel):
    title: str = "New Thread"
    provider_id: ProviderId = "openai"
    provider_endpoint_id: int | None = None
    model: str = "gpt-4o-mini"
    execution_mode: ExecutionMode = "require_confirm"


class LocalOpsThreadRead(BaseModel):
    id: str
    title: str
    provider_id: ProviderId
    provider_endpoint_id: int | None = None
    model: str
    execution_mode: ExecutionMode
    created_at: datetime
    updated_at: datetime


class LocalOpsMessageRead(BaseModel):
    id: str
    thread_id: str
    run_id: str | None
    role: str
    content: str
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class LocalOpsThreadDetail(BaseModel):
    thread: LocalOpsThreadRead
    messages: list[LocalOpsMessageRead] = Field(default_factory=list)


class LocalOpsPostMessage(BaseModel):
    content: str = Field(min_length=1)
    provider_id: ProviderId = "openai"
    provider_endpoint_id: int | None = None
    model: str = "gpt-4o-mini"
    execution_mode: ExecutionMode = "require_confirm"


class LocalOpsRunRead(BaseModel):
    id: str
    thread_id: str
    status: str
    llm_status: str = "queued"
    provider_id: ProviderId
    provider_endpoint_id: int | None = None
    endpoint_label: str = ""
    endpoint_url: str = ""
    model: str
    request_type: str = "chat"
    telemetry: dict[str, Any] = Field(default_factory=dict)
    execution_mode: ExecutionMode
    error: str
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LocalOpsToolCallRead(BaseModel):
    id: str
    run_id: str
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime
    updated_at: datetime


class LocalOpsRunDetail(BaseModel):
    run: LocalOpsRunRead
    tool_calls: list[LocalOpsToolCallRead] = Field(default_factory=list)


class LocalOpsApproveToolRequest(BaseModel):
    tool_call_id: str


class OllamaTestRequest(BaseModel):
    base_url: str
    api_key: str = ""


class OpenAiApiKeyStatus(BaseModel):
    configured: bool
    source: str = ""
    masked: str = ""


class OpenAIDevicePollRequest(BaseModel):
    flow_id: str = Field(min_length=6)


class OpenAIOAuthExchangeUrlRequest(BaseModel):
    callback_url: str = Field(min_length=8)


class OpenAIImportTokenRequest(BaseModel):
    token_input: str = Field(min_length=10)


class LocalOpsTerminalCreateRequest(BaseModel):
    force_new: bool = False
    cwd: str | None = None
    command: str | None = None


class LocalOpsAgentSessionCreateRequest(BaseModel):
    agent_slug: str = Field(min_length=1)
    title: str = ""
    seed_markdown: str = ""
    agent_name: str = ""
    workspace_root: str = ""
    codex_model: str = "gpt-5.3-codex"
    target_node_id: str = ""
    target_repo_path: str = ""
    target_repo_purpose: str = ""


class LocalOpsAgentSessionUpdateRequest(BaseModel):
    name: str = ""
    title: str = ""
    codex_model: str = "gpt-5.3-codex"
    input_file: str = "INPUT.md"
    output_file: str = "OUTPUT.md"
    state_file: str = "STATE.md"
    memory_file: str = "MEM.md"
    notes_file: str = "NOTES.md"
    investigations_file: str = "INVESTIGATIONS.md"
    host_profile_file: str = "HOST_PROFILE.md"
    repo_profile_file: str = "REPO_PROFILE.md"
    target_node_id: str = ""
    target_repo_path: str = ""
    target_repo_purpose: str = ""


class LocalOpsAgentPackUpsertRequest(BaseModel):
    slug: str = Field(min_length=1)
    title: str = ""
    instructions: str = Field(min_length=1)
    tooling: str = ""
    skill_md: str = ""


class LocalOpsAgentSessionRunRequest(BaseModel):
    task: str = Field(min_length=1)
    sandbox_mode: str = "workspace-write"
    timeout_s: int = Field(default=600, ge=30, le=3600)


class LocalOpsAgentFileWriteRequest(BaseModel):
    content: str = ""
