from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.models.run import Run


def _run_anchor_ts(run: Run) -> datetime:
    return run.started_at or run.ended_at or run.updated_at


def _run_completion_ts(run: Run) -> datetime:
    return run.ended_at or run.updated_at


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _status_bucket(value: str | None) -> str:
    status = (value or "").strip().lower()
    if status in {"running", "in_progress", "queued", "pending"}:
        return "running"
    if status in {"success", "succeeded", "completed", "done", "ok"}:
        return "success"
    if status in {"failed", "error", "canceled", "cancelled", "stale"}:
        return "failed"
    return status or "unknown"


def _run_payload(run: Run) -> dict:
    try:
        payload = json.loads(run.run_payload or "{}")
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def _is_dismissed_failure(run: Run) -> bool:
    payload = _run_payload(run)
    return bool(payload.get("dashboard_failure_dismissed"))


def dismiss_recent_failure(session: Session, run_id: str) -> bool:
    run = session.get(Run, run_id)
    if not run:
        return False
    payload = _run_payload(run)
    payload["dashboard_failure_dismissed"] = True
    payload["dashboard_failure_dismissed_at"] = datetime.utcnow().isoformat()
    run.run_payload = json.dumps(payload)
    session.add(run)
    session.commit()
    return True


def dismiss_all_recent_failures(session: Session) -> int:
    runs = session.exec(select(Run)).all()
    changed = 0
    now_iso = datetime.utcnow().isoformat()
    for run in runs:
        if _status_bucket(run.status) != "failed":
            continue
        payload = _run_payload(run)
        if payload.get("dashboard_failure_dismissed"):
            continue
        payload["dashboard_failure_dismissed"] = True
        payload["dashboard_failure_dismissed_at"] = now_iso
        run.run_payload = json.dumps(payload)
        session.add(run)
        changed += 1
    if changed:
        session.commit()
    return changed


def build_summary_metrics(session: Session) -> dict:
    now = datetime.utcnow()
    day_start = datetime(now.year, now.month, now.day)
    week_start = day_start - timedelta(days=day_start.weekday())
    month_start = datetime(now.year, now.month, 1)
    last_24h = now - timedelta(hours=24)

    runs = session.exec(select(Run)).all()

    runs_today = sum(1 for r in runs if day_start <= _naive_utc(_run_anchor_ts(r)) <= now)
    runs_wtd = sum(1 for r in runs if week_start <= _naive_utc(_run_anchor_ts(r)) <= now)
    runs_mtd = sum(1 for r in runs if month_start <= _naive_utc(_run_anchor_ts(r)) <= now)
    running_now = sum(1 for r in runs if _status_bucket(r.status) == "running")
    failures_today = sum(
        1
        for r in runs
        if _status_bucket(r.status) == "failed"
        and not _is_dismissed_failure(r)
        and day_start <= _naive_utc(_run_completion_ts(r)) <= now
    )

    finished = [
        r
        for r in runs
        if _status_bucket(r.status) in {"success", "failed"}
        and (_status_bucket(r.status) != "failed" or not _is_dismissed_failure(r))
        and day_start <= _naive_utc(_run_completion_ts(r)) <= now
    ]
    successes = sum(1 for r in finished if _status_bucket(r.status) == "success")
    success_rate = (successes / len(finished) * 100.0) if finished else 0.0

    total_last_24h = sum(1 for r in runs if last_24h <= _naive_utc(_run_anchor_ts(r)) <= now)

    recent_failures = [
        {
            "id": r.id,
            "repo_name": r.repo_name,
            "stage": r.stage,
            "updated_at": r.updated_at,
            "status": r.status,
        }
        for r in sorted(runs, key=lambda x: x.updated_at, reverse=True)
        if _status_bucket(r.status) == "failed" and not _is_dismissed_failure(r)
    ][:8]

    live_active_runs = [
        {
            "id": r.id,
            "repo_name": r.repo_name,
            "stage": r.stage,
            "status": r.status,
            "started_at": r.started_at,
            "updated_at": r.updated_at,
        }
        for r in sorted(runs, key=lambda x: x.updated_at, reverse=True)
        if _status_bucket(r.status) == "running"
    ][:20]

    return {
        "runs_today": runs_today,
        "runs_wtd": runs_wtd,
        "runs_mtd": runs_mtd,
        "running_now": running_now,
        "failures_today": failures_today,
        "success_rate": round(success_rate, 2),
        "total_last_24h": total_last_24h,
        "recent_failures": recent_failures,
        "live_active_runs": live_active_runs,
    }
