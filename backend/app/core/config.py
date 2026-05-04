from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.paths import config_path, dashburg_data_dir, ensure_runtime_dirs


ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = dashburg_data_dir()
CONFIG_PATH = config_path()


class AppConfig(BaseModel):
    runs_directory: str = Field(default=str(DATA_DIR / "sample_runs"))
    poll_interval_seconds: int = Field(default=5, ge=1, le=300)
    monitor_source_url: str = Field(default="http://127.0.0.1:9180")
    monitor_auth_user: str = Field(default="")
    monitor_auth_password: str = Field(default="")
    topic_base_url: str = Field(default_factory=lambda: os.getenv("TOPIC_BASE_URL", "http://topic.example.local:8080"))


def ensure_data_dirs() -> None:
    ensure_runtime_dirs()


def load_config() -> AppConfig:
    ensure_data_dirs()
    if not CONFIG_PATH.exists():
        cfg = AppConfig()
        save_config(cfg)
        return cfg
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)


def save_config(config: AppConfig) -> AppConfig:
    ensure_data_dirs()
    CONFIG_PATH.write_text(
        json.dumps(config.model_dump(), indent=2),
        encoding="utf-8",
    )
    return config


def update_config(patch: dict[str, Any]) -> AppConfig:
    current = load_config().model_dump()
    current.update(patch)
    cfg = AppConfig.model_validate(current)
    return save_config(cfg)
