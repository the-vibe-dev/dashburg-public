from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MessageRole = Literal["user", "assistant", "system", "tool"]
MessageSource = Literal["web", "discord", "system", "agent", "tool"]


class ChatSessionCreateRequest(BaseModel):
    session_id: str | None = None
    title: str = "Dashburg Chat Session"
    model: str | None = None
    provider: str = "ollama"
    source_types: list[MessageSource] = Field(default_factory=lambda: ["web"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatSessionAttachDiscordRequest(BaseModel):
    guild_id: str = ""
    channel_id: str = ""
    user_id: str = ""
    source_types: list[MessageSource] = Field(default_factory=lambda: ["web", "discord"])


class ChatMessageCreateRequest(BaseModel):
    role: MessageRole = "user"
    source: MessageSource = "web"
    content: str = Field(min_length=1)
    model: str | None = None
    provider: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tool_payload: dict[str, Any] | None = None
    audit_id: str | None = None


class ChatSessionSyncRequest(BaseModel):
    messages: list[ChatMessageCreateRequest] = Field(default_factory=list)


class ChatStreamRequest(BaseModel):
    content: str = Field(min_length=1)
    source: MessageSource = "web"
    model: str | None = None
    provider: str | None = None
    include_memory: bool = True
    max_history_messages: int = Field(default=24, ge=2, le=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessageOut(BaseModel):
    id: str
    session_id: str
    role: MessageRole
    source: MessageSource
    content: str
    created_at: str
    model: str
    provider: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    tool_payload: dict[str, Any] | None = None
    audit_id: str | None = None


class ChatSessionOut(BaseModel):
    id: str
    title: str
    status: str
    model: str
    provider: str
    source_types: list[MessageSource] = Field(default_factory=list)
    discord_link: dict[str, str] = Field(default_factory=dict)
    message_count: int = 0
    created_at: str
    updated_at: str
    last_message_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
