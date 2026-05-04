from __future__ import annotations

from datetime import datetime

from sqlmodel import Column, DateTime, Field, SQLModel


class RemoteJob(SQLModel, table=True):
    __tablename__ = "remote_job"

    id: str = Field(primary_key=True, max_length=64)
    server_id: str = Field(index=True, max_length=120)
    runner_job_id: str = Field(index=True, max_length=120)
    job_type: str = Field(index=True, max_length=120)
    status: str = Field(default="queued", index=True, max_length=50)
    request_json: str = Field(default="{}")
    result_json: str = Field(default="{}")
    log_offset: int = Field(default=0)
    merged_label: bool = Field(default=False)
    archived: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=False), nullable=False),
    )
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))
