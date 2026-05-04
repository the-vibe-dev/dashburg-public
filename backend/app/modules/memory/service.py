from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.modules.memory.storage import (
    LOCK_TIMEOUT_SECONDS,
    append_text_line,
    append_with_fallback,
    fallback_root,
    fingerprint_record,
    iter_jsonl,
    replay_local_queue,
    shared_available,
    shared_root,
)
from app.services.knowledge import search_knowledge


PIPELINE_STATES = {
    "captured",
    "skipped_empty",
    "skipped_duplicate",
    "queued_for_compaction",
    "compacted",
    "promoted",
    "promotion_skipped",
}


def _log_op(message: str) -> None:
    root = shared_root() if shared_available() else fallback_root()
    append_text_line(root / "logs" / "memory_ops.log", message)


def _rel(rel_path: str) -> Path:
    root = shared_root() if shared_available() else fallback_root()
    return root / rel_path


def _contains_fingerprint(rel_path: str, fp: str, tail: int = 5000) -> bool:
    rows = iter_jsonl(_rel(rel_path), tail=tail)
    for row in rows:
        if fingerprint_record(row) == fp:
            return True
    return False


def memory_health() -> dict[str, Any]:
    replay_path = fallback_root() / "replay_queue.jsonl"
    replay_len = len(iter_jsonl(replay_path)) if replay_path.exists() else 0
    return {
        "ok": True,
        "shared_root": str(shared_root()),
        "shared_available": shared_available(),
        "replay_queue_length": replay_len,
        "fallback_root": str(fallback_root()),
        "lock_timeout_seconds": LOCK_TIMEOUT_SECONDS,
    }


def memory_settings() -> dict[str, Any]:
    return {
        "shared_root": str(shared_root()),
        "fallback_root": str(fallback_root()),
        "brief_max_chars": 1800,
        "rerank_default": False,
        "lock_timeout_seconds": LOCK_TIMEOUT_SECONDS,
        "using_env_root": bool(str(os.getenv("DASHBURG_SHARED_MEMORY_ROOT", "")).strip()),
    }


def list_sessions(limit: int = 100, q: str = "") -> list[dict[str, Any]]:
    rows = iter_jsonl(_rel("memory/SESSION_INDEX.jsonl"), tail=max(1, limit * 5))
    q_norm = q.strip().lower()
    if q_norm:
        rows = [r for r in rows if q_norm in str(r).lower()]
    return rows[-limit:][::-1]


def list_candidates(limit: int = 100, q: str = "") -> list[dict[str, Any]]:
    rows = iter_jsonl(_rel("memory/MEMORY_CANDIDATES.jsonl"), tail=max(1, limit * 5))
    q_norm = q.strip().lower()
    if q_norm:
        rows = [r for r in rows if q_norm in str(r).lower()]
    return rows[-limit:][::-1]


def list_relationships(limit: int = 100, q: str = "") -> list[dict[str, Any]]:
    rows = iter_jsonl(_rel("memory/DOC_RELATIONSHIPS.jsonl"), tail=max(1, limit * 5))
    q_norm = q.strip().lower()
    if q_norm:
        rows = [r for r in rows if q_norm in str(r).lower()]
    return rows[-limit:][::-1]


def write_session_index(payload: dict[str, Any]) -> tuple[str, str]:
    return append_with_fallback("memory/SESSION_INDEX.jsonl", payload)


def write_relationship(payload: dict[str, Any]) -> tuple[str, str]:
    return append_with_fallback("memory/DOC_RELATIONSHIPS.jsonl", payload)


def write_delta(payload: dict[str, Any]) -> tuple[str, str]:
    return append_with_fallback("memory/MEMORY_DELTAS.jsonl", payload)


