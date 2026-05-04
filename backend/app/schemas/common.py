from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool
    service: str = "dashburg"
    timestamp: datetime


class ModuleRoute(BaseModel):
    path: str
    label: str


class ModuleCard(BaseModel):
    title: str
    description: str
    href: str


class ModuleInfo(BaseModel):
    key: str
    name: str
    sidebar_label: str
    routes: list[ModuleRoute] = Field(default_factory=list)
    cards: list[ModuleCard] = Field(default_factory=list)


class MetricsSummary(BaseModel):
    runs_today: int
    runs_wtd: int = 0
    runs_mtd: int = 0
    running_now: int
    failures_today: int
    success_rate: float
    total_last_24h: int
    recent_failures: list[dict[str, Any]]
    live_active_runs: list[dict[str, Any]]
