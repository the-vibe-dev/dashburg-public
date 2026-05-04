from __future__ import annotations

from datetime import datetime

from sqlmodel import Column, DateTime, Field, SQLModel


class Run(SQLModel, table=True):
    id: str = Field(primary_key=True, max_length=255)
    repo_name: str = Field(default="Unknown", index=True)
    monitor_name: str = Field(default="unknown", index=True)
    status: str = Field(default="unknown", index=True)
    stage: str = Field(default="-")
    topic: str = Field(default="-")
    timer_unit: str = Field(default="-")
    run_kind: str = Field(default="pipeline")
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    ended_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    source_path: str = Field(default="")
    run_payload: str = Field(default="{}")


class RunEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    event_key: str = Field(index=True, unique=True, max_length=500)
    event_type: str = Field(default="log", index=True)
    ts: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=False), nullable=False))
    message: str = Field(default="")
    payload: str = Field(default="{}")
