from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

import httpx
from fastapi import HTTPException
from sqlmodel import Session, delete, select

from app.core.config import ROOT_DIR
from app.core.paths import localops_data_dir
from app.db.session import engine
from app.modules.localops.memory import append_memory_delta, upsert_location_entry
from app.modules.memory.service import compact_memory, write_relationship, write_session_index
from app.services.ollama_client import OllamaClient, OllamaEndpoint, OllamaEvent, OllamaTelemetry
from app.models.localops import (
    LocalOpsMessage,
    LocalOpsProvider,
    LocalOpsRun,
    LocalOpsSettings,
    LocalOpsThread,
    LocalOpsToolCall,
    LocalOpsWorkspace,
)


DATA_DIR = localops_data_dir()
RUNS_DIR = DATA_DIR / "runs"
TOKENS_PATH = DATA_DIR / "openai_tokens.json"
OPENAI_KEY_PATH = DATA_DIR / "openai_api_key.json"
OAUTH_STATE_PATH = DATA_DIR / "oauth_states.json"
DEVICE_FLOW_PATH = DATA_DIR / "openai_device_flows.json"
AGENTS_DIR = ROOT_DIR / "localops" / "agents"
PROMPTS_DIR = ROOT_DIR / "localops" / "prompts"
AGENT_SESSIONS_DIR = DATA_DIR / "agent_sessions"
AGENT_SESSIONS_INDEX_PATH = DATA_DIR / "agent_sessions.json"
OLLAMA_CLIENT = OllamaClient(timeout_seconds=120.0)


def _now() -> datetime:
    return datetime.utcnow()


def _utc_epoch() -> int:
    return int(time.time())