def capture_candidate(payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    body = str(payload.get("body") or payload.get("summary") or payload.get("content") or "").strip()
    normalized = {
        **payload,
        "body": body,
        "state": "captured",
    }
    if not body:
        normalized["state"] = "skipped_empty"
        return "skipped_empty", normalized, ""
    dest, fp = append_with_fallback("memory/MEMORY_CANDIDATES.jsonl", normalized)
    _log_op(f"candidate captured via {dest} fp={fp}")
    return "captured", normalized, fp


def dedupe_candidate(candidate: dict[str, Any], fp: str) -> bool:
    if not fp:
        return False
    rows = iter_jsonl(_rel("memory/MEMORY_DELTAS.jsonl"), tail=10000)
    for row in rows:
        if str(row.get("fingerprint") or "") == fp:
            return True
        if fingerprint_record(row) == fp:
            return True
    return False


def queue_for_compaction(candidate: dict[str, Any], fingerprint: str) -> tuple[str, str]:
    row = {**candidate, "state": "queued_for_compaction", "fingerprint": fingerprint}
    return append_with_fallback("memory/MEMORY_DELTAS.jsonl", row)


def compact_memory(payload: dict[str, Any] | None = None, *, limit: int = 100, promote: bool = False) -> dict[str, Any]:
    req = payload if isinstance(payload, dict) else {}
    states: list[str] = []
    replayed = replay_local_queue(limit=200)

    candidate = req.get("candidate") if isinstance(req.get("candidate"), dict) else None
    compacted_count = 0
    out_candidate: dict[str, Any] | None = None

    if candidate is not None:
        state, row, fp = capture_candidate(candidate)
        states.append(state)
        out_candidate = row
        if state == "captured":
            if dedupe_candidate(row, fp):
                states.append("skipped_duplicate")
            else:
                queue_for_compaction(row, fp)
                states.append("queued_for_compaction")
                compaction_event = {
                    "state": "compacted",
                    "candidate": row,
                    "fingerprint": fp,
                }
                append_with_fallback("compacted/memory_compactions.jsonl", compaction_event)
                states.append("compacted")
                compacted_count += 1
                if promote:
                    states.append("promotion_skipped")
    else:
        pending = list_candidates(limit=limit)
        for row in pending:
            if str(row.get("state") or "") not in {"captured", "queued_for_compaction"}:
                continue
            fp = fingerprint_record(row)
            if dedupe_candidate(row, fp):
                continue
            append_with_fallback("compacted/memory_compactions.jsonl", {"state": "compacted", "candidate": row, "fingerprint": fp})
            compacted_count += 1
        if compacted_count:
            states.append("compacted")

    if not states:
        states = ["promotion_skipped" if promote else "compacted"]

    return {
        "states": [s for s in states if s in PIPELINE_STATES],
        "candidate": out_candidate,
        "compacted_count": compacted_count,
        "replayed_count": replayed,
    }


def _rank_hits(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return [{"score": 0.0, "item": row} for row in rows]
    out: list[dict[str, Any]] = []
    for row in rows:
        text = str(row).lower()
        score = float(text.count(q))
        if score > 0:
            out.append({"score": score, "item": row})
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


def _search_docs(query: str, limit: int = 10) -> list[dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return []
    base = _rel("docs")
    hits: list[dict[str, Any]] = []
    for sub in ("investigations", "profiles"):
        root = base / sub
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if q in content.lower() or q in path.name.lower():
                hits.append({
                    "path": str(path),
                    "snippet": content[:500],
                    "kind": f"doc:{sub}",
                })
            if len(hits) >= limit:
                return hits
    return hits


def search_memory(payload: dict[str, Any]) -> dict[str, Any]:
    replay_local_queue(limit=200)

    query = str(payload.get("query") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    repo_path = str(payload.get("repo_path") or "").strip()
    limit = max(1, min(int(payload.get("limit") or 20), 200))
    include_docs = bool(payload.get("include_docs", False))
    include_knowledge = bool(payload.get("include_knowledge", True))
    rerank = bool(payload.get("rerank", False))

    stages: list[str] = []
    results: list[dict[str, Any]] = []

    routing_rows = iter_jsonl(_rel("routing/LOCATIONS.json"))
    if not routing_rows:
        loc_path = _rel("routing/LOCATIONS.json")
        if loc_path.exists():
            try:
                import json

                raw = json.loads(loc_path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(raw, dict):
                    routing_rows = [raw]
            except Exception:
                routing_rows = []
    stages.append("routing")
    results.extend({"stage": "routing", "score": r["score"], "item": r["item"]} for r in _rank_hits(routing_rows, query)[:5])

    sessions = list_sessions(limit=limit * 2, q=query)
    stages.append("sessions")
    results.extend({"stage": "sessions", "score": r["score"], "item": r["item"]} for r in _rank_hits(sessions, query)[:limit])

    deltas = iter_jsonl(_rel("memory/MEMORY_DELTAS.jsonl"), tail=limit * 10)
    if node_id:
        deltas = [d for d in deltas if str(d.get("node_id") or "") == node_id]
    if repo_path:
        deltas = [d for d in deltas if repo_path in str(d.get("repo_path") or "")]
    stages.append("deltas")
    results.extend({"stage": "deltas", "score": r["score"], "item": r["item"]} for r in _rank_hits(deltas, query)[:limit])

    rels = list_relationships(limit=limit * 2, q=query)
    stages.append("relationships")
    results.extend({"stage": "relationships", "score": r["score"], "item": r["item"]} for r in _rank_hits(rels, query)[:limit])

    if include_knowledge and query:
        try:
            know = search_knowledge(query, limit=min(limit, 10))
        except Exception:
            know = []
        stages.append("knowledge")
        results.extend({"stage": "knowledge", "score": r["score"], "item": r["item"]} for r in _rank_hits(know, query)[:limit])

    if include_docs and query:
        docs = _search_docs(query, limit=min(limit, 20))
        stages.append("docs")
        results.extend({"stage": "docs", "score": r["score"], "item": r["item"]} for r in _rank_hits(docs, query)[:limit])

    # Optional rerank stage is intentionally lightweight and off by default.
    rerank_applied = False
    if rerank:
        stages.append("rerank")
        results.sort(key=lambda r: (r.get("score") or 0.0), reverse=True)
        rerank_applied = True

    results.sort(key=lambda r: (r.get("score") or 0.0), reverse=True)
    return {
        "items": results[:limit],
        "stages": stages,
        "rerank_applied": rerank_applied,
    }


def build_memory_brief(payload: dict[str, Any]) -> dict[str, Any]:
    max_chars = max(300, min(int(payload.get("max_chars") or 1800), 1800))
    search_payload = {
        "query": str(payload.get("query") or "").strip(),
        "node_id": payload.get("node_id"),
        "repo_path": payload.get("repo_path"),
        "limit": 24,
        "include_docs": False,
        "include_knowledge": True,
        "rerank": bool(payload.get("rerank", False)),
    }
    data = search_memory(search_payload)
    items = data.get("items") if isinstance(data.get("items"), list) else []

    node = str(payload.get("node_id") or "-")
    repo = str(payload.get("repo_path") or "-")

    routing: list[str] = []
    recent: list[str] = []
    sessions: list[str] = []
    for row in items:
        stage = str(row.get("stage") or "")
        item = row.get("item") if isinstance(row.get("item"), dict) else {}
        if stage == "routing" and len(routing) < 4:
            routing.append(str(item)[:120])
        if stage == "deltas" and len(recent) < 4:
            recent.append(str(item.get("kind") or item.get("state") or item)[:120])
        if stage == "sessions" and len(sessions) < 4:
            sid = str(item.get("session_id") or item.get("id") or item.get("title") or "")
            if sid:
                sessions.append(sid[:80])

    lines = [
        "[MEMORY BRIEF]",
        "",
        f"node: {node}",
        f"repo: {repo}",
        "",
        "routing:",
    ]
    if routing:
        lines.extend(f"- {row}" for row in routing)
    else:
        lines.append("- no routing hits")

    lines.extend(["", "recent events:"])
    if recent:
        lines.extend(f"- {row}" for row in recent)
    else:
        lines.append("- no recent events")

    lines.extend(["", "relevant sessions:"])
    if sessions:
        lines.extend(f"- {row}" for row in sessions)
    else:
        lines.append("- none")

    lines.extend(["", "[/MEMORY BRIEF]"])
    brief = "\n".join(lines)
    if len(brief) > max_chars:
        brief = brief[: max_chars - 20].rstrip() + "\n[/MEMORY BRIEF]"

    return {
        "brief": brief,
        "chars": len(brief),
    }
