from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MemoryHealthResponse(BaseModel):
    ok: bool
    shared_root: str
    shared_available: bool
    replay_queue_length: int
    fallback_root: str
    lock_timeout_seconds: float


class MemorySettingsResponse(BaseModel):
    shared_root: str
    fallback_root: str
    brief_max_chars: int = 1800
    rerank_default: bool = False
    lock_timeout_seconds: float = 3.0
    using_env_root: bool = True


class MemorySearchRequest(BaseModel):
    query: str = ""
    node_id: str | None = None
    repo_path: str | None = None
    limit: int = Field(default=20, ge=1, le=200)
    include_docs: bool = False
    include_knowledge: bool = True
    rerank: bool = False


class MemorySearchResult(BaseModel):
    stage: str
    score: float = 0.0
    item: dict[str, Any] = Field(default_factory=dict)


class MemorySearchResponse(BaseModel):
    items: list[MemorySearchResult] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    rerank_applied: bool = False


class MemoryBriefRequest(BaseModel):
    query: str = ""
    node_id: str | None = None
    repo_path: str | None = None
    max_chars: int = Field(default=1800, ge=300, le=1800)
    rerank: bool = False


class MemoryBriefResponse(BaseModel):
    brief: str
    chars: int


MemoryPipelineStatus = Literal[
    "captured",
    "skipped_empty",
    "skipped_duplicate",
    "queued_for_compaction",
    "compacted",
    "promoted",
    "promotion_skipped",
]


class MemoryCompactRequest(BaseModel):
    candidate: dict[str, Any] | None = None
    promote: bool = False
    limit: int = Field(default=100, ge=1, le=1000)


class MemoryCompactResponse(BaseModel):
    states: list[MemoryPipelineStatus] = Field(default_factory=list)
    candidate: dict[str, Any] | None = None
    compacted_count: int = 0
    replayed_count: int = 0


class MemoryListResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