def _json_load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _json_write_secure(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _jloads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _jdumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _as_int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _normalize_provider_id(value: str) -> str:
    v = str(value or "").strip().lower()
    if v in {"openai_oauth", "openai-api", "openai_api", "openai"}:
        return "openai"
    if v == "ollama":
        return "ollama"
    return "openai"


def _mask_secret(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 10:
        return "*" * len(raw)
    return f"{raw[:6]}...{raw[-4:]}"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def ensure_settings(session: Session) -> LocalOpsSettings:
    row = session.get(LocalOpsSettings, 1)
    if row:
        return row
    row = LocalOpsSettings()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def settings_to_dict(row: LocalOpsSettings) -> dict[str, Any]:
    return {
        "default_provider_id": _normalize_provider_id(row.default_provider_id),
        "default_model": row.default_model,
        "execution_mode": row.execution_mode,
        "max_tool_steps_per_run": row.max_tool_steps_per_run,
        "max_run_seconds": row.max_run_seconds,
        "max_concurrent_runs": row.max_concurrent_runs,
        "terminal_idle_timeout_minutes": row.terminal_idle_timeout_minutes,
        "allow_shell_exec": row.allow_shell_exec,
        "shell_allowlist": _jloads(row.shell_allowlist_json, []),
    }


def update_settings(session: Session, payload: dict[str, Any]) -> LocalOpsSettings:
    row = ensure_settings(session)
    row.default_provider_id = _normalize_provider_id(str(payload.get("default_provider_id", row.default_provider_id)))
    row.default_model = str(payload.get("default_model", row.default_model))
    row.execution_mode = str(payload.get("execution_mode", row.execution_mode))
    row.max_tool_steps_per_run = int(payload.get("max_tool_steps_per_run", row.max_tool_steps_per_run))
    row.max_run_seconds = int(payload.get("max_run_seconds", row.max_run_seconds))
    row.max_concurrent_runs = int(payload.get("max_concurrent_runs", row.max_concurrent_runs))
    row.terminal_idle_timeout_minutes = int(payload.get("terminal_idle_timeout_minutes", row.terminal_idle_timeout_minutes))
    row.allow_shell_exec = bool(payload.get("allow_shell_exec", row.allow_shell_exec))
    row.shell_allowlist_json = _jdumps(payload.get("shell_allowlist", _jloads(row.shell_allowlist_json, [])))
    row.updated_at = _now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def provider_to_dict(row: LocalOpsProvider) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider_id": _normalize_provider_id(row.provider_id),
        "name": row.name,
        "base_url": row.base_url,
        "enabled": row.enabled,
        "default_for_agents": row.default_for_agents,
        "extra": _jloads(row.extra_json, {}),
    }


def list_providers(session: Session) -> list[dict[str, Any]]:
    rows = session.exec(select(LocalOpsProvider).order_by(LocalOpsProvider.id.asc())).all()
    return [provider_to_dict(r) for r in rows]


def create_provider(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    row = LocalOpsProvider(
        provider_id=_normalize_provider_id(str(payload.get("provider_id", "ollama"))),
        name=str(payload.get("name", "")),
        base_url=str(payload.get("base_url", "")),
        api_key=str(payload.get("api_key", "")),
        enabled=bool(payload.get("enabled", True)),
        default_for_agents=bool(payload.get("default_for_agents", False)),
        extra_json=_jdumps(payload.get("extra", {})),
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return provider_to_dict(row)


def update_provider(session: Session, provider_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = session.get(LocalOpsProvider, provider_id)
    if not row:
        raise HTTPException(status_code=404, detail="provider not found")
    row.provider_id = _normalize_provider_id(str(payload.get("provider_id", row.provider_id)))
    row.name = str(payload.get("name", row.name))
    row.base_url = str(payload.get("base_url", row.base_url))
    row.api_key = str(payload.get("api_key", row.api_key))
    row.enabled = bool(payload.get("enabled", row.enabled))
    row.default_for_agents = bool(payload.get("default_for_agents", row.default_for_agents))
    row.extra_json = _jdumps(payload.get("extra", _jloads(row.extra_json, {})))
    row.updated_at = _now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return provider_to_dict(row)


def delete_provider(session: Session, provider_id: int) -> None:
    row = session.get(LocalOpsProvider, provider_id)
    if row:
        session.delete(row)
        session.commit()


def set_openai_api_key(api_key: str) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="api_key is required")
    _json_write_secure(OPENAI_KEY_PATH, {"api_key": key, "updated_at": _utc_epoch()})
    return openai_api_key_status()


def clear_openai_api_key() -> dict[str, Any]:
    if OPENAI_KEY_PATH.exists():
        OPENAI_KEY_PATH.unlink()
    return openai_api_key_status()


def openai_api_key_status() -> dict[str, Any]:
    env_key = _env("OPENAI_API_KEY")
    if env_key:
        return {"configured": True, "source": "env", "masked": _mask_secret(env_key)}
    payload = _json_load(OPENAI_KEY_PATH, {})
    file_key = str(payload.get("api_key", "")).strip() if isinstance(payload, dict) else ""
    if file_key:
        return {"configured": True, "source": "file", "masked": _mask_secret(file_key)}
    return {"configured": False, "source": "", "masked": ""}


def _get_openai_api_key() -> str:
    env_key = _env("OPENAI_API_KEY")
    if env_key:
        return env_key
    payload = _json_load(OPENAI_KEY_PATH, {})
    file_key = str(payload.get("api_key", "")).strip() if isinstance(payload, dict) else ""
    if file_key:
        return file_key
    raise HTTPException(status_code=400, detail="OpenAI API key is not configured")


def _oauth_cfg() -> dict[str, str]:
    base = _env("DASHBURG_BASE_URL", "http://127.0.0.1:8321")
    return {
        "client_id": _env("OPENAI_OAUTH_CLIENT_ID"),
        "client_secret": _env("OPENAI_OAUTH_CLIENT_SECRET"),
        "auth_url": _env("OPENAI_OAUTH_AUTH_URL", "https://auth.openai.com/oauth/authorize"),
        "token_url": _env("OPENAI_OAUTH_TOKEN_URL", "https://auth.openai.com/oauth/token"),
        "scopes": _env("OPENAI_OAUTH_SCOPES", "openid profile email offline_access"),
        "redirect_url": _env("OPENAI_OAUTH_REDIRECT_URL", f"{base}/api/localops/openai/oauth/callback"),
        "device_url": _env("OPENAI_OAUTH_DEVICE_URL"),
    }


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _make_pkce_pair() -> tuple[str, str]:
    verifier = _b64url(os.urandom(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("utf-8")).digest())
    return verifier, challenge


def openai_oauth_capabilities() -> dict[str, Any]:
    cfg = _oauth_cfg()
    missing_common: list[str] = []
    if not cfg["client_id"]:
        missing_common.append("OPENAI_OAUTH_CLIENT_ID")
    if not cfg["token_url"]:
        missing_common.append("OPENAI_OAUTH_TOKEN_URL")

    missing_auth = list(missing_common)
    if not cfg["auth_url"]:
        missing_auth.append("OPENAI_OAUTH_AUTH_URL")
    if not cfg["redirect_url"]:
        missing_auth.append("OPENAI_OAUTH_REDIRECT_URL")
    missing_authorize_link = []
    if not cfg["client_id"]:
        missing_authorize_link.append("OPENAI_OAUTH_CLIENT_ID")
    if not cfg["auth_url"]:
        missing_authorize_link.append("OPENAI_OAUTH_AUTH_URL")
    if not cfg["redirect_url"]:
        missing_authorize_link.append("OPENAI_OAUTH_REDIRECT_URL")

    missing_device = list(missing_common)
    if not cfg["device_url"]:
        missing_device.append("OPENAI_OAUTH_DEVICE_URL")

    return {
        "oauth_redirect_ready": len(missing_auth) == 0,
        "oauth_device_ready": len(missing_device) == 0,
        "oauth_authorize_link_ready": len(missing_authorize_link) == 0,
        "missing_for_redirect": missing_auth,
        "missing_for_device": missing_device,
        "missing_for_authorize_link": missing_authorize_link,
        "redirect_url": cfg["redirect_url"],
        "auth_url": cfg["auth_url"],
        "device_url": cfg["device_url"],
    }


def build_openai_oauth_start_url() -> str:
    cfg = _oauth_cfg()
    if not cfg["client_id"]:
        raise HTTPException(status_code=400, detail="OPENAI_OAUTH_CLIENT_ID is not configured")
    state = secrets.token_urlsafe(24)
    code_verifier, code_challenge = _make_pkce_pair()
    states = _json_load(OAUTH_STATE_PATH, {})
    if not isinstance(states, dict):
        states = {}
    states[state] = {"created_at": _utc_epoch(), "code_verifier": code_verifier, "redirect_uri": cfg["redirect_url"]}
    _json_write_secure(OAUTH_STATE_PATH, states)
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_url"],
        "scope": cfg["scopes"],
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{cfg['auth_url']}?{urlencode(params)}"


def build_openai_oauth_authorize_link() -> dict[str, Any]:
    # Use the same URL generation as redirect flow to keep behavior consistent.
    url = build_openai_oauth_start_url()
    cfg = _oauth_cfg()
    return {
        "authorize_url": url,
        "redirect_url": cfg["redirect_url"],
        "instructions": "Open authorize_url, approve access, then paste the final redirected URL (with code and state) into 'Exchange URL'.",
    }


def _consume_oauth_state(state: str) -> dict[str, Any]:
    states = _json_load(OAUTH_STATE_PATH, {})
    if not isinstance(states, dict):
        raise HTTPException(status_code=400, detail="invalid oauth state")
    raw = states.pop(state, None)
    _json_write_secure(OAUTH_STATE_PATH, states)
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="invalid oauth state")
    age = _utc_epoch() - int(raw.get("created_at", 0))
    if age > 600:
        raise HTTPException(status_code=400, detail="oauth state expired")
    return raw


def _extract_account_id_from_token(access_token: str) -> str:
    token = str(access_token or "").strip()
    if not token or token.count(".") < 2:
        return ""
    try:
        payload_part = token.split(".")[1]
        payload_part += "=" * ((4 - len(payload_part) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_part.encode("utf-8")).decode("utf-8", errors="replace"))
    except Exception:
        return ""
    for key in ("accountId", "account_id", "aid"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    sub = payload.get("sub")
    return str(sub).strip() if isinstance(sub, str) else ""


def _http_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, data: dict[str, Any] | None = None, timeout: float = 20.0) -> dict[str, Any]:
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    body = None
    if data is not None:
        body = urlencode({k: v for k, v in data.items() if v is not None}).encode("utf-8")
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(url, method=method, headers=req_headers, data=body)
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def openai_oauth_callback(code: str, state: str) -> dict[str, Any]:
    state_payload = _consume_oauth_state(state)
    cfg = _oauth_cfg()
    token_payload: dict[str, Any] = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": cfg["client_id"],
        "redirect_uri": str(state_payload.get("redirect_uri") or cfg["redirect_url"]),
        "code_verifier": str(state_payload.get("code_verifier") or ""),
    }
    # Support confidential clients when configured; PKCE works without this for public clients.
    if cfg["client_secret"]:
        token_payload["client_secret"] = cfg["client_secret"]
    payload = _http_json(
        cfg["token_url"],
        method="POST",
        data=token_payload,
    )
    access_token = str(payload.get("access_token", ""))
    tokens = {
        "access_token": access_token,
        "refresh_token": str(payload.get("refresh_token", "")),
        "token_type": str(payload.get("token_type", "Bearer")),
        "scope": str(payload.get("scope", "")),
        "expires_at": _utc_epoch() + int(payload.get("expires_in", 3600)),
        "obtained_at": _utc_epoch(),
        "account_id": _extract_account_id_from_token(access_token),
    }
    _json_write_secure(TOKENS_PATH, tokens)
    return {"connected": bool(tokens["access_token"]), "expires_at": tokens["expires_at"], "has_refresh_token": bool(tokens["refresh_token"])}


def openai_oauth_exchange_callback_url(callback_url: str) -> dict[str, Any]:
    parsed = urlparse(callback_url)
    query = parse_qs(parsed.query)
    code = (query.get("code") or [""])[0]
    state = (query.get("state") or [""])[0]
    if not code or not state:
        raise HTTPException(status_code=400, detail="callback URL must include code and state")
    return openai_oauth_callback(code, state)


def openai_import_token(token_input: str) -> dict[str, Any]:
    raw = str(token_input or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="token_input is required")

    access_token = ""
    refresh_token = ""
    token_type = "Bearer"
    expires_in = 3600

    if "access_token=" in raw:
        parsed = urlparse(raw)
        query = parse_qs(parsed.query)
        fragment = parse_qs(parsed.fragment)

        def pick(name: str) -> str:
            qv = (query.get(name) or [""])[0]
            fv = (fragment.get(name) or [""])[0]
            return str(qv or fv or "").strip()

        access_token = pick("access_token")
        refresh_token = pick("refresh_token")
        token_type = pick("token_type") or token_type
        expires_raw = pick("expires_in")
        try:
            expires_in = int(expires_raw or "3600")
        except Exception:
            expires_in = 3600
    else:
        access_token = raw

    if not access_token:
        raise HTTPException(status_code=400, detail="Could not find access_token in token_input")

    tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": token_type,
        "scope": "",
        "expires_at": _utc_epoch() + max(300, int(expires_in)),
        "obtained_at": _utc_epoch(),
        "account_id": _extract_account_id_from_token(access_token),
    }
    _json_write_secure(TOKENS_PATH, tokens)
    return {"connected": True, "expires_at": tokens["expires_at"], "has_refresh_token": bool(refresh_token)}


def disconnect_openai_oauth() -> None:
    if TOKENS_PATH.exists():
        TOKENS_PATH.unlink()


def openai_oauth_status() -> dict[str, Any]:
    payload = _json_load(TOKENS_PATH, {})
    if not isinstance(payload, dict) or not payload.get("access_token"):
        return {"connected": False, "expires_at": None, "has_refresh_token": False, "token_type": ""}
    return {
        "connected": True,
        "expires_at": int(payload.get("expires_at") or 0) or None,
        "has_refresh_token": bool(payload.get("refresh_token")),
        "token_type": str(payload.get("token_type", "")),
        "account_id": str(payload.get("account_id", "")),
    }


def openai_device_start() -> dict[str, Any]:
    cfg = _oauth_cfg()
    if not cfg["client_id"] or not cfg["device_url"]:
        raise HTTPException(status_code=400, detail="Device flow is not configured (need OPENAI_OAUTH_CLIENT_ID and OPENAI_OAUTH_DEVICE_URL)")
    payload = _http_json(
        cfg["device_url"],
        method="POST",
        data={"client_id": cfg["client_id"], "scope": cfg["scopes"]},
    )
    device_code = str(payload.get("device_code", "")).strip()
    if not device_code:
        raise HTTPException(status_code=502, detail="Device authorization response missing device_code")
    flow_id = secrets.token_hex(12)
    flows = _json_load(DEVICE_FLOW_PATH, {})
    if not isinstance(flows, dict):
        flows = {}
    expires_in = int(payload.get("expires_in", 900) or 900)
    flows[flow_id] = {
        "device_code": device_code,
        "created_at": _utc_epoch(),
        "expires_at": _utc_epoch() + expires_in,
        "interval": int(payload.get("interval", 5) or 5),
    }
    _json_write_secure(DEVICE_FLOW_PATH, flows)
    return {
        "flow_id": flow_id,
        "user_code": str(payload.get("user_code", "")),
        "verification_uri": str(payload.get("verification_uri", "")),
        "verification_uri_complete": str(payload.get("verification_uri_complete", "")),
        "expires_in": expires_in,
        "interval": int(payload.get("interval", 5) or 5),
    }


