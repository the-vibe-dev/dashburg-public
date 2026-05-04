from __future__ import annotations

from datetime import datetime

from sqlmodel import Column, DateTime, Field, SQLModel


class RemoteOpsSettings(SQLModel, table=True):
    __tablename__ = "remoteops_settings"

    id: int | None = Field(default=1, primary_key=True)
    main_llm_provider: str = Field(default="ollama", max_length=40)
    main_llm_model: str = Field(default="")
    main_llm_base_url: str = Field(default="")
    main_llm_api_key_ref: str = Field(default="")
    chat_enabled: bool = Field(default=False)
    execution_mode: str = Field(default="require_confirm", max_length=40)
    default_target_node_id: str = Field(default="", max_length=120)
    job_timeouts_json: str = Field(default="{}")
    log_retention_days: int = Field(default=14)
    allow_codex_jobs: bool = Field(default=True)
    allow_system_actions: bool = Field(default=True)
    allow_apt_upgrade: bool = Field(default=False)
    max_concurrent_jobs_per_node: int = Field(default=1)
    max_concurrent_jobs_global: int = Field(default=8)
    terminal_enabled: bool = Field(default=True)
    terminal_idle_timeout_minutes: int = Field(default=5)
    terminal_max_sessions: int = Field(default=2)
    terminal_recording_enabled: bool = Field(default=False)
    client_token: str = Field(default="", max_length=255)
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))


class RemoteOpsNode(SQLModel, table=True):
    __tablename__ = "remoteops_nodes"

    id: str = Field(primary_key=True, max_length=120)
    enabled: bool = Field(default=True)
    label: str = Field(default="", max_length=200)
    base_url: str = Field(default="", max_length=400)
    supports_codex: bool = Field(default=False)
    supports_terminal: bool = Field(default=False)
    max_concurrent_jobs: int = Field(default=1)
    capabilities_json: str = Field(default="{}")
    allowed_job_types_json: str = Field(default="[]")
    allowed_repos_json: str = Field(default="[]")
    allowed_services_json: str = Field(default="[]")
    notes: str = Field(default="")
    key_id: str = Field(default="", max_length=120)
    last_seen_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))


class RemoteOpsNodeKey(SQLModel, table=True):
    __tablename__ = "remoteops_node_keys"

    id: int | None = Field(default=None, primary_key=True)
    node_id: str = Field(index=True, max_length=120)
    key_id: str = Field(max_length=120)
    secret_ref: str = Field(max_length=200)
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    disabled_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))


class RemoteOpsJob(SQLModel, table=True):
    __tablename__ = "remoteops_jobs"

    id: str = Field(primary_key=True, max_length=64)
    node_id: str = Field(index=True, max_length=120)
    runner_job_id: str = Field(index=True, max_length=120)
    job_type: str = Field(index=True, max_length=120)
    status: str = Field(default="queued", index=True, max_length=50)
    params_json: str = Field(default="{}")
    result_json: str = Field(default="{}")
    created_by: str = Field(default="ui", max_length=100)
    merged_label: bool = Field(default=False)
    archived: bool = Field(default=False)
    log_offset: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))


class RemoteOpsTerminalSession(SQLModel, table=True):
    __tablename__ = "remoteops_terminal_sessions"

    id: str = Field(primary_key=True, max_length=64)
    node_id: str = Field(index=True, max_length=120)
    status: str = Field(default="open", max_length=30)
    created_by: str = Field(default="ui", max_length=100)
    record_io: bool = Field(default=False)
    last_activity_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    closed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
