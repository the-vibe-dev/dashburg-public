from __future__ import annotations

from datetime import datetime

from sqlmodel import Column, DateTime, Field, SQLModel


class LocalOpsSettings(SQLModel, table=True):
    __tablename__ = "localops_settings"

    id: int | None = Field(default=1, primary_key=True)
    default_provider_id: str = Field(default="openai", max_length=40)
    default_model: str = Field(default="gpt-4o-mini", max_length=120)
    execution_mode: str = Field(default="require_confirm", max_length=50)
    max_tool_steps_per_run: int = Field(default=8)
    max_run_seconds: int = Field(default=600)
    max_concurrent_runs: int = Field(default=2)
    terminal_idle_timeout_minutes: int = Field(default=30)
    allow_shell_exec: bool = Field(default=False)
    shell_allowlist_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))


class LocalOpsProvider(SQLModel, table=True):
    __tablename__ = "localops_providers"

    id: int | None = Field(default=None, primary_key=True)
    provider_id: str = Field(index=True, max_length=40)  # openai | ollama
    name: str = Field(default="", max_length=120)
    base_url: str = Field(default="", max_length=400)
    api_key: str = Field(default="", max_length=255)
    enabled: bool = Field(default=True)
    default_for_agents: bool = Field(default=False)
    extra_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))


class LocalOpsThread(SQLModel, table=True):
    __tablename__ = "localops_threads"

    id: str = Field(primary_key=True, max_length=64)
    title: str = Field(default="New Thread", max_length=200)
    provider_id: str = Field(default="openai", max_length=40)
    provider_endpoint_id: int | None = Field(default=None, index=True)
    model: str = Field(default="gpt-4o-mini", max_length=120)
    execution_mode: str = Field(default="require_confirm", max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))


class LocalOpsMessage(SQLModel, table=True):
    __tablename__ = "localops_messages"

    id: str = Field(primary_key=True, max_length=64)
    thread_id: str = Field(index=True, max_length=64)
    run_id: str | None = Field(default=None, index=True, max_length=64)
    role: str = Field(max_length=30)  # system | user | assistant | tool
    content: str = Field(default="")
    meta_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))


class LocalOpsRun(SQLModel, table=True):
    __tablename__ = "localops_runs"

    id: str = Field(primary_key=True, max_length=64)
    thread_id: str = Field(index=True, max_length=64)
    status: str = Field(default="queued", index=True, max_length=40)  # queued | running | waiting_approval | completed | failed | canceled
    llm_status: str = Field(default="queued", index=True, max_length=40)
    provider_id: str = Field(default="openai", max_length=40)
    provider_endpoint_id: int | None = Field(default=None, index=True)
    endpoint_label: str = Field(default="", max_length=160)
    endpoint_url: str = Field(default="", max_length=400)
    model: str = Field(default="gpt-4o-mini", max_length=120)
    request_type: str = Field(default="chat", max_length=32)
    telemetry_json: str = Field(default="{}")
    execution_mode: str = Field(default="require_confirm", max_length=50)
    error: str = Field(default="")
    started_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))


class LocalOpsToolCall(SQLModel, table=True):
    __tablename__ = "localops_tool_calls"

    id: str = Field(primary_key=True, max_length=64)
    run_id: str = Field(index=True, max_length=64)
    tool_name: str = Field(max_length=80)
    args_json: str = Field(default="{}")
    result_json: str = Field(default="{}")
    status: str = Field(default="pending", max_length=40)  # pending | approved | completed | rejected | failed
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))


class LocalOpsWorkspace(SQLModel, table=True):
    __tablename__ = "localops_workspaces"

    id: str = Field(primary_key=True, max_length=64)
    run_id: str = Field(index=True, max_length=64)
    agent_slug: str = Field(default="", max_length=100)
    path: str = Field(default="", max_length=600)
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