def openai_device_poll(flow_id: str) -> dict[str, Any]:
    cfg = _oauth_cfg()
    flows = _json_load(DEVICE_FLOW_PATH, {})
    if not isinstance(flows, dict):
        flows = {}
    flow = flows.get(flow_id)
    if not isinstance(flow, dict):
        raise HTTPException(status_code=404, detail="device flow not found")
    if int(flow.get("expires_at", 0)) <= _utc_epoch():
        flows.pop(flow_id, None)
        _json_write_secure(DEVICE_FLOW_PATH, flows)
        return {"status": "expired"}

    try:
        token_payload: dict[str, Any] = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": str(flow.get("device_code", "")),
            "client_id": cfg["client_id"],
        }
        # Some OAuth providers require client_secret, others (public clients) do not.
        if cfg["client_secret"]:
            token_payload["client_secret"] = cfg["client_secret"]

        token_resp = _http_json(
            cfg["token_url"],
            method="POST",
            data=token_payload,
        )
    except HTTPException:
        raise
    except Exception as exc:
        msg = str(exc)
        if "authorization_pending" in msg:
            return {"status": "pending", "interval": int(flow.get("interval", 5) or 5)}
        if "slow_down" in msg:
            return {"status": "pending", "interval": max(8, int(flow.get("interval", 5) or 5) + 3)}
        raise HTTPException(status_code=502, detail=f"Device token poll failed: {exc}") from exc

    access_token = str(token_resp.get("access_token", "")).strip()
    if not access_token:
        # oauth servers can return explicit error JSON with 200s
        err = str(token_resp.get("error", "")).strip()
        if err in {"authorization_pending", "slow_down"}:
            return {"status": "pending", "interval": int(flow.get("interval", 5) or 5)}
        return {"status": "failed", "error": err or "missing access_token"}

    tokens = {
        "access_token": access_token,
        "refresh_token": str(token_resp.get("refresh_token", "")),
        "token_type": str(token_resp.get("token_type", "Bearer")),
        "scope": str(token_resp.get("scope", "")),
        "expires_at": _utc_epoch() + int(token_resp.get("expires_in", 3600)),
        "obtained_at": _utc_epoch(),
        "account_id": _extract_account_id_from_token(access_token),
    }
    _json_write_secure(TOKENS_PATH, tokens)
    flows.pop(flow_id, None)
    _json_write_secure(DEVICE_FLOW_PATH, flows)
    return {"status": "connected", "expires_at": tokens["expires_at"], "has_refresh_token": bool(tokens["refresh_token"])}


def _refresh_openai_token_if_needed() -> str:
    payload = _json_load(TOKENS_PATH, {})
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise HTTPException(status_code=401, detail="OpenAI OAuth is not connected")
    access = str(payload.get("access_token", ""))
    expires_at = int(payload.get("expires_at", 0) or 0)
    if expires_at > _utc_epoch() + 60:
        return access
    refresh = str(payload.get("refresh_token", "")).strip()
    if not refresh:
        raise HTTPException(status_code=401, detail="OpenAI token expired; reconnect OAuth")
    cfg = _oauth_cfg()
    try:
        token_resp = _http_json(
            cfg["token_url"],
            method="POST",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"OpenAI token refresh failed: {exc}") from exc
    new_access = str(token_resp.get("access_token", "")).strip()
    if not new_access:
        raise HTTPException(status_code=401, detail="OpenAI token refresh failed: missing access_token")
    payload["access_token"] = new_access
    payload["expires_at"] = _utc_epoch() + int(token_resp.get("expires_in", 3600))
    if token_resp.get("refresh_token"):
        payload["refresh_token"] = str(token_resp["refresh_token"])
    payload["token_type"] = str(token_resp.get("token_type", payload.get("token_type", "Bearer")))
    payload["account_id"] = _extract_account_id_from_token(new_access)
    _json_write_secure(TOKENS_PATH, payload)
    return new_access


def _provider_to_ollama_endpoint(provider: LocalOpsProvider) -> OllamaEndpoint:
    label = str(provider.name or "").strip() or f"ollama-{provider.id}"
    return OllamaEndpoint(endpoint_id=provider.id, label=label, base_url=str(provider.base_url or "").strip(), api_key=str(provider.api_key or "").strip())


def _ollama_json(base_url: str, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 15.0) -> dict[str, Any]:
    endpoint = OllamaEndpoint(endpoint_id=None, label="ad-hoc", base_url=str(base_url or "").strip(), api_key="")
    return OLLAMA_CLIENT.request_json(endpoint, path, method=method, payload=payload, timeout=timeout)


def test_ollama(base_url: str) -> dict[str, Any]:
    version = _ollama_json(base_url, "/api/version", timeout=8.0)
    tags = _ollama_json(base_url, "/api/tags", timeout=8.0)
    models = tags.get("models", []) if isinstance(tags, dict) else []
    return {"ok": True, "version": version, "models_count": len(models)}


def list_ollama_models(base_url: str) -> list[str]:
    tags = _ollama_json(base_url, "/api/tags", timeout=10.0)
    items = tags.get("models", []) if isinstance(tags, dict) else []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name:
                out.append(name)
    return out


def list_openai_models() -> list[str]:
    return ["gpt-5.1", "gpt-5.2", "gpt-5.3", "gpt-5-mini", "gpt-4o", "gpt-4o-mini"]


