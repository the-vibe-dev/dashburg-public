from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RunnerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8844
    node_id: str = ""
    key_id: str
    shared_secret: str
    auth_max_skew_seconds: int = 60
    auth_required: bool = True

    data_dir: str = "/var/lib/dashburg-runner"
    log_file: str = "/var/log/dashburg-runner.log"

    apt_upgrade_enabled: bool = False
    codex_enabled: bool = False
    webagent_enabled: bool = False
    webagent_command: str = ""
    webagent_node_api_base: str = "http://127.0.0.1:9477"
    webagent_node_api_token_env: str = "WEBAGENT_NODE_API_TOKEN"
    webagent_node_api_token: str = ""
    webagent_node_artifacts_dir: str = "/opt/dashburg/browser-qa-node/artifacts"
    webagent_timeout_seconds: int = 900
    webagent_poll_interval_seconds: float = 2.0
    webagent_action_timeout_seconds: int = 45
    max_concurrent_jobs: int = 1
    workspace_root: str = "/tmp/dashburg-orchestration"
    roles: list[str] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)

    allowed_repos: list[str] = Field(default_factory=list)
    allowed_services: list[str] = Field(default_factory=list)
    allowed_compose_dirs: list[str] = Field(default_factory=list)


def _expand_paths(values: list[str]) -> list[str]:
    return [str(Path(v).expanduser().resolve()) for v in values]


def load_config(config_path: str | None = None) -> RunnerConfig:
    env_path = os.getenv("RUNNER_CONFIG", "").strip()
    selected: Path | None = None
    if config_path:
        selected = Path(config_path)
    elif env_path:
        selected = Path(env_path)
    else:
        candidates = [
            Path("./config.yaml"),
            Path("/etc/dashburg-runner/config.yaml"),
            Path("./runner/config.yaml"),
        ]
        for candidate in candidates:
            if candidate.expanduser().exists():
                selected = candidate
                break
        if selected is None:
            selected = Path("./config.yaml")

    path = selected.expanduser().resolve()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = RunnerConfig.model_validate(data)
    cfg.allowed_repos = _expand_paths(cfg.allowed_repos)
    cfg.allowed_compose_dirs = _expand_paths(cfg.allowed_compose_dirs)
    return cfg


def path_is_allowlisted(path: str, allowlist: list[str]) -> bool:
    candidate = Path(path).expanduser().resolve()
    for allowed in allowlist:
        base = Path(allowed).resolve()
        try:
            candidate.relative_to(base)
            return True
        except ValueError:
            continue
    return False
