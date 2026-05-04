from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from knowledge_layer import KnowledgeClient, KnowledgeConfig, build_record, redact_mail_content, should_write_record
except ModuleNotFoundError:
    KnowledgeClient = None  # type: ignore[assignment]
    KnowledgeConfig = None  # type: ignore[assignment]

    def build_record(payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    def redact_mail_content(text: str) -> str:
        return text

    def should_write_record(**_: Any) -> bool:
        return False


class _NullKnowledgeClient:
    config = type("Config", (), {"min_confidence": 1.0, "min_usefulness": 1.0, "mail_write_enabled": False})()

    def search(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
        return []

    def search_mail_knowledge(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
        return []

    def add_record(self, *_: Any, **__: Any) -> dict[str, Any]:
        return {"ok": True, "skipped": True, "reason": "knowledge_layer_unavailable"}

    def add_mail_record(self, *_: Any, **__: Any) -> dict[str, Any]:
        return {"ok": True, "skipped": True, "reason": "knowledge_layer_unavailable"}


@lru_cache(maxsize=1)
def get_knowledge_client() -> Any:
    if KnowledgeClient is None or KnowledgeConfig is None:
        return _NullKnowledgeClient()
    return KnowledgeClient(KnowledgeConfig.from_env(spool_dir=str((ROOT_DIR / "data" / "knowledge").resolve())))


def reset_knowledge_client_cache() -> None:
    get_knowledge_client.cache_clear()


def search_knowledge(query: str, *, filters: dict[str, Any] | None = None, limit: int = 5) -> list[dict[str, Any]]:
    return get_knowledge_client().search(query, filters=filters or {}, limit=limit)


def search_mail_knowledge(query: str, *, filters: dict[str, Any] | None = None, limit: int = 5) -> list[dict[str, Any]]:
    return get_knowledge_client().search_mail_knowledge(query, filters=filters or {}, limit=limit)


def maybe_add_record(payload: dict[str, Any], *, confidence: float | None, usefulness: float | None, reusable: bool = True) -> dict[str, Any]:
    client = get_knowledge_client()
    if not should_write_record(
        confidence=confidence,
        usefulness=usefulness,
        min_confidence=client.config.min_confidence,
        min_usefulness=client.config.min_usefulness,
        reusable=reusable,
    ):
        return {"ok": True, "skipped": True, "reason": "quality_gate"}
    return client.add_record(build_record(payload))


def maybe_add_mail_record(*, record_type: str, title: str, summary: str, content: str, tags: list[str] | None, topic: str, metadata: dict[str, Any] | None, confidence: float | None, usefulness: float | None, reusable: bool = True) -> dict[str, Any]:
    client = get_knowledge_client()
    if not client.config.mail_write_enabled:
        return {"ok": True, "skipped": True, "reason": "mail_write_disabled"}
    if not should_write_record(
        confidence=confidence,
        usefulness=usefulness,
        min_confidence=client.config.min_confidence,
        min_usefulness=client.config.min_usefulness,
        reusable=reusable,
    ):
        return {"ok": True, "skipped": True, "reason": "quality_gate"}
    return client.add_mail_record(
        record_type=record_type,
        title=title,
        summary=summary,
        content=content,
        tags=tags,
        topic=topic,
        metadata=metadata,
    )


def summarize_knowledge_hits(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows[:5]:
        title = str(row.get("title") or row.get("summary") or "").strip()
        summary = str(row.get("summary") or "").strip()
        if not title and not summary:
            continue
        lines.append(f"- {title}: {summary}".strip(": "))
    return "\n".join(lines)


def redact_mail_text(text: str) -> str:
    return redact_mail_content(text)