def _openai_api_base_url() -> str:
    raw = _env("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
    parsed = urlparse(raw)
    if parsed.scheme.lower() == "http" and parsed.netloc.lower().endswith("openai.com"):
        raw = f"https://{parsed.netloc}{parsed.path or ''}"
    return raw.rstrip("/")


def _openai_chat(provider_model: str, messages: list[dict[str, str]]) -> str:
    token = _get_openai_api_key()
    endpoint = f"{_openai_api_base_url()}/chat/completions"
    req = Request(
        endpoint,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps({"model": provider_model, "messages": messages, "temperature": 0.2}).encode("utf-8"),
    )
    try:
        # Ignore host-level proxy env vars for OpenAI calls; they can break TLS handshakes.
        opener = build_opener(ProxyHandler({}))
        with opener.open(req, timeout=60.0) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        hint = ""
        message = str(exc)
        if "WRONG_VERSION_NUMBER" in message.upper() and endpoint.startswith("http://"):
            hint = " (OPENAI_API_BASE_URL appears to use http://; use https://)"
        raise HTTPException(status_code=502, detail=f"OpenAI chat failed: {message}{hint}") from exc
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    return str((message or {}).get("content") or "")


def _ollama_chat(base_url: str, provider_model: str, messages: list[dict[str, str]]) -> str:
    payload = _ollama_json(
        base_url,
        "/api/chat",
        method="POST",
        payload={"model": provider_model, "messages": messages, "stream": False},
        timeout=120.0,
    )
    message = payload.get("message") if isinstance(payload, dict) else {}
    return str((message or {}).get("content") or "")


def _choose_ollama_provider(session: Session, run: LocalOpsRun) -> tuple[LocalOpsProvider, list[LocalOpsProvider]]:
    providers = session.exec(
        select(LocalOpsProvider)
        .where(LocalOpsProvider.provider_id == "ollama", LocalOpsProvider.enabled == True)
        .order_by(LocalOpsProvider.default_for_agents.desc(), LocalOpsProvider.id.asc())
    ).all()
    if not providers:
        raise HTTPException(status_code=400, detail="No enabled Ollama provider configured")
    selected: LocalOpsProvider | None = None
    if run.provider_endpoint_id is not None:
        for p in providers:
            if p.id == run.provider_endpoint_id:
                selected = p
                break
    if selected is None:
        selected = providers[0]
    fallback = [p for p in providers if p.id != selected.id]
    return selected, fallback


TOOL_RE = re.compile(r"```localops_tool\s*(\{.*?\})\s*```", re.S)


def parse_tool_blocks(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for match in TOOL_RE.finditer(text or ""):
        raw = match.group(1)
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("tool"):
            out.append(obj)
    return out


def _safe_rel(path: str) -> str:
    p = str(path or "").replace("\\", "/").strip().lstrip("/")
    if ".." in p.split("/"):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    return p


def _workspace_root(run_id: str) -> Path:
    return RUNS_DIR / run_id / "workspace"


def _workspace_path(run_id: str, rel_path: str) -> Path:
    root = _workspace_root(run_id).resolve()
    target = (root / _safe_rel(rel_path)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path escapes workspace") from exc
    return target


def _list_files(path: Path) -> list[str]:
    if not path.exists():
        return []
    if path.is_file():
        return [path.name]
    out: list[str] = []
    for p in sorted(path.rglob("*")):
        if p.is_file():
            out.append(str(p.relative_to(path)))
    return out


def list_agent_packs() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not AGENTS_DIR.exists():
        return items
    for entry in sorted(AGENTS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        instructions = entry / "INSTRUCTIONS.md"
        title = entry.name
        if instructions.exists():
            try:
                first = instructions.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip("# ").strip()
                if first:
                    title = first
            except Exception:
                pass
        items.append(
            {
                "slug": entry.name,
                "title": title,
                "has_instructions": instructions.exists(),
                "has_skill": (entry / "SKILL.md").exists(),
            }
        )
    return items


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-")
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")
    return slug


def _pack_payload(slug: str) -> dict[str, Any]:
    pack = AGENTS_DIR / slug
    if not pack.exists():
        raise HTTPException(status_code=404, detail=f"agent pack not found: {slug}")
    instructions = pack / "INSTRUCTIONS.md"
    tooling = pack / "TOOLING.md"
    skill = pack / "SKILL.md"
    title = slug
    if instructions.exists():
        first = instructions.read_text(encoding="utf-8", errors="replace").splitlines()
        if first:
            title = first[0].strip("# ").strip() or slug
    return {
        "slug": slug,
        "title": title,
        "has_instructions": instructions.exists(),
        "has_skill": skill.exists(),
        "instructions": instructions.read_text(encoding="utf-8", errors="replace") if instructions.exists() else "",
        "tooling": tooling.read_text(encoding="utf-8", errors="replace") if tooling.exists() else "",
        "skill_md": skill.read_text(encoding="utf-8", errors="replace") if skill.exists() else "",
    }


def create_or_update_agent_pack(
    slug: str,
    title: str,
    instructions: str,
    tooling: str = "",
    skill_md: str = "",
) -> dict[str, Any]:
    ensure_dirs()
    safe_slug = _safe_slug(slug)
    pack = AGENTS_DIR / safe_slug
    pack.mkdir(parents=True, exist_ok=True)
    body = str(instructions or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="instructions are required")
    header = str(title or "").strip() or safe_slug
    (pack / "INSTRUCTIONS.md").write_text(f"# {header}\n\n{body}\n", encoding="utf-8")
    if str(tooling or "").strip():
        (pack / "TOOLING.md").write_text(str(tooling).strip() + "\n", encoding="utf-8")
    if str(skill_md or "").strip():
        (pack / "SKILL.md").write_text(str(skill_md).strip() + "\n", encoding="utf-8")
    return _pack_payload(safe_slug)


def _agent_sessions_index() -> list[dict[str, Any]]:
    raw = _json_load(AGENT_SESSIONS_INDEX_PATH, [])
    return raw if isinstance(raw, list) else []


def _write_agent_sessions_index(rows: list[dict[str, Any]]) -> None:
    _json_write_secure(AGENT_SESSIONS_INDEX_PATH, {"items": rows})


def _read_agent_sessions_index() -> list[dict[str, Any]]:
    raw = _json_load(AGENT_SESSIONS_INDEX_PATH, {})
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        items = raw.get("items")
        if isinstance(items, list):
            return items
    return []


def list_agent_sessions() -> list[dict[str, Any]]:
    return sorted(_read_agent_sessions_index(), key=lambda r: str(r.get("updated_at", "")), reverse=True)


def create_agent_session(
    agent_slug: str,
    title: str = "",
    seed_markdown: str = "",
    agent_name: str = "",
    workspace_root: str = "",
    codex_model: str = "gpt-5.3-codex",
) -> dict[str, Any]:
    ensure_dirs()
    slug = str(agent_slug or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="agent_slug is required")
    pack = AGENTS_DIR / slug
    if not pack.exists() or not pack.is_dir():
        raise HTTPException(status_code=404, detail=f"agent pack not found: {slug}")

    sid = secrets.token_hex(12)
    root_in = str(workspace_root or "").strip()
    if root_in:
        base_root = Path(root_in).expanduser()
        if not base_root.is_absolute():
            base_root = (DATA_DIR / base_root).resolve()
    else:
        base_root = AGENT_SESSIONS_DIR
    base = (base_root / sid).resolve()
    workspace = base / "workspace"
    logs = base / "logs"
    workspace.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    instructions = pack / "INSTRUCTIONS.md"
    if instructions.exists():
        shutil.copy2(instructions, workspace / "AGENT.md")
    input_rel = "INPUT.md"
    output_rel = "OUTPUT.md"
    state_rel = "STATE.md"
    memory_rel = "MEM.md"
    notes_rel = "NOTES.md"
    investigations_rel = "INVESTIGATIONS.md"
    host_profile_rel = "HOST_PROFILE.md"
    repo_profile_rel = "REPO_PROFILE.md"
    input_path = workspace / input_rel
    output_path = workspace / output_rel
    state_path = workspace / state_rel
    memory_path = workspace / memory_rel
    notes_path = workspace / notes_rel
    investigations_path = workspace / investigations_rel
    host_profile_path = workspace / host_profile_rel
    repo_profile_path = workspace / repo_profile_rel
    input_path.write_text(seed_markdown or "# Input\n\n", encoding="utf-8")
    if not output_path.exists():
        output_path.write_text("# Output\n\n", encoding="utf-8")
    if not state_path.exists():
        state_path.write_text("# State\n\n- status: idle\n", encoding="utf-8")
    if not memory_path.exists():
        memory_path.write_text("# Memory\n\n", encoding="utf-8")
    if not notes_path.exists():
        notes_path.write_text("# Notes\n\n", encoding="utf-8")
    if not investigations_path.exists():
        investigations_path.write_text(
            "# Investigations\n\n"
            "Use this log to append timestamped remote/local investigation summaries.\n\n",
            encoding="utf-8",
        )
    if not host_profile_path.exists():
        host_profile_path.write_text(
            "# Host Profile\n\n"
            "## Access\n\n"
            "## Services\n\n"
            "## Settings\n\n"
            "## Known Issues\n\n",
            encoding="utf-8",
        )
    if not repo_profile_path.exists():
        repo_profile_path.write_text(
            "# Repo Profile\n\n"
            "## Layout\n\n"
            "## Entrypoints\n\n"
            "## Config Paths\n\n"
            "## Known Issues / Fixes\n\n",
            encoding="utf-8",
        )

    now_iso = datetime.utcnow().isoformat() + "Z"
    row = {
        "id": sid,
        "agent_slug": slug,
        "name": (agent_name.strip() if agent_name else ""),
        "title": (title.strip() or slug),
        "codex_model": str(codex_model or "gpt-5.3-codex").strip(),
        "workspace_root": str(base_root),
        "workspace_path": str(workspace),
        "input_file": input_rel,
        "output_file": output_rel,
        "state_file": state_rel,
        "memory_file": memory_rel,
        "notes_file": notes_rel,
        "investigations_file": investigations_rel,
        "host_profile_file": host_profile_rel,
        "repo_profile_file": repo_profile_rel,
        "target_node_id": "",
        "target_repo_path": "",
        "target_repo_purpose": "",
        "log_file": "logs/codex.log",
        "status": "idle",
        "last_result": {},
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    rows = _read_agent_sessions_index()
    rows.append(row)
    _write_agent_sessions_index(rows)
    return row


def get_agent_session(session_id: str) -> dict[str, Any]:
    sid = str(session_id or "").strip()
    for row in _read_agent_sessions_index():
        if str(row.get("id", "")) == sid:
            return row
    raise HTTPException(status_code=404, detail="agent session not found")


def update_agent_session(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_agent_session(session_id)
    ws = Path(str(row.get("workspace_path", ""))).resolve()
    if not ws.exists():
        raise HTTPException(status_code=404, detail="agent workspace not found")

    def _set_rel(name: str, default_value: str) -> None:
        if name not in payload:
            return
        rel = _safe_rel(str(payload.get(name) or default_value))
        row[name] = rel
        target = ws / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text("", encoding="utf-8")

    if "name" in payload:
        row["name"] = str(payload.get("name") or "").strip()
    if "title" in payload:
        row["title"] = str(payload.get("title") or row.get("title", "")).strip() or str(row.get("agent_slug", "agent"))
    if "codex_model" in payload:
        row["codex_model"] = str(payload.get("codex_model") or "gpt-5.3-codex").strip()
    if "target_node_id" in payload:
        row["target_node_id"] = str(payload.get("target_node_id") or "").strip()
    if "target_repo_path" in payload:
        row["target_repo_path"] = str(payload.get("target_repo_path") or "").strip()
    if "target_repo_purpose" in payload:
        row["target_repo_purpose"] = str(payload.get("target_repo_purpose") or "").strip()
    _set_rel("input_file", "INPUT.md")
    _set_rel("output_file", "OUTPUT.md")
    _set_rel("state_file", "STATE.md")
    _set_rel("memory_file", "MEM.md")
    _set_rel("notes_file", "NOTES.md")
    _set_rel("investigations_file", "INVESTIGATIONS.md")
    _set_rel("host_profile_file", "HOST_PROFILE.md")
    _set_rel("repo_profile_file", "REPO_PROFILE.md")

    row["updated_at"] = datetime.utcnow().isoformat() + "Z"
    return _save_agent_session(row)


def _run_codex_cmd(
    cwd: Path,
    prompt: str,
    sandbox_mode: str,
    timeout_s: int,
    codex_model: str = "",
) -> subprocess.CompletedProcess[str]:
    base_cmd = ["codex", "exec", "-s", sandbox_mode]
    model = str(codex_model or "").strip()
    cmd = [*base_cmd, prompt]
    if model:
        cmd = [*base_cmd, "--model", model, prompt]
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=max(30, int(timeout_s)),
        check=False,
    )
    if model and proc.returncode != 0 and "unknown option" in (proc.stderr or "").lower():
        proc = subprocess.run(
            [*base_cmd, prompt],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=max(30, int(timeout_s)),
            check=False,
        )
    return proc


def _save_agent_session(updated: dict[str, Any]) -> dict[str, Any]:
    sid = str(updated.get("id", ""))
    rows = _read_agent_sessions_index()
    found = False
    for idx, row in enumerate(rows):
        if str(row.get("id", "")) == sid:
            rows[idx] = updated
            found = True
            break
    if not found:
        rows.append(updated)
    _write_agent_sessions_index(rows)
    return updated


def _record_agent_session_memory_delta(
    row: dict[str, Any],
    *,
    file_key: str,
    path: Path,
    content: str,
) -> None:
    node_id = str(row.get("target_node_id") or "").strip()
    repo_path = str(row.get("target_repo_path") or "").strip()
    repo_purpose = str(row.get("target_repo_purpose") or "").strip()
    normalized_key = str(file_key or "").strip().lower()
    if normalized_key in {"investigations", "host_profile", "repo_profile"} and node_id:
        kwargs: dict[str, str] = {
            "node_id": node_id,
            "repo_path": repo_path or "/",
            "repo_purpose": repo_purpose,
            "notes": f"updated via localops session {str(row.get('id') or '')}",
        }
        if normalized_key == "investigations":
            kwargs["last_investigation_file"] = str(path)
        else:
            kwargs["last_profile_file"] = str(path)
        upsert_location_entry(**kwargs)
    append_memory_delta(
        {
            "kind": "localops.session.file_write",
            "session_id": str(row.get("id") or ""),
            "agent_slug": str(row.get("agent_slug") or ""),
            "node_id": node_id,
            "repo_path": repo_path,
            "file_key": normalized_key,
            "path": str(path),
            "bytes": len(content.encode("utf-8")),
        }
    )
    session_id = str(row.get("id") or "")
    if session_id:
        try:
            write_session_index(
                {
                    "session_id": session_id,
                    "created_at": str(row.get("created_at") or ""),
                    "agent": str(row.get("agent_slug") or ""),
                    "node_id": node_id,
                    "repo_path": repo_path,
                    "files_touched": [str(path)],
                    "jobs": [],
                    "entities": [],
                    "summary": f"LocalOps session file write: {normalized_key}",
                    "keywords": [normalized_key, node_id, repo_path],
                }
            )
            write_relationship(
                {
                    "subject_type": "session",
                    "subject_id": session_id,
                    "relation": "produced",
                    "object_type": "file",
                    "object_id": str(path),
                    "node_id": node_id,
                    "repo_path": repo_path,
                }
            )
        except Exception:
            # Memory indexing should be best-effort and must not break LocalOps writes.
            pass


def _agent_session_file_path(row: dict[str, Any], file_key: str) -> Path:
    ws = Path(str(row.get("workspace_path", ""))).resolve()
    if not ws.exists():
        raise HTTPException(status_code=404, detail="agent workspace not found")
    defaults = {
        "input": ("input_file", "INPUT.md"),
        "output": ("output_file", "OUTPUT.md"),
        "state": ("state_file", "STATE.md"),
        "memory": ("memory_file", "MEM.md"),
        "notes": ("notes_file", "NOTES.md"),
        "investigations": ("investigations_file", "INVESTIGATIONS.md"),
        "host_profile": ("host_profile_file", "HOST_PROFILE.md"),
        "repo_profile": ("repo_profile_file", "REPO_PROFILE.md"),
        "agent": ("agent_file", "AGENT.md"),
    }
    key = str(file_key or "").strip().lower()
    if key not in defaults:
        raise HTTPException(status_code=400, detail=f"unsupported file key: {file_key}")
    row_key, default_rel = defaults[key]
    rel = _safe_rel(str(row.get(row_key) or default_rel))
    path = (ws / rel).resolve()
    try:
        path.relative_to(ws)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="file path escapes workspace") from exc
    return path


def read_agent_session_file(session_id: str, file_key: str) -> dict[str, Any]:
    row = get_agent_session(session_id)
    path = _agent_session_file_path(row, file_key)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    content = path.read_text(encoding="utf-8", errors="replace")
    return {
        "session_id": str(row.get("id", "")),
        "file_key": file_key,
        "path": str(path),
        "content": content,
    }


def write_agent_session_file(session_id: str, file_key: str, content: str) -> dict[str, Any]:
    row = get_agent_session(session_id)
    path = _agent_session_file_path(row, file_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(content or ""), encoding="utf-8")
    row["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _save_agent_session(row)
    _record_agent_session_memory_delta(row, file_key=file_key, path=path, content=str(content or ""))
    return {
        "session_id": str(row.get("id", "")),
        "file_key": file_key,
        "path": str(path),
        "saved": True,
        "bytes": len(str(content or "").encode("utf-8")),
    }


def run_agent_session(session_id: str, task: str, sandbox_mode: str = "workspace-write", timeout_s: int = 600) -> dict[str, Any]:
    row = get_agent_session(session_id)
    ws = Path(str(row.get("workspace_path", ""))).resolve()
    if not ws.exists():
        raise HTTPException(status_code=404, detail="agent workspace not found")
    input_rel = _safe_rel(str(row.get("input_file") or "INPUT.md"))
    output_rel = _safe_rel(str(row.get("output_file") or "OUTPUT.md"))
    state_rel = _safe_rel(str(row.get("state_file") or "STATE.md"))
    memory_rel = _safe_rel(str(row.get("memory_file") or "MEM.md"))
    notes_rel = _safe_rel(str(row.get("notes_file") or "NOTES.md"))
    investigations_rel = _safe_rel(str(row.get("investigations_file") or "INVESTIGATIONS.md"))
    host_profile_rel = _safe_rel(str(row.get("host_profile_file") or "HOST_PROFILE.md"))
    repo_profile_rel = _safe_rel(str(row.get("repo_profile_file") or "REPO_PROFILE.md"))
    codex_model = str(row.get("codex_model") or "gpt-5.3-codex").strip()

    for rel, content in [
        (investigations_rel, "# Investigations\n\n"),
        (host_profile_rel, "# Host Profile\n\n"),
        (repo_profile_rel, "# Repo Profile\n\n"),
    ]:
        target = ws / rel
        if not target.exists():
            target.write_text(content, encoding="utf-8")

    prompt = (
        "You are running inside a LocalOps agent workspace. "
        f"Read {input_rel}, {state_rel}, {memory_rel}, {notes_rel}, {investigations_rel}, {host_profile_rel}, {repo_profile_rel}, and AGENT.md if present. "
        f"Task: {task.strip()} "
        f"Write your final markdown output to {output_rel}. "
        f"Update {state_rel} and {memory_rel} with key learnings and progress. "
        f"Append investigation findings to {investigations_rel}. "
        f"Update {host_profile_rel} and {repo_profile_rel} with durable observations/settings/issues/fixes. "
        "Do not write outside workspace."
    )

    logs_dir = ws.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    proc = _run_codex_cmd(ws, prompt, sandbox_mode, timeout_s, codex_model=codex_model)
    (logs_dir / "codex.log").write_text(
        (proc.stdout or "") + ("\n--- STDERR ---\n" + proc.stderr if proc.stderr else ""),
        encoding="utf-8",
    )
    out_file = ws / output_rel
    out_preview = out_file.read_text(encoding="utf-8", errors="replace")[-4000:] if out_file.exists() else ""
    result = {
        "ok": proc.returncode == 0,
        "rc": proc.returncode,
        "sandbox_mode": sandbox_mode,
        "codex_model": codex_model,
        "workspace_path": str(ws),
        "changed_files": _list_files(ws),
        "output_preview": out_preview,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }

    row["status"] = "idle" if proc.returncode == 0 else "failed"
    row["last_result"] = result
    row["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _save_agent_session(row)

    # Persist shared-memory artifacts for every run so Memory UI is populated
    # even when files were updated by codex exec instead of manual file-save APIs.
    index_keys = [
        "output",
        "state",
        "memory",
        "notes",
        "investigations",
        "host_profile",
        "repo_profile",
    ]
    for key in index_keys:
        try:
            p = _agent_session_file_path(row, key)
            if not p.exists() or not p.is_file():
                continue
            content = p.read_text(encoding="utf-8", errors="replace")
            _record_agent_session_memory_delta(row, file_key=key, path=p, content=content)
        except Exception:
            # Keep LocalOps run path resilient to indexing issues.
            pass

    try:
        compact_memory(
            {
                "candidate": {
                    "session_id": str(row.get("id") or ""),
                    "agent": str(row.get("agent_slug") or ""),
                    "node_id": str(row.get("target_node_id") or ""),
                    "repo_path": str(row.get("target_repo_path") or ""),
                    "summary": out_preview[:800],
                    "body": out_preview[:1200],
                    "source": "localops.run_agent_session",
                }
            },
            limit=1,
            promote=False,
        )
    except Exception:
        # Candidate capture/compaction is best-effort.
        pass

    return {"session": row, "result": result}


def _remoteops_submit_job(args: dict[str, Any]) -> dict[str, Any]:
    node_id = str(args.get("node_id", "")).strip()
    job_type = str(args.get("job_type", "")).strip()
    params = args.get("params", {})
    if not node_id or not job_type:
        raise HTTPException(status_code=400, detail="node_id and job_type are required")
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="params must be an object")

    from app.modules.remote_ops.service import (
        create_remote_job,
        ensure_settings as ensure_remote_settings,
        get_node,
        job_to_payload,
    )

    with Session(engine) as remote_session:
        node = get_node(remote_session, node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"RemoteOps node not found: {node_id}")
        _ = ensure_remote_settings(remote_session)
        row = create_remote_job(remote_session, node=node, job_type=job_type, params=params, created_by="localops")
        append_memory_delta(
            {
                "kind": "remoteops.job.create",
                "node_id": node_id,
                "job_type": job_type,
                "params": params,
                "job_id": str(row.id),
            }
        )
        return {"job": job_to_payload(row)}


def _copy_agent_pack(agent_slug: str, run_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    src = AGENTS_DIR / agent_slug
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"agent pack not found: {agent_slug}")
    run_dir = RUNS_DIR / run_id
    ws = run_dir / "workspace"
    artifacts = ws / "ARTIFACTS"
    logs = run_dir / "logs"
    ws.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    instr = src / "INSTRUCTIONS.md"
    if instr.exists():
        shutil.copy2(instr, ws / "AGENT.md")
    tooling = src / "TOOLING.md"
    if tooling.exists():
        shutil.copy2(tooling, ws / "TOOLING.md")
    (ws / "INPUT.json").write_text(json.dumps(inputs, indent=2), encoding="utf-8")
    return {
        "workspace_id": run_id,
        "workspace_path": str(ws),
        "artifact_dir": str(artifacts),
    }


def _run_codex_exec(run_id: str, prompt: str, timeout_s: int = 600, sandbox_mode: str = "workspace-write") -> dict[str, Any]:
    run_dir = RUNS_DIR / run_id
    ws = run_dir / "workspace"
    logs = run_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if not ws.exists():
        ws.mkdir(parents=True, exist_ok=True)
    proc = _run_codex_cmd(ws, prompt, sandbox_mode, timeout_s)
    (logs / "codex.log").write_text((proc.stdout or "") + ("\n--- STDERR ---\n" + proc.stderr if proc.stderr else ""), encoding="utf-8")
    files = _list_files(ws)
    return {
        "ok": proc.returncode == 0,
        "rc": proc.returncode,
        "workspace_id": run_id,
        "changed_files": files,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def _run_shell(settings: LocalOpsSettings, run_id: str, command: str) -> dict[str, Any]:
    if not settings.allow_shell_exec:
        raise HTTPException(status_code=403, detail="Shell execution is disabled")
    allow = _jloads(settings.shell_allowlist_json, [])
    cmd = str(command or "").strip()
    if not any(cmd.startswith(str(prefix)) for prefix in allow):
        raise HTTPException(status_code=403, detail="Command not allowlisted")
    ws = _workspace_root(run_id)
    ws.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True, shell=True, timeout=120, check=False)
    return {"ok": proc.returncode == 0, "rc": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-2000:]}


def execute_tool(session: Session, settings: LocalOpsSettings, run: LocalOpsRun, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    ws = _workspace_root(run.id)
    ws.mkdir(parents=True, exist_ok=True)
    if tool_name == "localops.spawn_agent":
        agent_slug = str(args.get("agent_slug", "")).strip()
        inputs = args.get("inputs", {})
        if not isinstance(inputs, dict):
            inputs = {"value": inputs}
        res = _copy_agent_pack(agent_slug, run.id, inputs)
        if not session.get(LocalOpsWorkspace, run.id):
            session.add(LocalOpsWorkspace(id=run.id, run_id=run.id, agent_slug=agent_slug, path=str(ws), created_at=_now()))
            session.commit()
        return res
    if tool_name == "localops.codex_exec":
        prompt = str(args.get("prompt", "")).strip()
        timeout_s = int(args.get("timeout_s", 600))
        sandbox_mode = str(args.get("sandbox_mode", "workspace-write"))
        return _run_codex_exec(run.id, prompt, timeout_s=timeout_s, sandbox_mode=sandbox_mode)
    if tool_name == "localops.read_file":
        rel = str(args.get("path", ""))
        target = _workspace_path(run.id, rel)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        return {"path": rel, "content": target.read_text(encoding="utf-8", errors="replace")}
    if tool_name == "localops.write_file":
        rel = str(args.get("path", ""))
        content = str(args.get("content", ""))
        target = _workspace_path(run.id, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": rel, "bytes": len(content.encode("utf-8"))}
    if tool_name == "localops.list_workspace":
        rel = str(args.get("path", "")).strip()
        base = _workspace_path(run.id, rel) if rel else _workspace_root(run.id)
        return {"path": rel or ".", "files": _list_files(base)}
    if tool_name == "localops.exec_shell":
        return _run_shell(settings, run.id, str(args.get("command", "")))
    if tool_name == "localops.remoteops_job":
        return _remoteops_submit_job(args)
    if tool_name == "localops.finish_agent":
        artifacts = _list_files(_workspace_root(run.id) / "ARTIFACTS")
        return {"workspace_id": run.id, "artifacts": artifacts, "next_steps": "Review artifacts and finalize response."}
    raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")


def tool_is_auto_allowlisted(name: str) -> bool:
    return name in {
        "localops.spawn_agent",
        "localops.codex_exec",
        "localops.read_file",
        "localops.write_file",
        "localops.list_workspace",
        "localops.finish_agent",
    }


def create_thread(session: Session, payload: dict[str, Any]) -> LocalOpsThread:
    thread = LocalOpsThread(
        id=secrets.token_hex(16),
        title=str(payload.get("title", "New Thread"))[:200],
        provider_id=_normalize_provider_id(str(payload.get("provider_id", "openai"))),
        provider_endpoint_id=_as_int_or_none(payload.get("provider_endpoint_id")),
        model=str(payload.get("model", "gpt-4o-mini")),
        execution_mode=str(payload.get("execution_mode", "require_confirm")),
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(thread)
    session.commit()
    session.refresh(thread)
    return thread


def list_threads(session: Session) -> list[LocalOpsThread]:
    return session.exec(select(LocalOpsThread).order_by(LocalOpsThread.updated_at.desc())).all()


def get_thread(session: Session, thread_id: str) -> LocalOpsThread | None:
    return session.get(LocalOpsThread, thread_id)


def delete_thread(session: Session, thread_id: str) -> bool:
    thread = session.get(LocalOpsThread, thread_id)
    if not thread:
        return False
    runs = session.exec(select(LocalOpsRun).where(LocalOpsRun.thread_id == thread_id)).all()
    run_ids = [r.id for r in runs]
    if run_ids:
        for run_id in run_ids:
            session.exec(delete(LocalOpsToolCall).where(LocalOpsToolCall.run_id == run_id))
            session.exec(delete(LocalOpsWorkspace).where(LocalOpsWorkspace.run_id == run_id))
    session.exec(delete(LocalOpsMessage).where(LocalOpsMessage.thread_id == thread_id))
    session.exec(delete(LocalOpsRun).where(LocalOpsRun.thread_id == thread_id))
    session.delete(thread)
    session.commit()
    return True


def thread_messages(session: Session, thread_id: str) -> list[LocalOpsMessage]:
    return session.exec(select(LocalOpsMessage).where(LocalOpsMessage.thread_id == thread_id).order_by(LocalOpsMessage.created_at.asc())).all()


def create_message(session: Session, thread_id: str, run_id: str | None, role: str, content: str, meta: dict[str, Any] | None = None) -> LocalOpsMessage:
    row = LocalOpsMessage(
        id=secrets.token_hex(16),
        thread_id=thread_id,
        run_id=run_id,
        role=role,
        content=content,
        meta_json=_jdumps(meta or {}),
        created_at=_now(),
    )
    session.add(row)
    thread = session.get(LocalOpsThread, thread_id)
    if thread:
        thread.updated_at = _now()
        session.add(thread)
    session.commit()
    session.refresh(row)
    return row


def create_run(session: Session, thread: LocalOpsThread, payload: dict[str, Any]) -> LocalOpsRun:
    provider_id = _normalize_provider_id(str(payload.get("provider_id", thread.provider_id)))
    endpoint_id = _as_int_or_none(payload.get("provider_endpoint_id", thread.provider_endpoint_id))
    row = LocalOpsRun(
        id=secrets.token_hex(16),
        thread_id=thread.id,
        status="queued",
        llm_status="queued",
        provider_id=provider_id,
        provider_endpoint_id=endpoint_id,
        endpoint_label="",
        endpoint_url="",
        model=str(payload.get("model", thread.model)),
        request_type="chat",
        telemetry_json=_jdumps(
            {
                "status": "queued",
                "request_type": "chat",
                "endpoint_id": endpoint_id,
                "endpoint_label": "",
                "endpoint_url": "",
                "model": str(payload.get("model", thread.model)),
                "chunk_count": 0,
                "output_char_count": 0,
            }
        ),
        execution_mode=str(payload.get("execution_mode", thread.execution_mode)),
        error="",
        started_at=_now(),
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_run(session: Session, run_id: str) -> LocalOpsRun | None:
    return session.get(LocalOpsRun, run_id)


def run_tool_calls(session: Session, run_id: str) -> list[LocalOpsToolCall]:
    return session.exec(select(LocalOpsToolCall).where(LocalOpsToolCall.run_id == run_id).order_by(LocalOpsToolCall.created_at.asc())).all()


def add_tool_call(session: Session, run_id: str, tool_name: str, args: dict[str, Any], status: str = "pending", result: dict[str, Any] | None = None) -> LocalOpsToolCall:
    row = LocalOpsToolCall(
        id=secrets.token_hex(16),
        run_id=run_id,
        tool_name=tool_name,
        args_json=_jdumps(args),
        result_json=_jdumps(result or {}),
        status=status,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def update_tool_call(session: Session, row: LocalOpsToolCall, *, status: str | None = None, result: dict[str, Any] | None = None) -> LocalOpsToolCall:
    if status:
        row.status = status
    if result is not None:
        row.result_json = _jdumps(result)
    row.updated_at = _now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _message_as_chat(msg: LocalOpsMessage) -> dict[str, str]:
    role = msg.role
    if role not in {"system", "user", "assistant", "tool"}:
        role = "user"
    return {"role": "assistant" if role == "tool" else role, "content": msg.content}


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def build_chat_messages(session: Session, thread_id: str) -> list[dict[str, str]]:
    msgs = thread_messages(session, thread_id)
    system = _load_prompt("system.md")
    tooling = _load_prompt("tools.md")
    out: list[dict[str, str]] = []
    if system:
        out.append({"role": "system", "content": system})
    if tooling:
        out.append({"role": "system", "content": tooling})
    out.extend(_message_as_chat(m) for m in msgs)
    return out


def model_response(session: Session, run: LocalOpsRun) -> str:
    messages = build_chat_messages(session, run.thread_id)
    if _normalize_provider_id(run.provider_id) == "openai":
        return _openai_chat(run.model, messages)
    if _normalize_provider_id(run.provider_id) == "ollama":
        selected, _fallback = _choose_ollama_provider(session, run)
        return _ollama_chat(selected.base_url, run.model, messages)
    raise HTTPException(status_code=400, detail=f"Unsupported provider: {run.provider_id}")


def _set_run_telemetry(session: Session, run: LocalOpsRun, telemetry: dict[str, Any]) -> None:
    run.telemetry_json = _jdumps(telemetry)
    run.updated_at = _now()
    session.add(run)
    session.commit()


async def _ollama_stream_chat(session: Session, run: LocalOpsRun, messages: list[dict[str, str]]) -> tuple[str, OllamaTelemetry]:
    selected, fallback = _choose_ollama_provider(session, run)
    selected_ep = _provider_to_ollama_endpoint(selected)
    fallback_eps = [_provider_to_ollama_endpoint(p) for p in fallback]
    error_chain: list[str] = []

    async def _run_one(endpoint: OllamaEndpoint, fallback_from: OllamaEndpoint | None = None) -> OllamaTelemetry:
        async def on_event(evt: OllamaEvent, telemetry: OllamaTelemetry) -> None:
            run.llm_status = telemetry.status
            run.provider_endpoint_id = telemetry.endpoint_id
            run.endpoint_label = telemetry.endpoint_label
            run.endpoint_url = telemetry.endpoint_url
            if fallback_from is not None:
                telemetry.fallback_endpoint_id = fallback_from.endpoint_id
                telemetry.fallback_endpoint_label = fallback_from.label
            if evt.event_type != "ollama_stream_chunk" or telemetry.chunk_count % 5 == 0:
                _set_run_telemetry(session, run, telemetry.to_json())
            await run_broker.publish(
                run.id,
                "ollama.event",
                {
                    "event_type": evt.event_type,
                    "status": evt.status,
                    "ts_ms": evt.ts_ms,
                    "data": evt.data,
                    "telemetry": telemetry.to_json(),
                },
            )

        async def on_chunk(chunk: str, _telemetry: OllamaTelemetry) -> None:
            await run_broker.publish(run.id, "token", {"chunk": chunk})

        telemetry = await OLLAMA_CLIENT.run_streaming_generation(
            endpoint=endpoint,
            request_type="chat",
            model=run.model,
            payload={"messages": messages},
            route="localops.chat",
            timeout=120.0,
            on_event=on_event,
            on_chunk=on_chunk,
        )
        return telemetry

    try:
        telemetry = await _run_one(selected_ep, None)
        _set_run_telemetry(session, run, telemetry.to_json())
        return telemetry.output_text, telemetry
    except Exception as exc:
        error_chain.append(f"{selected_ep.label}: {exc}")

    for endpoint in fallback_eps:
        try:
            telemetry = await _run_one(endpoint, selected_ep)
            telemetry.fallback_endpoint_id = selected_ep.endpoint_id
            telemetry.fallback_endpoint_label = selected_ep.label
            _set_run_telemetry(session, run, telemetry.to_json())
            return telemetry.output_text, telemetry
        except Exception as exc:
            error_chain.append(f"{endpoint.label}: {exc}")
            continue

    details = "; ".join(error_chain)[:500]
    raise HTTPException(status_code=502, detail=f"Ollama chat failed across endpoints: {details}")


class RunBroker:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subs.setdefault(run_id, set()).add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        if run_id in self._subs:
            self._subs[run_id].discard(q)
            if not self._subs[run_id]:
                self._subs.pop(run_id, None)

    async def publish(self, run_id: str, event: str, data: dict[str, Any]) -> None:
        queues = list(self._subs.get(run_id, set()))
        stale: list[asyncio.Queue[dict[str, Any]]] = []
        for q in queues:
            if q.full():
                stale.append(q)
                continue
            await q.put({"event": event, "data": data})
        for q in stale:
            self.unsubscribe(run_id, q)

    async def stream(self, run_id: str):
        q = self.subscribe(run_id)
        try:
            yield "event: connected\ndata: {\"ok\":true}\n\n"
            while True:
                item = await q.get()
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'], default=str)}\n\n"
        finally:
            self.unsubscribe(run_id, q)


run_broker = RunBroker()
_running_tasks: dict[str, asyncio.Task[None]] = {}


@dataclass
class ToolDecision:
    execute: bool
    pending: bool
    reason: str = ""


def _tool_decision(execution_mode: str, tool_name: str) -> ToolDecision:
    if execution_mode == "propose_only":
        return ToolDecision(execute=False, pending=True, reason="propose_only mode")
    if execution_mode == "require_confirm":
        return ToolDecision(execute=False, pending=True, reason="awaiting user confirmation")
    if execution_mode == "auto_execute_allowlisted":
        if tool_is_auto_allowlisted(tool_name):
            return ToolDecision(execute=True, pending=False)
        return ToolDecision(execute=False, pending=True, reason="not allowlisted for auto mode")
    return ToolDecision(execute=False, pending=True, reason="unknown execution mode")


async def _run_loop(run_id: str) -> None:
    with Session(engine) as session:
        run = get_run(session, run_id)
        if not run:
            return
        settings = ensure_settings(session)
        running_now = session.exec(select(LocalOpsRun).where(LocalOpsRun.status == "running")).all()
        if len(running_now) > settings.max_concurrent_runs:
            run.status = "failed"
            run.error = "Max concurrent runs reached"
            run.finished_at = _now()
            run.updated_at = _now()
            session.add(run)
            session.commit()
            await run_broker.publish(run.id, "run.error", {"message": run.error})
            return

        run.status = "running"
        run.llm_status = "connecting"
        run.updated_at = _now()
        session.add(run)
        session.commit()
        await run_broker.publish(run.id, "run.status", {"status": run.status})

        started = time.time()
        step = 0
        last_assistant = ""
        try:
            while step < settings.max_tool_steps_per_run and (time.time() - started) < settings.max_run_seconds:
                step += 1
                provider_norm = _normalize_provider_id(run.provider_id)
                if provider_norm == "ollama":
                    run.llm_status = "connecting"
                    run.updated_at = _now()
                    session.add(run)
                    session.commit()
                    await run_broker.publish(run.id, "run.status", {"status": run.status, "llm_status": run.llm_status})
                    messages = build_chat_messages(session, run.thread_id)
                    text, telemetry = await _ollama_stream_chat(session, run, messages)
                    run.llm_status = telemetry.status
                else:
                    text = model_response(session, run)
                    run.llm_status = "completed"
                last_assistant = text
                create_message(session, run.thread_id, run.id, "assistant", text, {"step": step})
                if provider_norm != "ollama":
                    # Keep synthetic chunking for non-streaming providers.
                    for i in range(0, len(text), 120):
                        await run_broker.publish(run.id, "token", {"chunk": text[i : i + 120]})

                tools = parse_tool_blocks(text)
                if not tools:
                    run.status = "completed"
                    run.llm_status = "completed"
                    run.finished_at = _now()
                    run.updated_at = _now()
                    session.add(run)
                    session.commit()
                    await run_broker.publish(run.id, "run.status", {"status": "completed", "llm_status": run.llm_status})
                    return

                waiting = False
                for tool in tools:
                    tname = str(tool.get("tool", "")).strip()
                    targs = tool.get("args", {})
                    if not isinstance(targs, dict):
                        targs = {}
                    decision = _tool_decision(run.execution_mode, tname)
                    tc = add_tool_call(session, run.id, tname, targs, status="pending")
                    await run_broker.publish(run.id, "tool.pending", {"id": tc.id, "tool": tname, "args": targs, "reason": decision.reason})
                    if not decision.execute:
                        waiting = True
                        continue
                    try:
                        result = execute_tool(session, settings, run, tname, targs)
                        update_tool_call(session, tc, status="completed", result=result)
                        create_message(session, run.thread_id, run.id, "tool", f"Tool `{tname}` result:\n{json.dumps(result, indent=2)}", {"tool_call_id": tc.id})
                        await run_broker.publish(run.id, "tool.result", {"id": tc.id, "tool": tname, "result": result})
                    except Exception as exc:
                        err = {"error": str(exc)}
                        update_tool_call(session, tc, status="failed", result=err)
                        create_message(session, run.thread_id, run.id, "tool", f"Tool `{tname}` failed: {exc}", {"tool_call_id": tc.id})
                        await run_broker.publish(run.id, "tool.error", {"id": tc.id, "tool": tname, "error": str(exc)})
                if waiting:
                    run.status = "waiting_approval"
                    run.updated_at = _now()
                    session.add(run)
                    session.commit()
                    await run_broker.publish(run.id, "run.status", {"status": run.status, "llm_status": run.llm_status})
                    return

            run.status = "failed"
            run.llm_status = "failed"
            run.error = "Tool loop limits reached"
            run.finished_at = _now()
            run.updated_at = _now()
            session.add(run)
            session.commit()
            await run_broker.publish(run.id, "run.error", {"message": run.error, "assistant": last_assistant})
        except httpx.TimeoutException as exc:
            run.status = "failed"
            run.llm_status = "timed_out"
            run.error = str(exc)
            run.finished_at = _now()
            run.updated_at = _now()
            session.add(run)
            session.commit()
            await run_broker.publish(run.id, "run.status", {"status": run.status, "llm_status": run.llm_status})
            await run_broker.publish(run.id, "run.error", {"message": str(exc)})
        except asyncio.CancelledError:
            run.status = "canceled"
            run.llm_status = "cancelled"
            run.finished_at = _now()
            run.updated_at = _now()
            session.add(run)
            session.commit()
            await run_broker.publish(run.id, "run.status", {"status": run.status, "llm_status": run.llm_status})
            raise
        except Exception as exc:
            run.status = "failed"
            run.llm_status = "failed"
            run.error = str(exc)
            run.finished_at = _now()
            run.updated_at = _now()
            session.add(run)
            session.commit()
            await run_broker.publish(run.id, "run.error", {"message": str(exc)})


def start_run_task(run_id: str) -> None:
    if run_id in _running_tasks and not _running_tasks[run_id].done():
        return
    _running_tasks[run_id] = asyncio.create_task(_run_loop(run_id))


def cancel_run(run_id: str) -> bool:
    task = _running_tasks.get(run_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def approve_tool_call_and_continue(run_id: str, tool_call_id: str) -> dict[str, Any]:
    with Session(engine) as session:
        run = get_run(session, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        tc = session.get(LocalOpsToolCall, tool_call_id)
        if not tc or tc.run_id != run_id:
            raise HTTPException(status_code=404, detail="tool call not found")
        if tc.status not in {"pending", "approved"}:
            return {"ok": True, "status": tc.status}
        settings = ensure_settings(session)
        args = _jloads(tc.args_json, {})
        try:
            result = execute_tool(session, settings, run, tc.tool_name, args)
            update_tool_call(session, tc, status="completed", result=result)
            create_message(session, run.thread_id, run.id, "tool", f"Tool `{tc.tool_name}` result:\n{json.dumps(result, indent=2)}", {"tool_call_id": tc.id})
            await run_broker.publish(run.id, "tool.result", {"id": tc.id, "tool": tc.tool_name, "result": result})
        except Exception as exc:
            update_tool_call(session, tc, status="failed", result={"error": str(exc)})
            create_message(session, run.thread_id, run.id, "tool", f"Tool `{tc.tool_name}` failed: {exc}", {"tool_call_id": tc.id})
            await run_broker.publish(run.id, "tool.error", {"id": tc.id, "tool": tc.tool_name, "error": str(exc)})
        run.status = "running"
        run.llm_status = "connecting"
        run.updated_at = _now()
        session.add(run)
        session.commit()
        start_run_task(run.id)
        return {"ok": True, "status": "running"}
