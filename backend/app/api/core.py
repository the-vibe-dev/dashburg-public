from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.config import load_config, update_config
from app.db.session import get_session
from app.models.run import Run
from app.modules.registry import get_modules
from app.schemas.common import HealthResponse, MetricsSummary, ModuleInfo
from app.schemas.config import ConfigResponse, ConfigUpdate
from app.services.metrics import build_summary_metrics, dismiss_all_recent_failures, dismiss_recent_failure
from app.services.monitor_proxy import get_monitor_live

router = APIRouter(prefix="/api", tags=["core"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, service="dashgithub", timestamp=datetime.utcnow())


@router.get("/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    cfg = load_config()
    return ConfigResponse.model_validate(cfg.model_dump())


@router.put("/config", response_model=ConfigResponse)
def put_config(payload: ConfigUpdate) -> ConfigResponse:
    patch = payload.model_dump(exclude_none=True)
    cfg = update_config(patch)
    return ConfigResponse.model_validate(cfg.model_dump())


@router.get("/modules", response_model=list[ModuleInfo])
def get_registered_modules() -> list[ModuleInfo]:
    modules = get_modules()
    return [
        ModuleInfo(
            key=m.key,
            name=m.name,
            sidebar_label=m.sidebar_label,
            routes=[{"path": r["path"], "label": r["label"]} for r in m.routes],
            cards=[{"title": c["title"], "description": c["description"], "href": c["href"]} for c in m.cards],
        )
        for m in modules
    ]


@router.get("/metrics/summary", response_model=MetricsSummary)
async def metrics_summary(session: Session = Depends(get_session)) -> MetricsSummary:
    metrics = build_summary_metrics(session)
    try:
        monitor = await get_monitor_live()
        if monitor.get("ok"):
            summary = monitor.get("summary", {})
            metrics["running_now"] = summary.get("running", metrics["running_now"])
            for key in ("runs_today", "runs_wtd", "runs_mtd"):
                if key in summary and isinstance(summary.get(key), (int, float)):
                    metrics[key] = int(summary[key])
            running_repos = monitor.get("running", [])
            if running_repos:
                metrics["live_active_runs"] = [
                    {
                        "id": r.get("run_id", "-"),
                        "repo_name": r.get("display_name") or r.get("repo", "-"),
                        "stage": r.get("last_stage", "-"),
                        "status": "running",
                        "started_at": r.get("run_started_at"),
                        "updated_at": r.get("last_update"),
                    }
                    for r in running_repos
                ][:20]
    except Exception:
        logger.exception("Failed to merge live monitor metrics into summary response")
    return MetricsSummary.model_validate(metrics)


@router.delete("/metrics/recent-failures/{run_id}")
def remove_recent_failure(run_id: str, session: Session = Depends(get_session)) -> dict:
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not dismiss_recent_failure(session, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {"ok": True, "run_id": run_id, "dismissed": True}


@router.post("/metrics/recent-failures/clear")
def clear_recent_failures(session: Session = Depends(get_session)) -> dict:
    changed = dismiss_all_recent_failures(session)
    return {"ok": True, "dismissed": changed}
