from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class UploadOption:
    upload_profile_id: str
    name: str
    platform: str
    enabled: bool
    description: str = ""


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def _env_prefix(profile_id: str) -> str:
    return "UPLOAD_PROFILE_" + profile_id.upper().replace("-", "_")


def _default_options() -> list[UploadOption]:
    return [
        UploadOption(upload_profile_id="youtube-default", name="YouTube Default", platform="youtube", enabled=True),
        UploadOption(upload_profile_id="facebook-default", name="Facebook Default", platform="facebook", enabled=True),
        UploadOption(upload_profile_id="tiktok-default", name="TikTok Default", platform="tiktok", enabled=False),
    ]


def list_upload_options() -> list[UploadOption]:
    configured = os.getenv("AIVIDEOFACTORY_UPLOAD_OPTIONS_JSON", "").strip()
    if configured:
        import json

        try:
            raw = json.loads(configured)
            out: list[UploadOption] = []
            if isinstance(raw, list):
                for row in raw:
                    if not isinstance(row, dict):
                        continue
                    profile_id = str(row.get("upload_profile_id") or "").strip()
                    if not profile_id:
                        continue
                    out.append(
                        UploadOption(
                            upload_profile_id=profile_id,
                            name=str(row.get("name") or profile_id),
                            platform=str(row.get("platform") or "other").lower(),
                            enabled=bool(row.get("enabled", True)),
                            description=str(row.get("description") or ""),
                        )
                    )
            if out:
                return out
        except Exception:
            pass
    return _default_options()


def resolve_upload_label(upload_profile_id: str) -> dict[str, str]:
    profile_id = upload_profile_id.strip()
    if not profile_id:
        return {"name": "Unassigned", "platform": "unknown"}
    for item in list_upload_options():
        if item.upload_profile_id == profile_id:
            return {"name": item.name, "platform": item.platform}
    return {"name": profile_id, "platform": "unknown"}


def resolve_upload_env(upload_profile_id: str) -> dict[str, str]:
    profile_id = upload_profile_id.strip()
    if not profile_id:
        return {}
    prefix = _env_prefix(profile_id)
    out: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith(prefix + "_") and value:
            out[key[len(prefix) + 1 :]] = value
    # Common global fallback keys used by current creator repos.
    global_keys = [
        "OPENAI_API_KEY",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_CHANNEL_ID",
        "FACEBOOK_PAGE_ACCESS_TOKEN",
        "FACEBOOK_ACCESS_TOKEN",
        "TIKTOK_ACCESS_TOKEN",
    ]
    for key in global_keys:
        if key not in out and os.getenv(key):
            out[key] = str(os.getenv(key))
    return out


def upload_options_payload() -> list[dict[str, Any]]:
    return [
        {
            "upload_profile_id": item.upload_profile_id,
            "name": item.name,
            "platform": item.platform,
            "enabled": item.enabled,
            "description": item.description,
        }
        for item in list_upload_options()
    ]
