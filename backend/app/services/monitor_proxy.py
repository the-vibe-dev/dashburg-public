"""Thin proxy that fetches live data from the remote monitor portal.

Caches the last good response for TTL seconds so every frontend request
doesn't create a new TCP connection to the monitor host.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import load_config

_TTL = 15.0  # seconds

_cache: dict[str, Any] = {
    "data": None,
    "ts": 0.0,
}
_lock = asyncio.Lock()
_PERIOD_PATH = Path(__file__).resolve().parents[3] / "data" / "monitor_period_rollup.json"


def _platform_slug(value: str) -> str:
    slug = (value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    if slug in {"yt", "youtube"}:
        return "youtube"
    if slug in {"fb", "facebook", "meta"}:
        return "facebook"
    if slug in {"ig", "instagram"}:
        return "instagram"
    return (value or "").strip().lower()


def _normalize_upload_failures(failures: Any) -> list[dict[str, str]]:
    if not isinstance(failures, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in failures:
        if not isinstance(item, dict):
            continue
        platform_key = _platform_slug(str(item.get("platform") or ""))
        if platform_key not in {"youtube", "facebook", "instagram"}:
            continue
        error = str(item.get("error") or "").strip()
        when = str(item.get("when") or "").strip()
        key = platform_key
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "platform": platform_key,
                "label": {
                    "youtube": "YouTube",
                    "facebook": "Facebook",
                    "instagram": "Instagram",
                }[platform_key],
                "error": error or "Upload failed with no error detail.",
                "when": when or "-",
            }
        )
    return out


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        if cleaned in {"", "-", "n/a"}:
            return 0
        try:
            return int(float(cleaned))
        except ValueError:
            return 0
    return 0


def _live_running_repos(ai_root: Path = Path("/srv/dashgithub/ai")) -> set[str]:
    root = ai_root.resolve()
    root_text = str(root)
    script_pattern = re.compile(re.escape(root_text) + r"/([^/\s]+)/([^\s/]+\.py)")
    ignored = {".venv", "monitor", "trends"}
    ignored_scripts = {
        "app.py",
        "comment.py",
        "comments.py",
        "fb_bot.py",
        "ig_bot.py",
        "social_metrics.py",
        "portal.py",
        "oauth.py",
    }
    try:
        output = subprocess.check_output(["ps", "-eo", "args="], text=True, timeout=2.0)
    except Exception:
        return set()

    repos: set[str] = set()
    for cmd in output.splitlines():
        if root_text not in cmd:
            continue
        for match in script_pattern.finditer(cmd):
            repo = match.group(1).strip().lower()
            script_name = match.group(2).strip().lower()
            if not repo or repo in ignored or repo.startswith("."):
                continue
            if script_name in ignored_scripts:
                continue
            repos.add(repo)
    return repos


def _merge_live_running_into_overview(overview: dict[str, Any]) -> dict[str, Any]:
    repos = overview.get("repos")
    if not isinstance(repos, list):
        return overview
    running = overview.get("running")
    if not isinstance(running, list):
        running = []

    repo_index: dict[str, dict[str, Any]] = {}
    for row in repos:
        if not isinstance(row, dict):
            continue
        repo_key = str(row.get("repo") or "").strip().lower()
        if repo_key:
            repo_index[repo_key] = row

    running_keys = {
        str(item.get("repo") or item.get("repo_name") or "").strip().lower()
        for item in running
        if isinstance(item, dict)
    }

    for repo in sorted(_live_running_repos()):
        existing = repo_index.get(repo)
        if existing is None:
            existing = {
                "repo": repo,
                "display_name": repo,
                "channel_icon_url": "",
                "platform_links": {},
                "last_update": datetime.now(timezone.utc).isoformat(),
                "last_update_epoch": int(time.time()),
                "status": "running",
                "status_badge": "running",
                "stuck": False,
                "topic": "",
                "run_id": "",
                "last_stage": "process_active",
                "upload_status": "running",
                "upload_states": {},
                "upload_failures": [],
                "yt_data": {"available": False},
                "fb_data": {"available": False},
                "ig_data": {"available": False},
                "runs_total": 0,
                "runs_success": 0,
                "runs_error": 0,
                "success_rate": 0,
                "next_run": "-",
                "next_run_in": "-",
                "next_timer_unit": "",
                "comment_next_run": "-",
                "comment_next_run_in": "-",
                "comment_service_active": None,
                "run_elapsed": "live process",
                "stage_elapsed": "live process",
                "run_started_at": "",
                "top_error": "",
                "comment": "",
                "final_video": "",
                "diagnostics": [],
            }
            repos.append(existing)
            repo_index[repo] = existing
        existing["live_process"] = True
        existing["status"] = "running"
        existing["status_badge"] = "running"
        if not str(existing.get("last_stage") or "").strip():
            existing["last_stage"] = "process_active"
        if repo not in running_keys:
            running.append(existing)
            running_keys.add(repo)

    overview["repos"] = repos
    overview["running"] = running
    overview["summary"] = {
        "repos": len(repos),
        "healthy": sum(1 for r in repos if isinstance(r, dict) and r.get("status_badge") == "ok"),
        "running": sum(1 for r in repos if isinstance(r, dict) and r.get("status_badge") == "running"),
        "errors": sum(
            1
            for r in repos
            if isinstance(r, dict) and r.get("status_badge") == "error" and not bool(r.get("stuck"))
        ),
        "stuck": sum(1 for r in repos if isinstance(r, dict) and bool(r.get("stuck"))),
    }
    return overview


def _platform_blob(repo: dict[str, Any], platform: str) -> dict[str, Any]:
    # Prefer explicit legacy monitor fields if present.
    key_map = {"youtube": "yt_data", "facebook": "fb_data", "instagram": "ig_data"}
    blob = repo.get(key_map[platform])
    if isinstance(blob, dict):
        return blob
    # Fallback to social_metrics map.
    social = repo.get("social_metrics")
    if isinstance(social, dict):
        v = social.get(platform)
        if isinstance(v, dict):
            return v
    return {}


def _synthesize_rollup_from_repos(overview: dict[str, Any]) -> dict[str, Any]:
    repos = overview.get("repos")
    if not isinstance(repos, list):
        return overview

    target = overview.get("live_rollup")
    if not isinstance(target, dict):
        target = overview.get("rollup")
    if not isinstance(target, dict):
        target = {}

    by_platform = target.get("by_platform")
    if not isinstance(by_platform, dict):
        by_platform = {}

    agg: dict[str, dict[str, int]] = {
        "youtube": {"views_total": 0, "subs_total": 0, "views_d0": 0, "views_d1": 0, "views_d7": 0, "views_d30": 0, "subs_d0": 0, "subs_d1": 0, "subs_d30": 0},
        "facebook": {"views_total": 0, "subs_total": 0, "views_d0": 0, "views_d1": 0, "views_d7": 0, "views_d30": 0, "subs_d0": 0, "subs_d1": 0, "subs_d30": 0},
        "instagram": {"views_total": 0, "subs_total": 0, "views_d0": 0, "views_d1": 0, "views_d7": 0, "views_d30": 0, "subs_d0": 0, "subs_d1": 0, "subs_d30": 0},
    }
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        for platform in ("youtube", "facebook", "instagram"):
            blob = _platform_blob(repo, platform)
            if not isinstance(blob, dict):
                continue
            agg[platform]["views_total"] += _to_int(blob.get("views_total", blob.get("views_lifetime", blob.get("views", 0))))
            agg[platform]["subs_total"] += _to_int(blob.get("subs_total", blob.get("followers", 0)))
            agg[platform]["views_d0"] += _to_int(blob.get("views_d0", blob.get("views_d1", 0)))
            agg[platform]["views_d1"] += _to_int(blob.get("views_d1", 0))
            agg[platform]["views_d7"] += _to_int(blob.get("views_d7", 0))
            agg[platform]["views_d30"] += _to_int(blob.get("views_d30", 0))
            agg[platform]["subs_d0"] += _to_int(blob.get("subs_d0", blob.get("subs_d1", 0)))
            agg[platform]["subs_d1"] += _to_int(blob.get("subs_d1", 0))
            agg[platform]["subs_d30"] += _to_int(blob.get("subs_d30", 0))

    for platform, values in agg.items():
        existing = by_platform.get(platform)
        if not isinstance(existing, dict):
            existing = {}
        existing.setdefault("views_total", values["views_total"])
        existing.setdefault("subs_total", values["subs_total"])
        views_delta = existing.get("views_delta")
        if not isinstance(views_delta, dict):
            views_delta = {}
        if "d0" not in views_delta or (_to_int(views_delta.get("d0")) == 0 and values["views_d0"] > 0):
            views_delta["d0"] = values["views_d0"]
        if "d1" not in views_delta or (_to_int(views_delta.get("d1")) == 0 and values["views_d1"] > 0):
            views_delta["d1"] = values["views_d1"]
        if "d7" not in views_delta or (_to_int(views_delta.get("d7")) == 0 and values["views_d7"] > 0):
            views_delta["d7"] = values["views_d7"]
        if "d30" not in views_delta or (_to_int(views_delta.get("d30")) == 0 and values["views_d30"] > 0):
            views_delta["d30"] = values["views_d30"]
        existing["views_delta"] = views_delta
        subs_delta = existing.get("subs_delta")
        if not isinstance(subs_delta, dict):
            subs_delta = {}
        if "d0" not in subs_delta or (_to_int(subs_delta.get("d0")) == 0 and values["subs_d0"] != 0):
            subs_delta["d0"] = values["subs_d0"]
        if "d1" not in subs_delta or (_to_int(subs_delta.get("d1")) == 0 and values["subs_d1"] != 0):
            subs_delta["d1"] = values["subs_d1"]
        if "d30" not in subs_delta or (_to_int(subs_delta.get("d30")) == 0 and values["subs_d30"] != 0):
            subs_delta["d30"] = values["subs_d30"]
        existing["subs_delta"] = subs_delta
        by_platform[platform] = existing

    target["by_platform"] = by_platform
    if "views_total" not in target or _to_int(target.get("views_total")) == 0:
        target["views_total"] = sum(v.get("views_total", 0) for v in agg.values())
    if "subs_total" not in target or _to_int(target.get("subs_total")) == 0:
        target["subs_total"] = sum(v.get("subs_total", 0) for v in agg.values())
    views_delta_all = target.get("views_delta")
    if not isinstance(views_delta_all, dict):
        views_delta_all = {}
    views_rollup = {
        "d0": sum(v.get("views_d0", 0) for v in agg.values()),
        "d1": sum(v.get("views_d1", 0) for v in agg.values()),
        "d7": sum(v.get("views_d7", 0) for v in agg.values()),
        "d30": sum(v.get("views_d30", 0) for v in agg.values()),
    }
    for key, value in views_rollup.items():
        if key not in views_delta_all or (_to_int(views_delta_all.get(key)) == 0 and value > 0):
            views_delta_all[key] = value
    target["views_delta"] = views_delta_all

    subs_delta_all = target.get("subs_delta")
    if not isinstance(subs_delta_all, dict):
        subs_delta_all = {}
    subs_rollup = {
        "d0": sum(v.get("subs_d0", 0) for v in agg.values()),
        "d1": sum(v.get("subs_d1", 0) for v in agg.values()),
        "d30": sum(v.get("subs_d30", 0) for v in agg.values()),
    }
    for key, value in subs_rollup.items():
        if key not in subs_delta_all or (_to_int(subs_delta_all.get(key)) == 0 and value != 0):
            subs_delta_all[key] = value
    target["subs_delta"] = subs_delta_all

    if "live_rollup" in overview and isinstance(overview.get("live_rollup"), dict):
        overview["live_rollup"] = target
    else:
        overview["rollup"] = target
    return overview


def _normalize_monitor_shape(overview: dict[str, Any]) -> dict[str, Any]:
    repos = overview.get("repos", [])
    if isinstance(repos, list):
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            states = repo.get("upload_states")
            if isinstance(states, dict):
                repo["upload_states"] = {_platform_slug(str(k)): str(v).lower() for k, v in states.items()}
            failures = _normalize_upload_failures(repo.get("upload_failures"))
            repo["upload_failures"] = failures
            for item in failures:
                platform = item["platform"]
                repo.setdefault("upload_states", {})
                if repo["upload_states"].get(platform) not in {"ok", "pending", "off"}:
                    repo["upload_states"][platform] = "fail"
            if failures and str(repo.get("top_error") or "").strip() in {"", "-", "unknown"}:
                repo["top_error"] = f"{failures[0]['label']}: {failures[0]['error']}"
            social = repo.get("social_metrics")
            if isinstance(social, dict):
                repo["social_metrics"] = {_platform_slug(str(k)): v for k, v in social.items()}
    for rollup_key in ("live_rollup", "rollup"):
        rollup = overview.get(rollup_key)
        if isinstance(rollup, dict):
            by_platform = rollup.get("by_platform")
            if isinstance(by_platform, dict):
                rollup["by_platform"] = {_platform_slug(str(k)): v for k, v in by_platform.items()}
    return overview


def _recompute_upload_state_counts(overview: dict[str, Any]) -> dict[str, Any]:
    repos = overview.get("repos")
    if not isinstance(repos, list):
        return overview
    rollup = overview.get("live_rollup")
    if not isinstance(rollup, dict):
        rollup = overview.get("rollup")
    if not isinstance(rollup, dict):
        return overview

    counts = {"ok": 0, "fail": 0, "pending": 0, "off": 0, "unknown": 0}
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        states = repo.get("upload_states")
        if not isinstance(states, dict):
            continue
        for value in states.values():
            state = str(value or "").strip().lower()
            if state in {"ok", "success"}:
                counts["ok"] += 1
            elif state in {"fail", "failed", "error"}:
                counts["fail"] += 1
            elif state in {"pending", "running"}:
                counts["pending"] += 1
            elif state in {"off", "disabled"}:
                counts["off"] += 1
            else:
                counts["unknown"] += 1

    rollup["upload_states"] = counts
    if "live_rollup" in overview and isinstance(overview.get("live_rollup"), dict):
        overview["live_rollup"] = rollup
    else:
        overview["rollup"] = rollup
    return overview


def _attach_repo_diagnostics(overview: dict[str, Any]) -> dict[str, Any]:
    repos = overview.get("repos")
    if not isinstance(repos, list):
        return overview
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        failures = repo.get("upload_failures")
        states = repo.get("upload_states")
        diagnostics: list[dict[str, str]] = []
        if isinstance(states, dict):
            for platform, state in states.items():
                normalized = _platform_slug(str(platform))
                state_text = str(state or "").lower()
                if state_text in {"fail", "failed", "error"}:
                    diagnostics.append(
                        {
                            "severity": "error",
                            "scope": "upload",
                            "platform": normalized,
                            "message": f"{normalized} upload state is {state_text}",
                            "action": "Check token, profile mapping, and payload constraints.",
                        }
                    )
                elif state_text in {"pending", "running"}:
                    diagnostics.append(
                        {
                            "severity": "info",
                            "scope": "upload",
                            "platform": normalized,
                            "message": f"{normalized} upload is still in progress",
                            "action": "Wait briefly, then inspect run logs if it remains pending.",
                        }
                    )
        if isinstance(failures, list):
            for item in failures:
                if not isinstance(item, dict):
                    continue
                diagnostics.append(
                    {
                        "severity": "error",
                        "scope": "upload",
                        "platform": _platform_slug(str(item.get("platform") or "")),
                        "message": str(item.get("error") or "Upload failed"),
                        "action": "Resolve credentials or platform constraints, then retry.",
                    }
                )
        top_error = str(repo.get("top_error") or "").strip()
        if top_error and top_error not in {"-", "unknown"}:
            diagnostics.append(
                {
                    "severity": "error",
                    "scope": "pipeline",
                    "platform": "general",
                    "message": top_error,
                    "action": "Inspect stage logs and rerun once the failing dependency is fixed.",
                }
            )
        repo["diagnostics"] = diagnostics[:8]
    return overview


def _load_period_store() -> dict[str, Any]:
    if not _PERIOD_PATH.exists():
        return {"days": {}}
    try:
        raw = json.loads(_PERIOD_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("days"), dict):
            return raw
    except Exception:
        pass
    return {"days": {}}


def _save_period_store(store: dict[str, Any]) -> None:
    _PERIOD_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PERIOD_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _apply_period_totals(overview: dict[str, Any]) -> dict[str, Any]:
    rollup = overview.get("live_rollup")
    if not isinstance(rollup, dict):
        rollup = overview.get("rollup")
    if not isinstance(rollup, dict):
        return overview
    by_platform = rollup.get("by_platform")
    if not isinstance(by_platform, dict):
        by_platform = {}

    now_dt = datetime.now(timezone.utc)
    today = now_dt.strftime("%Y-%m-%d")
    week_start = (now_dt - timedelta(days=now_dt.weekday())).date()
    month_start = now_dt.replace(day=1).date()

    store = _load_period_store()
    days = store.get("days")
    if not isinstance(days, dict):
        days = {}
        store["days"] = days

    today_entry = days.get(today)
    if not isinstance(today_entry, dict):
        today_entry = {"views_delta": {"d0": 0}, "by_platform": {}}
        days[today] = today_entry

    day_by_platform = today_entry.get("by_platform")
    if not isinstance(day_by_platform, dict):
        day_by_platform = {}
        today_entry["by_platform"] = day_by_platform

    # Persist the latest known "today" values (monotonic during the day).
    top_views = rollup.get("views_delta")
    top_d0 = _to_int(top_views.get("d0")) if isinstance(top_views, dict) else 0
    today_entry["views_delta"] = {"d0": max(_to_int((today_entry.get("views_delta") or {}).get("d0")), top_d0)}
    for platform in ("youtube", "facebook", "instagram"):
        pdata = by_platform.get(platform)
        if not isinstance(pdata, dict):
            continue
        vd = pdata.get("views_delta")
        pd0 = _to_int(vd.get("d0")) if isinstance(vd, dict) else 0
        prev = day_by_platform.get(platform)
        prev_d0 = _to_int((prev.get("views_delta") or {}).get("d0")) if isinstance(prev, dict) else 0
        day_by_platform[platform] = {"views_delta": {"d0": max(prev_d0, pd0)}}

    # Trim to ~120 days.
    keep_after = (now_dt - timedelta(days=120)).strftime("%Y-%m-%d")
    for key in list(days.keys()):
        if key < keep_after:
            del days[key]
    _save_period_store(store)

    wtd = 0
    mtd = 0
    platform_wtd: dict[str, int] = {"youtube": 0, "facebook": 0, "instagram": 0}
    platform_mtd: dict[str, int] = {"youtube": 0, "facebook": 0, "instagram": 0}
    for day_key, day_data in days.items():
        try:
            day_date = datetime.strptime(day_key, "%Y-%m-%d").date()
        except Exception:
            continue
        d0 = _to_int(((day_data.get("views_delta") or {}) if isinstance(day_data, dict) else {}).get("d0"))
        if day_date >= week_start:
            wtd += d0
        if day_date >= month_start:
            mtd += d0
        byp = day_data.get("by_platform") if isinstance(day_data, dict) else {}
        if isinstance(byp, dict):
            for platform in ("youtube", "facebook", "instagram"):
                pv = byp.get(platform)
                pv_d0 = _to_int(((pv.get("views_delta") or {}) if isinstance(pv, dict) else {}).get("d0"))
                if day_date >= week_start:
                    platform_wtd[platform] += pv_d0
                if day_date >= month_start:
                    platform_mtd[platform] += pv_d0

    views_delta = rollup.get("views_delta")
    if not isinstance(views_delta, dict):
        views_delta = {}
    views_delta["wtd"] = wtd
    views_delta["mtd"] = mtd
    rollup["views_delta"] = views_delta

    for platform in ("youtube", "facebook", "instagram"):
        pdata = by_platform.get(platform)
        if not isinstance(pdata, dict):
            continue
        vd = pdata.get("views_delta")
        if not isinstance(vd, dict):
            vd = {}
        vd["wtd"] = platform_wtd[platform]
        vd["mtd"] = platform_mtd[platform]
        pdata["views_delta"] = vd
        by_platform[platform] = pdata
    rollup["by_platform"] = by_platform

    if "live_rollup" in overview and isinstance(overview.get("live_rollup"), dict):
        overview["live_rollup"] = rollup
    else:
        overview["rollup"] = rollup
    return overview


def _apply_run_period_totals(overview: dict[str, Any]) -> dict[str, Any]:
    repos = overview.get("repos")
    if not isinstance(repos, list):
        return overview

    now_dt = datetime.now(timezone.utc)
    today = now_dt.strftime("%Y-%m-%d")
    week_start = (now_dt - timedelta(days=now_dt.weekday())).date()
    month_start = now_dt.replace(day=1).date()

    store = _load_period_store()
    run_days = store.get("run_days")
    if not isinstance(run_days, dict):
        run_days = {}
        store["run_days"] = run_days

    today_entry = run_days.get(today)
    if not isinstance(today_entry, dict):
        today_entry = {"baseline": {}, "latest": {}}
        run_days[today] = today_entry
    baseline = today_entry.get("baseline")
    latest = today_entry.get("latest")
    if not isinstance(baseline, dict):
        baseline = {}
        today_entry["baseline"] = baseline
    if not isinstance(latest, dict):
        latest = {}
        today_entry["latest"] = latest

    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo_key = str(repo.get("repo") or repo.get("repo_name") or "").strip().lower()
        if not repo_key:
            continue
        current_total = _to_int(repo.get("runs_total"))
        if repo_key not in baseline:
            baseline[repo_key] = current_total
        prev_latest = _to_int(latest.get(repo_key))
        latest[repo_key] = max(prev_latest, current_total)

    def _day_delta(day_entry: Any) -> int:
        if not isinstance(day_entry, dict):
            return 0
        b = day_entry.get("baseline") if isinstance(day_entry.get("baseline"), dict) else {}
        l = day_entry.get("latest") if isinstance(day_entry.get("latest"), dict) else {}
        keys = set(b.keys()) | set(l.keys())
        total = 0
        for key in keys:
            lv = _to_int(l.get(key))
            bv = _to_int(b.get(key, lv))
            total += max(0, lv - bv)
        return total

    runs_today = _day_delta(today_entry)
    runs_wtd = 0
    runs_mtd = 0
    for day_key, day_entry in run_days.items():
        try:
            day_date = datetime.strptime(day_key, "%Y-%m-%d").date()
        except Exception:
            continue
        delta = _day_delta(day_entry)
        if day_date >= week_start:
            runs_wtd += delta
        if day_date >= month_start:
            runs_mtd += delta

    keep_after = (now_dt - timedelta(days=120)).strftime("%Y-%m-%d")
    for key in list(run_days.keys()):
        if key < keep_after:
            del run_days[key]
    _save_period_store(store)

    summary = overview.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        overview["summary"] = summary
    summary["runs_today"] = runs_today
    summary["runs_wtd"] = runs_wtd
    summary["runs_mtd"] = runs_mtd
    return overview


def _make_opener(user: str, password: str) -> urllib.request.OpenerDirector:
    """Return an opener that sends Basic Auth on every request."""
    if not user:
        return urllib.request.build_opener()
    credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
    handler = urllib.request.BaseHandler()
    opener = urllib.request.build_opener()

    class _AuthHandler(urllib.request.BaseHandler):
        def http_request(self, req: urllib.request.Request) -> urllib.request.Request:
            req.add_unredirected_header("Authorization", f"Basic {credentials}")
            return req

        https_request = http_request

    return urllib.request.build_opener(_AuthHandler())


def _fetch_url(url: str, opener: urllib.request.OpenerDirector, timeout: float = 5.0) -> dict[str, Any]:
    with opener.open(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, opener: urllib.request.OpenerDirector, payload: dict[str, Any] | None = None, timeout: float = 8.0) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    if not raw.strip():
        return {}
    return json.loads(raw)


def _build_overview(base_url: str, user: str, password: str) -> dict[str, Any]:
    """Fetch /api/overview and, if available, /api/rollup for delta data."""
    opener = _make_opener(user, password)
    overview = _fetch_url(f"{base_url}/api/overview", opener, timeout=5.0)

    try:
        rollup = _fetch_url(f"{base_url}/api/rollup", opener, timeout=3.0)
        # The monitor rollup has richer delta fields than the overview rollup
        overview["live_rollup"] = rollup.get("rollup", rollup)
    except Exception:
        pass

    overview = _normalize_monitor_shape(overview)
    overview = _synthesize_rollup_from_repos(overview)
    overview = _recompute_upload_state_counts(overview)
    overview = _apply_period_totals(overview)
    overview = _attach_repo_diagnostics(overview)
    overview = _merge_live_running_into_overview(overview)

    # Derive summary + running list the frontend expects (monitor omits these)
    repos = overview.get("repos", [])
    runs_total = sum(_to_int(r.get("runs_total")) for r in repos if isinstance(r, dict))
    runs_success = sum(_to_int(r.get("runs_success")) for r in repos if isinstance(r, dict))
    runs_error = sum(_to_int(r.get("runs_error")) for r in repos if isinstance(r, dict))
    overview["summary"] = {
        "repos": len(repos),
        "healthy": sum(1 for r in repos if r.get("status_badge") == "ok"),
        "running": sum(1 for r in repos if r.get("status_badge") == "running"),
        "errors": sum(1 for r in repos if r.get("status_badge") == "error" and not r.get("stuck")),
        "stuck": sum(1 for r in repos if r.get("stuck")),
        "runs_total": runs_total,
        "runs_success": runs_success,
        "runs_error": runs_error,
    }
    overview = _apply_run_period_totals(overview)
    overview["running"] = [r for r in repos if r.get("status_badge") == "running"]

    overview["ok"] = True
    overview["fetched_at"] = time.time()
    return overview


async def get_monitor_live() -> dict[str, Any]:
    """Return cached monitor overview, refreshing when stale."""
    now = time.monotonic()
    if _cache["data"] is not None and (now - _cache["ts"]) < _TTL:
        return _cache["data"]

    async with _lock:
        # Re-check after acquiring the lock (another coroutine may have refreshed)
        now = time.monotonic()
        if _cache["data"] is not None and (now - _cache["ts"]) < _TTL:
            return _cache["data"]

        cfg = load_config()
        base_url = (cfg.monitor_source_url or "").rstrip("/")
        if not base_url:
            return _error("No monitor_source_url configured", _cache.get("data"))

        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None, _build_overview, base_url, cfg.monitor_auth_user, cfg.monitor_auth_password
            )
        except Exception as exc:
            return _error(str(exc), _cache.get("data"))

        _cache["data"] = data
        _cache["ts"] = time.monotonic()
        return data


def _error(msg: str, stale: dict[str, Any] | None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ok": False,
        "error": msg,
        "repos": [],
        "running": [],
        "summary": {"repos": 0, "healthy": 0, "running": 0, "errors": 0},
        "rollup": {},
    }
    if stale is not None:
        return {**stale, "ok": False, "stale": True, "error": msg}
    return base


async def clear_monitor_failures() -> dict[str, Any]:
    """Clear upload failure markers on the monitor source and invalidate live cache."""
    cfg = load_config()
    base_url = (cfg.monitor_source_url or "").rstrip("/")
    if not base_url:
        return {"ok": False, "error": "No monitor_source_url configured"}

    opener = _make_opener(cfg.monitor_auth_user, cfg.monitor_auth_password)
    loop = asyncio.get_event_loop()

    try:
        result = await loop.run_in_executor(None, _post_json, f"{base_url}/api/failures/clear", opener, {})
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    async with _lock:
        _cache["data"] = None
        _cache["ts"] = 0.0

    if isinstance(result, dict):
        return {"ok": bool(result.get("ok", True)), **result}
    return {"ok": True}
