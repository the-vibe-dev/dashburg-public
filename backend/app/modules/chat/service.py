from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.localops import LocalOpsProvider
from app.modules.memory.service import build_memory_brief
from app.services.ollama_client import OllamaClient, OllamaEndpoint

try:
    import redis as redis_lib
except Exception:  # pragma: no cover
    redis_lib = None


OLLAMA_CLIENT = OllamaClient(timeout_seconds=180.0)
SESSION_PREFIX = "dashburg:chat:session:v1"
SESSIONS_INDEX_KEY = "dashburg:chat:sessions:v1"
DEFAULT_MODEL = "qwen3:14b"
DEFAULT_PROVIDER = "ollama"
DEFAULT_TTL_SECONDS = 43200

ROLE_SET = {"user", "assistant", "system", "tool"}
SOURCE_SET = {"web", "discord", "system", "agent", "tool"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime | None = None) -> str:
    value = ts or _now()
    return value.isoformat()


def _safe_json_load(value: str, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except Exception:
        return fallback
    return parsed


def _safe_json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _redis_url() -> str:
    return str(os.getenv("CHAT_REDIS_URL") or os.getenv("REDIS_URL") or "redis://127.0.0.1:6379/0").strip()


def _broker_enabled() -> bool:
    raw = str(os.getenv("REDIS_BROKER_ENABLED", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _broker_base_url() -> str:
    return str(os.getenv("REDIS_BROKER_BASE_URL", "http://127.0.0.1:8710")).strip().rstrip("/")


def _broker_jobs_path() -> str:
    path = str(os.getenv("REDIS_LLM_JOBS_PATH", "/llm/jobs")).strip()
    return path if path.startswith("/") else f"/{path}"


def _broker_poll_seconds() -> float:
    try:
        return max(0.2, float(os.getenv("REDIS_BROKER_POLL_S", "0.8")))
    except Exception:
        return 0.8


def _broker_timeout_seconds() -> float:
    try:
        return max(5.0, float(os.getenv("REDIS_BROKER_TIMEOUT_S", "120")))
    except Exception:
        return 120.0


def _redis_client() -> Any:
    if redis_lib is None:
        raise HTTPException(status_code=503, detail="redis package not installed")
    try:
        client = redis_lib.Redis.from_url(_redis_url(), decode_responses=True, socket_timeout=3.0)
        client.ping()
        return client
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {exc}") from exc


def _sanitize_session_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return uuid.uuid4().hex
    safe = re.sub(r"[^a-zA-Z0-9:_-]", "-", raw)
    safe = re.sub(r"-{2,}", "-", safe).strip("-")
    return safe[:128] or uuid.uuid4().hex


def _sanitize_role(value: str | None) -> str:
    role = str(value or "").strip().lower() or "user"
    return role if role in ROLE_SET else "user"


def _sanitize_source(value: str | None) -> str:
    source = str(value or "").strip().lower() or "web"
    return source if source in SOURCE_SET else "web"


def _session_key(session_id: str) -> str:
    return f"{SESSION_PREFIX}:{session_id}"


def _messages_key(session_id: str) -> str:
    return f"{SESSION_PREFIX}:{session_id}:messages"


def _public_message(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "session_id": str(row.get("session_id") or ""),
        "role": _sanitize_role(str(row.get("role") or "user")),
        "source": _sanitize_source(str(row.get("source") or "web")),
        "content": str(row.get("content") or ""),
        "created_at": str(row.get("created_at") or _iso()),
        "model": str(row.get("model") or ""),
        "provider": str(row.get("provider") or ""),
        "status": str(row.get("status") or "completed"),
        "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
        "tool_payload": row.get("tool_payload") if isinstance(row.get("tool_payload"), dict) else None,
        "audit_id": str(row.get("audit_id") or "") or None,
    }


def _public_session(data: dict[str, str]) -> dict[str, Any]:
    return {
        "id": str(data.get("id") or ""),
        "title": str(data.get("title") or "Dashburg Chat Session"),
        "status": str(data.get("status") or "active"),
        "model": str(data.get("model") or os.getenv("OLLAMA_ROUTER_DEFAULT_MODEL", DEFAULT_MODEL)),
        "provider": str(data.get("provider") or DEFAULT_PROVIDER),
        "source_types": _safe_json_load(data.get("source_types_json", "[]"), []),
        "discord_link": _safe_json_load(data.get("discord_link_json", "{}"), {}),
        "message_count": int(data.get("message_count") or 0),
        "created_at": str(data.get("created_at") or _iso()),
        "updated_at": str(data.get("updated_at") or _iso()),
        "last_message_at": str(data.get("last_message_at") or "") or None,
        "metadata": _safe_json_load(data.get("metadata_json", "{}"), {}),
    }


def _resolve_model(requested: str | None, session_data: dict[str, str] | None = None) -> str:
    if requested and requested.strip():
        return requested.strip()
    if session_data:
        v = str(session_data.get("model") or "").strip()
        if v:
            return v
    env_model = str(os.getenv("OLLAMA_ROUTER_DEFAULT_MODEL") or "").strip()
    return env_model or DEFAULT_MODEL


def _resolve_provider_endpoint(session: Session) -> OllamaEndpoint:
    env_endpoint = str(os.getenv("OLLAMA_ROUTER_DEFAULT_ENDPOINT") or "").strip()
    env_label = str(os.getenv("OLLAMA_ROUTER_DEFAULT_LABEL") or "ollama-router").strip() or "ollama-router"
    if env_endpoint:
        return OllamaEndpoint(endpoint_id=None, label=env_label, base_url=env_endpoint)

    preferred = session.exec(
        select(LocalOpsProvider)
        .where(LocalOpsProvider.provider_id == "ollama")
        .where(LocalOpsProvider.enabled == True)  # noqa: E712
        .order_by(LocalOpsProvider.default_for_agents.desc(), LocalOpsProvider.id.asc())
    ).first()
    if preferred and preferred.base_url.strip():
        return OllamaEndpoint(
            endpoint_id=preferred.id,
            label=preferred.name or "ollama",
            base_url=preferred.base_url.strip(),
            api_key=preferred.api_key.strip(),
        )

    return OllamaEndpoint(endpoint_id=None, label="ollama-fallback", base_url="http://127.0.0.1:11434")


def _touch_session(client: Any, session_id: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS, increment: bool = False) -> dict[str, str]:
    key = _session_key(session_id)
    data = client.hgetall(key)
    if not data:
        raise HTTPException(status_code=404, detail="chat session not found")
    now = _iso()
    mapping: dict[str, str] = {"updated_at": now}
    if increment:
        mapping["message_count"] = str(int(data.get("message_count") or 0) + 1)
        mapping["last_message_at"] = now
    client.hset(key, mapping=mapping)
    client.expire(key, ttl_seconds)
    client.zadd(SESSIONS_INDEX_KEY, {session_id: _now().timestamp()})
    data.update(mapping)
    return data


def create_session(payload: dict[str, Any]) -> dict[str, Any]:
    client = _redis_client()
    session_id = _sanitize_session_id(payload.get("session_id"))
    key = _session_key(session_id)
    existing = client.hgetall(key)
    if existing:
        return _public_session(existing)

    model = _resolve_model(str(payload.get("model") or ""), None)
    provider = str(payload.get("provider") or DEFAULT_PROVIDER).strip() or DEFAULT_PROVIDER
    title = str(payload.get("title") or "Dashburg Chat Session").strip() or "Dashburg Chat Session"
    source_types = payload.get("source_types") if isinstance(payload.get("source_types"), list) else ["web"]
    source_types = [_sanitize_source(str(v)) for v in source_types]
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    now = _iso()
    ttl_seconds = int(payload.get("ttl_seconds") or os.getenv("CHAT_SESSION_TTL_SECONDS") or DEFAULT_TTL_SECONDS)
    row = {
        "id": session_id,
        "title": title,
        "status": "active",
        "model": model,
        "provider": provider,
        "source_types_json": _safe_json_dump(source_types),
        "discord_link_json": _safe_json_dump({}),
        "message_count": "0",
        "created_at": now,
        "updated_at": now,
        "last_message_at": "",
        "metadata_json": _safe_json_dump(metadata),
    }
    client.hset(key, mapping=row)
    client.expire(key, ttl_seconds)
    client.zadd(SESSIONS_INDEX_KEY, {session_id: _now().timestamp()})
    return _public_session(row)


def get_chat_session(session_id: str) -> dict[str, Any]:
    client = _redis_client()
    key = _session_key(_sanitize_session_id(session_id))
    row = client.hgetall(key)
    if not row:
        raise HTTPException(status_code=404, detail="chat session not found")
    return _public_session(row)


def list_sessions(limit: int = 50) -> dict[str, Any]:
    client = _redis_client()
    count = max(1, min(limit, 200))
    ids = client.zrevrange(SESSIONS_INDEX_KEY, 0, count - 1)
    items: list[dict[str, Any]] = []
    for sid in ids:
        row = client.hgetall(_session_key(sid))
        if row:
            items.append(_public_session(row))
    return {"items": items}


def append_message(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = _redis_client()
    sid = _sanitize_session_id(session_id)
    session_data = _touch_session(client, sid, increment=True)

    message = {
        "id": uuid.uuid4().hex,
        "session_id": sid,
        "role": _sanitize_role(payload.get("role")),
        "source": _sanitize_source(payload.get("source")),
        "content": str(payload.get("content") or "").strip(),
        "created_at": _iso(),
        "model": str(payload.get("model") or session_data.get("model") or ""),
        "provider": str(payload.get("provider") or session_data.get("provider") or ""),
        "status": str(payload.get("status") or "completed"),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        "tool_payload": payload.get("tool_payload") if isinstance(payload.get("tool_payload"), dict) else None,
        "audit_id": str(payload.get("audit_id") or "") or None,
    }
    if not message["content"]:
        raise HTTPException(status_code=400, detail="content is required")

    client.rpush(_messages_key(sid), _safe_json_dump(message))
    ttl_seconds = int(os.getenv("CHAT_SESSION_TTL_SECONDS") or DEFAULT_TTL_SECONDS)
    client.expire(_messages_key(sid), ttl_seconds)
    return _public_message(message)


def list_messages(session_id: str, limit: int = 200) -> dict[str, Any]:
    client = _redis_client()
    sid = _sanitize_session_id(session_id)
    _touch_session(client, sid, increment=False)

    items = client.lrange(_messages_key(sid), -max(1, min(limit, 1000)), -1)
    out: list[dict[str, Any]] = []
    for raw in items:
        row = _safe_json_load(raw, {})
        if isinstance(row, dict):
            out.append(_public_message(row))
    return {"items": out}


def attach_discord(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = _redis_client()
    sid = _sanitize_session_id(session_id)
    data = _touch_session(client, sid, increment=False)

    link = {
        "guild_id": str(payload.get("guild_id") or "").strip(),
        "channel_id": str(payload.get("channel_id") or "").strip(),
        "user_id": str(payload.get("user_id") or "").strip(),
    }
    source_types = payload.get("source_types") if isinstance(payload.get("source_types"), list) else ["web", "discord"]
    source_types = [_sanitize_source(str(v)) for v in source_types]
    client.hset(
        _session_key(sid),
        mapping={
            "discord_link_json": _safe_json_dump(link),
            "source_types_json": _safe_json_dump(source_types),
            "updated_at": _iso(),
        },
    )
    data.update({"discord_link_json": _safe_json_dump(link), "source_types_json": _safe_json_dump(source_types), "updated_at": _iso()})
    return _public_session(data)


def sync_messages(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    count = 0
    for row in messages:
        if not isinstance(row, dict):
            continue
        if not str(row.get("content") or "").strip():
            continue
        append_message(session_id, row)
        count += 1
    return {"ok": True, "synced": count}


def _to_ollama_messages(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    mapped: list[dict[str, str]] = []
    for row in history:
        role = _sanitize_role(str(row.get("role") or "user"))
        text = str(row.get("content") or "").strip()
        if not text:
            continue
        if role not in {"user", "assistant", "system"}:
            continue
        mapped.append({"role": role, "content": text})
    return mapped


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n"


def _extract_broker_text(result_payload: dict[str, Any]) -> str:
    message_value = result_payload.get("message")
    if isinstance(message_value, dict):
        content = message_value.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    candidates = [
        result_payload.get("response"),
        result_payload.get("text"),
        result_payload.get("content"),
        result_payload.get("output"),
        (result_payload.get("result") or {}).get("response") if isinstance(result_payload.get("result"), dict) else None,
        (result_payload.get("result") or {}).get("message", {}).get("content")
        if isinstance((result_payload.get("result") or {}).get("message"), dict)
        else None,
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()

    choices = result_payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    return ""


def _chunk_text(text: str, chunk_size: int = 180) -> list[str]:
    raw = str(text or "")
    if len(raw) <= chunk_size:
        return [raw] if raw else []
    out: list[str] = []
    idx = 0
    while idx < len(raw):
        out.append(raw[idx : idx + chunk_size])
        idx += chunk_size
    return out


async def _broker_chat_completion(model: str, messages: list[dict[str, str]]) -> str:
    base = _broker_base_url()
    submit_body = {
        "source_repo": "dashburg",
        "tenant_tag": "default",
        "idempotency_key": f"dashburg-chat-{uuid.uuid4().hex}",
        "priority": 100,
        "payload": {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.2,
            },
        },
    }

    timeout = _broker_timeout_seconds()
    poll = _broker_poll_seconds()
    async with httpx.AsyncClient(timeout=timeout) as http:
        submit = await http.post(f"{base}{_broker_jobs_path()}", json=submit_body)
        submit.raise_for_status()
        submit_data = submit.json() if submit.content else {}
        job_id = str(submit_data.get("job_id") or "").strip()
        if not job_id:
            raise RuntimeError(f"redis broker submit missing job_id: {submit_data}")

        deadline = time.time() + timeout
        state = "queued"
        while time.time() < deadline:
            row = await http.get(f"{base}/jobs/{job_id}")
            row.raise_for_status()
            row_data = row.json() if row.content else {}
            state = str(row_data.get("state") or state).strip().lower() or state
            if state in {"done", "succeeded", "completed"}:
                break
            if state in {"failed", "canceled"}:
                raise RuntimeError(f"redis broker job failed id={job_id} state={state}")
            await asyncio.sleep(poll)
        else:
            raise RuntimeError(f"redis broker timeout id={job_id} state={state}")

        result = await http.get(f"{base}/jobs/{job_id}/result")
        result.raise_for_status()
        result_data = result.json() if result.content else {}
        payload = result_data.get("result_payload") if isinstance(result_data, dict) else None
        if not isinstance(payload, dict):
            payload = result_data if isinstance(result_data, dict) else {}
        text = _extract_broker_text(payload)
        if not text:
            raise RuntimeError(f"redis broker result missing text id={job_id}")
        return text


async def stream_assistant_reply(session: Session, session_id: str, payload: dict[str, Any]) -> AsyncGenerator[str, None]:
    client = _redis_client()
    sid = _sanitize_session_id(session_id)

    if not client.exists(_session_key(sid)):
        create_session({"session_id": sid, "source_types": [payload.get("source") or "web"]})

    user_message = append_message(
        sid,
        {
            "role": "user",
            "source": _sanitize_source(payload.get("source")),
            "content": str(payload.get("content") or ""),
            "model": payload.get("model"),
            "provider": payload.get("provider"),
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        },
    )

    history_data = list_messages(sid, limit=int(payload.get("max_history_messages") or 24))
    history = history_data.get("items") if isinstance(history_data.get("items"), list) else []

    prompt_text = str(payload.get("content") or "")
    include_memory = bool(payload.get("include_memory", True))
    if include_memory and prompt_text:
        brief = build_memory_brief({"query": prompt_text, "max_chars": 1200})
        brief_text = str(brief.get("brief") or "").strip()
        if brief_text:
            history = [
                {
                    "id": uuid.uuid4().hex,
                    "session_id": sid,
                    "role": "system",
                    "source": "system",
                    "content": brief_text,
                    "created_at": _iso(),
                    "model": "",
                    "provider": "",
                    "status": "completed",
                    "metadata": {"memory": True},
                    "tool_payload": None,
                    "audit_id": None,
                }
            ] + history

    session_data = client.hgetall(_session_key(sid))
    model = _resolve_model(str(payload.get("model") or ""), session_data)
    endpoint = _resolve_provider_endpoint(session)
    ollama_messages = _to_ollama_messages(history)

    provider_label = "redis-broker" if _broker_enabled() else "ollama"
    source_label = _broker_base_url() if _broker_enabled() else endpoint.label
    yield _sse("started", {"session_id": sid, "model": model, "provider": provider_label, "source": source_label})

    output_parts: list[str] = []
    done_reason = "stop"

    async def _stream_direct_ollama() -> None:
        nonlocal done_reason
        async for chunk in OLLAMA_CLIENT.stream_json_lines(
            endpoint,
            "/api/chat",
            payload={"model": model, "messages": ollama_messages, "stream": True},
            timeout=float(os.getenv("CHAT_STREAM_TIMEOUT_MS") or 180000) / 1000.0,
        ):
            piece = ""
            message_obj = chunk.get("message") if isinstance(chunk.get("message"), dict) else {}
            if message_obj:
                piece = str(message_obj.get("content") or "")
            if piece:
                output_parts.append(piece)
                yield _sse("delta", {"text": piece})
            if bool(chunk.get("done")):
                done_reason = str(chunk.get("done_reason") or "stop")
                break

    try:
        if _broker_enabled():
            try:
                final = await _broker_chat_completion(model, ollama_messages)
                for piece in _chunk_text(final):
                    output_parts.append(piece)
                    yield _sse("delta", {"text": piece})
                done_reason = "stop"
            except Exception as broker_exc:
                # Resiliency fallback: if broker fails, stream directly from configured Ollama route.
                yield _sse("delta", {"text": "[broker-fallback] "})
                client.hset(
                    _session_key(sid),
                    mapping={
                        "updated_at": _iso(),
                        "last_error": f"broker_failed:{str(broker_exc)[:600]}",
                    },
                )
                async for evt in _stream_direct_ollama():
                    yield evt
        else:
            async for evt in _stream_direct_ollama():
                yield evt

        final_text = "".join(output_parts).strip()
        if not final_text:
            final_text = "(no assistant output)"

        assistant_message = append_message(
            sid,
            {
                "role": "assistant",
                "source": "agent",
                "content": final_text,
                "model": model,
                "provider": provider_label,
                "status": "completed",
                "metadata": {
                    "source": payload.get("source") or "web",
                    "done_reason": done_reason,
                    "reply_to": user_message.get("id"),
                },
            },
        )
        yield _sse("final", {"message": assistant_message})
    except Exception as exc:
        err_text = str(exc)
        client.hset(_session_key(sid), mapping={"last_error": err_text, "updated_at": _iso()})
        yield _sse("error", {"error": err_text})
    finally:
        yield _sse("done", {"session_id": sid})
