from __future__ import annotations

import asyncio
import html
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.core.config import load_config
from app.db.session import engine
from app.models.run import Run, RunEvent
from app.services.sse import SSEBroker

ROOT_DIR = Path(__file__).resolve().parents[3]


@dataclass
class CollectorState:
    stop: asyncio.Event
    task: asyncio.Task | None = None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _status_from_payload(payload: dict[str, Any]) -> str:
    for key in ("status", "state", "run_status"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val.lower()
    return "unknown"


def _extract_run_payload(run_dir: Path, payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    run_id = str(payload.get("run_id") or payload.get("id") or run_dir.name)
    return {
        "id": run_id,
        "repo_name": str(payload.get("repo_name") or payload.get("repo") or payload.get("channel") or run_dir.parent.name),
        "monitor_name": str(payload.get("monitor_name") or payload.get("monitor") or run_dir.parent.name),
        "status": _status_from_payload(payload),
        "stage": str(payload.get("stage") or payload.get("current_stage") or "-"),
        "topic": str(payload.get("topic") or payload.get("title") or "-"),
        "timer_unit": str(payload.get("timer_unit") or payload.get("systemd_timer") or "-"),
        "run_kind": str(payload.get("run_kind") or "pipeline"),
        "started_at": _parse_dt(payload.get("started_at") or payload.get("start_time")),
        "ended_at": _parse_dt(payload.get("ended_at") or payload.get("end_time")),
        "updated_at": datetime.utcnow(),
        "source_path": str(run_dir),
        "run_payload": json.dumps(payload, default=str),
    }


def _strip_tags(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", "", value or "")
    return html.unescape(no_tags).strip()


def _extract_p_label(section: str, label: str) -> str:
    match = re.search(rf"<p><strong>{re.escape(label)}:</strong>\s*(.*?)</p>", section, flags=re.S)
    return _strip_tags(match.group(1)) if match else "-"


def _parse_dt_text(value: str) -> datetime | None:
    value = value.strip()
    if not value or value == "-":
        return None
    normalized = value.replace(" ", "T")
    return _parse_dt(normalized)


def _parse_status(status_text: str) -> str:
    lowered = status_text.lower().strip()
    if lowered in {"ok", "success"}:
        return "success"
    if lowered in {"running", "in_progress"}:
        return "running"
    if lowered in {"error", "failed", "fail"}:
        return "failed"
    return lowered or "unknown"


def _parse_snapshot_runs(snapshot_file: Path) -> list[dict[str, Any]]:
    content = snapshot_file.read_text(encoding="utf-8", errors="ignore")
    sections = re.findall(r'<section class="repo-card">(.*?)</section>', content, flags=re.S)
    parsed: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for idx, section in enumerate(sections):
        name_match = re.search(r"<h2>(.*?)</h2>", section, flags=re.S)
        sub_match = re.search(r'<div class="sub">Monitor:\s*(.*?)\s*\|\s*Last update:\s*(.*?)</div>', section, flags=re.S)
        status_match = re.search(r'<div class="badge [^"]*">([^<]+)</div>', section, flags=re.S)
        if not name_match:
            continue

        repo_name = _strip_tags(name_match.group(1))
        monitor_name = _strip_tags(sub_match.group(1)) if sub_match else "unknown"
        updated_at = _parse_dt_text(_strip_tags(sub_match.group(2))) if sub_match else None
        status = _parse_status(_strip_tags(status_match.group(1))) if status_match else "unknown"

        topic = _extract_p_label(section, "Topic")
        run_id_raw = _extract_p_label(section, "Run ID")
        run_id = run_id_raw or f"snapshot-{idx}"
        if run_id in seen_ids:
            run_id = f"{run_id}-{monitor_name}-{idx}"
        seen_ids.add(run_id)

        stage = _extract_p_label(section, "Stage")
        timer_unit = _extract_p_label(section, "Timer Unit")
        next_run = _extract_p_label(section, "Next Run")
        upload_status = _extract_p_label(section, "Upload Status")
        comments_raw = _extract_p_label(section, "Comments")
        final_video = _extract_p_label(section, "Final Video")
        latest_error = _extract_p_label(section, "Latest Error")

        run_success = 0
        run_total = 0
        run_errors = 0
        runs_raw = _extract_p_label(section, "Runs")
        runs_match = re.search(r"(\d+)\s*/\s*(\d+).*errors\s*(\d+)", runs_raw)
        if runs_match:
            run_success = int(runs_match.group(1))
            run_total = int(runs_match.group(2))
            run_errors = int(runs_match.group(3))

        social_links: dict[str, str] = {}
        for href, label in re.findall(r'<a class="social-link" href="([^"]+)"[^>]*>([^<]+)</a>', section, flags=re.S):
            social_links[_strip_tags(label)] = _strip_tags(href)

        upload_platforms: dict[str, str] = {}
        for platform, state in re.findall(r'<span class="chip [^"]*">([^:]+):\s*([^<]+)</span>', section, flags=re.S):
            upload_platforms[_strip_tags(platform)] = _strip_tags(state).lower()

        upload_failures: list[dict[str, str]] = []
        for card in re.findall(r'<div class="fail-card">(.*?)</div>\s*</div>?', section, flags=re.S):
            plat = re.search(r'<div class="fail-platform">(.*?)</div>', card, flags=re.S)
            failed = re.search(r'<div class="fail-time">(.*?)</div>', card, flags=re.S)
            err = re.search(r'<div class="fail-error">(.*?)</div>', card, flags=re.S)
            upload_failures.append(
                {
                    "platform": _strip_tags(plat.group(1)) if plat else "Unknown",
                    "failed_at": _strip_tags(failed.group(1)) if failed else "-",
                    "error": _strip_tags(err.group(1)) if err else "-",
                }
            )

        social_metrics: dict[str, dict[str, Any]] = {}
        for metric_card in re.findall(r'<div class="metric-card">(.*?)</div>\s*</div>?', section, flags=re.S):
            title_match = re.search(r'<div class="metric-title">(.*?)</div>', metric_card, flags=re.S)
            if not title_match:
                continue
            platform_name = _strip_tags(title_match.group(1))
            values: dict[str, Any] = {}
            for k, v in re.findall(r'<div class="metric-line"><span>(.*?)</span><strong>(.*?)</strong></div>', metric_card, flags=re.S):
                key = _strip_tags(k).lower().replace(" ", "_")
                raw_val = _strip_tags(v).replace(",", "")
                try:
                    values[key] = int(raw_val.replace("+", ""))
                except ValueError:
                    values[key] = _strip_tags(v)
            social_metrics[platform_name] = values

        payload: dict[str, Any] = {
            "run_id": run_id,
            "repo_name": repo_name,
            "monitor_name": monitor_name,
            "status": status,
            "stage": stage,
            "topic": topic,
            "timer_unit": timer_unit,
            "run_success": run_success,
            "run_total": run_total,
            "run_errors": run_errors,
            "next_run": next_run,
            "upload_status": upload_status.lower(),
            "upload_platforms": upload_platforms,
            "upload_failures": upload_failures,
            "comments": {"raw": comments_raw},
            "social_links": social_links,
            "social_metrics": social_metrics,
            "final_video": final_video,
            "latest_error": latest_error,
            "started_at": None,
            "ended_at": None,
        }
        parsed.append(
            {
                "id": run_id,
                "repo_name": repo_name,
                "monitor_name": monitor_name,
                "status": status,
                "stage": stage,
                "topic": topic,
                "timer_unit": timer_unit,
                "run_kind": "snapshot",
                "started_at": None,
                "ended_at": None,
                "updated_at": updated_at or datetime.utcnow(),
                "source_path": str(snapshot_file),
                "run_payload": json.dumps(payload, default=str),
            }
        )

    return parsed


def _normalize_remote_run(repo: dict[str, Any], idx: int, source_url: str) -> dict[str, Any]:
    monitor_name = str(repo.get("monitor_name") or repo.get("monitor") or f"remote-{idx}")
    explicit_run_id = repo.get("run_id")
    run_id: str
    if explicit_run_id:
        run_id = str(explicit_run_id)
    else:
        candidate = str(repo.get("id") or f"remote-{idx}")
        run_total_raw = repo.get("run_total")
        run_total = int(run_total_raw) if isinstance(run_total_raw, (int, float, str)) and str(run_total_raw).strip().isdigit() else 0
        # Some monitor feeds only expose a stable channel id/name in `id`.
        # Build a per-run synthetic id from monitor + run_total when possible.
        if run_total > 0 and candidate.strip().lower() in {monitor_name.strip().lower(), str(repo.get("name") or "").strip().lower()}:
            run_id = f"{monitor_name}:{run_total}"
        else:
            run_id = candidate
    status = _parse_status(str(repo.get("status") or repo.get("status_class") or "unknown"))
    payload = {
        "run_id": run_id,
        "repo_name": repo.get("repo_name") or repo.get("name") or "Unknown",
        "monitor_name": monitor_name,
        "status": status,
        "stage": repo.get("stage") or "-",
        "topic": repo.get("topic") or "-",
        "timer_unit": repo.get("timer_unit") or "-",
        "run_success": repo.get("run_success", 0),
        "run_total": repo.get("run_total", 0),
        "run_errors": repo.get("run_errors", 0),
        "next_run": repo.get("next_run", "-"),
        "upload_status": repo.get("upload_status", status),
        "upload_platforms": repo.get("upload_platforms", {}),
        "upload_failures": repo.get("upload_failures", []),
        "comments": repo.get("comments", {}),
        "social_links": repo.get("social_links", {}),
        "social_metrics": repo.get("social_metrics", {}),
        "final_video": repo.get("final_video", "-"),
        "latest_error": repo.get("latest_error", "-"),
        "started_at": repo.get("started_at"),
        "ended_at": repo.get("ended_at"),
    }
    return {
        "id": run_id,
        "repo_name": str(payload["repo_name"]),
        "monitor_name": str(payload["monitor_name"]),
        "status": status,
        "stage": str(payload["stage"]),
        "topic": str(payload["topic"]),
        "timer_unit": str(payload["timer_unit"]),
        "run_kind": "remote_monitor",
        "started_at": _parse_dt(payload.get("started_at")),
        "ended_at": _parse_dt(payload.get("ended_at")),
        "updated_at": _parse_dt(repo.get("updated_at")) or datetime.utcnow(),
        "source_path": source_url,
        "run_payload": json.dumps(payload, default=str),
    }


def _fetch_remote_overview(base_url: str | None) -> list[dict[str, Any]]:
    if not base_url:
        return []
    overview_url = f"{base_url.rstrip('/')}/api/overview"
    try:
        with urllib.request.urlopen(overview_url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    repos = payload.get("repos", []) if isinstance(payload, dict) else []
    if not isinstance(repos, list):
        return []
    normalized: list[dict[str, Any]] = []
    for idx, repo in enumerate(repos):
        if isinstance(repo, dict):
            normalized.append(_normalize_remote_run(repo, idx, base_url))
    return normalized


async def collect_once(broker: SSEBroker | None = None) -> None:
    cfg = load_config()
    runs_dir = Path(cfg.runs_directory)
    run_dirs = sorted([p for p in runs_dir.iterdir() if p.is_dir()]) if runs_dir.exists() else []
    remote_runs = _fetch_remote_overview(cfg.monitor_source_url)
    snapshot_candidates = [ROOT_DIR / "Pipeline Monitor.html", ROOT_DIR / "index.html"]
    snapshot_file = next((p for p in snapshot_candidates if p.exists()), None)
    snapshot_runs = _parse_snapshot_runs(snapshot_file) if snapshot_file else []

    with Session(engine) as session:
        if remote_runs and len(remote_runs) >= len(run_dirs):
            for normalized in remote_runs:
                run_id = normalized["id"]
                existing = session.get(Run, run_id)
                old_status = existing.status if existing else None
                if existing is None:
                    existing = Run(**normalized)
                    session.add(existing)
                    if broker is not None:
                        await broker.publish({"event": "run.new", "data": {"run_id": run_id}})
                else:
                    for key, val in normalized.items():
                        setattr(existing, key, val)

                if old_status and old_status != existing.status and broker is not None:
                    await broker.publish(
                        {
                            "event": "run.status",
                            "data": {"run_id": run_id, "status": existing.status, "previous": old_status},
                        }
                    )
            session.commit()
            return

        # If the preserved monitor snapshot has richer data than local sample runs,
        # prefer it so the modularized monitor view matches the legacy monitor.
        if snapshot_runs and len(snapshot_runs) > len(run_dirs):
            for normalized in snapshot_runs:
                run_id = normalized["id"]
                existing = session.get(Run, run_id)
                old_status = existing.status if existing else None
                if existing is None:
                    existing = Run(**normalized)
                    session.add(existing)
                    if broker is not None:
                        await broker.publish({"event": "run.new", "data": {"run_id": run_id}})
                else:
                    for key, val in normalized.items():
                        setattr(existing, key, val)

                if old_status and old_status != existing.status and broker is not None:
                    await broker.publish(
                        {
                            "event": "run.status",
                            "data": {"run_id": run_id, "status": existing.status, "previous": old_status},
                        }
                    )
            session.commit()
            return

        for run_dir in run_dirs:
            run_json_path = run_dir / "run.json"
            run_payload: dict[str, Any] = {}
            if run_json_path.exists():
                try:
                    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    run_payload = {}

            normalized = _extract_run_payload(run_dir, run_payload)
            run_id = normalized["id"]
            existing = session.get(Run, run_id)
            old_status = existing.status if existing else None
            if existing is None:
                existing = Run(**normalized)
                session.add(existing)
                if broker is not None:
                    await broker.publish({"event": "run.new", "data": {"run_id": run_id}})
            else:
                for key, val in normalized.items():
                    setattr(existing, key, val)

            if old_status and old_status != existing.status and broker is not None:
                await broker.publish(
                    {
                        "event": "run.status",
                        "data": {"run_id": run_id, "status": existing.status, "previous": old_status},
                    }
                )

            events_path = run_dir / "events.jsonl"
            if events_path.exists():
                for idx, raw in enumerate(events_path.read_text(encoding="utf-8").splitlines()):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        event_payload = json.loads(raw)
                    except json.JSONDecodeError:
                        event_payload = {"message": raw, "type": "log"}
                    ev_ts = _parse_dt(event_payload.get("ts") or event_payload.get("timestamp")) or datetime.utcnow()
                    ev_type = str(event_payload.get("type") or event_payload.get("event") or "log")
                    ev_msg = str(event_payload.get("message") or event_payload.get("msg") or "")
                    base = event_payload.get("id") or f"{run_id}:{idx}:{ev_type}:{ev_msg[:30]}"
                    ev_key = str(base)

                    found = session.exec(select(RunEvent).where(RunEvent.event_key == ev_key)).first()
                    if found:
                        continue
                    event = RunEvent(
                        run_id=run_id,
                        event_key=ev_key,
                        event_type=ev_type,
                        ts=ev_ts,
                        message=ev_msg,
                        payload=json.dumps(event_payload, default=str),
                    )
                    session.add(event)
                    if broker is not None:
                        await broker.publish(
                            {
                                "event": "run.event",
                                "data": {"run_id": run_id, "event_type": ev_type, "message": ev_msg},
                            }
                        )

        session.commit()


async def collector_loop(state: CollectorState, broker: SSEBroker) -> None:
    while not state.stop.is_set():
        await collect_once(broker)
        cfg = load_config()
        try:
            await asyncio.wait_for(state.stop.wait(), timeout=cfg.poll_interval_seconds)
        except asyncio.TimeoutError:
            continue
