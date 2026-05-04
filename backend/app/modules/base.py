from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fastapi import APIRouter


@dataclass
class BackendModule:
    key: str
    name: str
    sidebar_label: str
    router: APIRouter
    routes: list[dict[str, str]] = field(default_factory=list)
    cards: list[dict[str, str]] = field(default_factory=list)
    collectors: list[Callable] = field(default_factory=list)
    metrics_contributors: list[Callable] = field(default_factory=list)
