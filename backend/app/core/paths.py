from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    return Path(raw).expanduser().resolve() if raw else default.resolve()


def dashburg_data_dir() -> Path:
    return _path_from_env("DASHBURG_DATA_DIR", ROOT_DIR / "data")


def dashburg_config_dir() -> Path:
    return _path_from_env("DASHBURG_CONFIG_DIR", dashburg_data_dir())


def dashburg_secrets_dir() -> Path:
    return _path_from_env("DASHBURG_SECRETS_DIR", dashburg_data_dir())


def config_path() -> Path:
    return dashburg_config_dir() / "config.json"


def db_path() -> Path:
    return dashburg_data_dir() / "db.sqlite3"


def localops_data_dir() -> Path:
    return dashburg_data_dir() / "localops"


def remoteops_data_dir() -> Path:
    return dashburg_secrets_dir() / "remoteops"


def remoteops_inventory_path() -> Path:
    raw = os.getenv("DASHBURG_REMOTEOPS_INVENTORY", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return dashburg_config_dir() / "remote_ops" / "servers.yaml"


def ensure_runtime_dirs() -> None:
    for path in {
        dashburg_data_dir(),
        dashburg_config_dir(),
        dashburg_secrets_dir(),
        localops_data_dir(),
        remoteops_data_dir(),
        remoteops_inventory_path().parent,
    }:
        path.mkdir(parents=True, exist_ok=True)
