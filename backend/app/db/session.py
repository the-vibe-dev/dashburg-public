from __future__ import annotations

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401  # ensure model metadata is registered
from app.core.paths import db_path, ensure_runtime_dirs


DB_PATH = db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)


def init_db() -> None:
    ensure_runtime_dirs()
    SQLModel.metadata.create_all(engine)
    # Lightweight sqlite migrations for additive columns on existing installs.
    with engine.begin() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info('project')"))]
        if "priority_rank" not in cols:
            conn.execute(text("ALTER TABLE project ADD COLUMN priority_rank INTEGER"))
        vv_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('viralvideo_scripts')"))]
        if vv_cols:
            if "channel_profile_id" not in vv_cols:
                conn.execute(text("ALTER TABLE viralvideo_scripts ADD COLUMN channel_profile_id TEXT"))
            if "creator_type" not in vv_cols:
                conn.execute(text("ALTER TABLE viralvideo_scripts ADD COLUMN creator_type TEXT DEFAULT 'vidmaker'"))
            if "generation_params_json" not in vv_cols:
                conn.execute(text("ALTER TABLE viralvideo_scripts ADD COLUMN generation_params_json TEXT DEFAULT '{}'"))
            if "validation_status" not in vv_cols:
                conn.execute(text("ALTER TABLE viralvideo_scripts ADD COLUMN validation_status TEXT DEFAULT 'unknown'"))
            if "validation_result_json" not in vv_cols:
                conn.execute(
                    text(
                        "ALTER TABLE viralvideo_scripts ADD COLUMN validation_result_json TEXT DEFAULT '{\"errors\":[],\"warnings\":[]}'"
                    )
                )
        run_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('viralvideo_runs')"))]
        if run_cols:
            if "channel_profile_id" not in run_cols:
                conn.execute(text("ALTER TABLE viralvideo_runs ADD COLUMN channel_profile_id TEXT"))
            if "script_snapshot_json" not in run_cols:
                conn.execute(text("ALTER TABLE viralvideo_runs ADD COLUMN script_snapshot_json TEXT DEFAULT '{}'"))
            if "generation_params_snapshot_json" not in run_cols:
                conn.execute(text("ALTER TABLE viralvideo_runs ADD COLUMN generation_params_snapshot_json TEXT DEFAULT '{}'"))
            if "validation_snapshot_json" not in run_cols:
                conn.execute(text("ALTER TABLE viralvideo_runs ADD COLUMN validation_snapshot_json TEXT DEFAULT '{}'"))
        exp_post_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('viralvideo_experiment_posts')"))]
        if exp_post_cols:
            if "score_components_json" not in exp_post_cols:
                conn.execute(text("ALTER TABLE viralvideo_experiment_posts ADD COLUMN score_components_json TEXT DEFAULT '{}'"))
            if "attribution_date" not in exp_post_cols:
                conn.execute(text("ALTER TABLE viralvideo_experiment_posts ADD COLUMN attribution_date TEXT DEFAULT ''"))
        exp_day_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('viralvideo_experiment_days')"))]
        if exp_day_cols:
            if "plan_json" not in exp_day_cols:
                conn.execute(text("ALTER TABLE viralvideo_experiment_days ADD COLUMN plan_json TEXT DEFAULT '{}'"))
        localops_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('localops_settings')"))]
        if localops_cols and "terminal_idle_timeout_minutes" not in localops_cols:
            conn.execute(text("ALTER TABLE localops_settings ADD COLUMN terminal_idle_timeout_minutes INTEGER DEFAULT 30"))
        localops_thread_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('localops_threads')"))]
        if localops_thread_cols and "provider_endpoint_id" not in localops_thread_cols:
            conn.execute(text("ALTER TABLE localops_threads ADD COLUMN provider_endpoint_id INTEGER"))
        localops_run_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('localops_runs')"))]
        if localops_run_cols:
            if "llm_status" not in localops_run_cols:
                conn.execute(text("ALTER TABLE localops_runs ADD COLUMN llm_status TEXT DEFAULT 'queued'"))
            if "provider_endpoint_id" not in localops_run_cols:
                conn.execute(text("ALTER TABLE localops_runs ADD COLUMN provider_endpoint_id INTEGER"))
            if "endpoint_label" not in localops_run_cols:
                conn.execute(text("ALTER TABLE localops_runs ADD COLUMN endpoint_label TEXT DEFAULT ''"))
            if "endpoint_url" not in localops_run_cols:
                conn.execute(text("ALTER TABLE localops_runs ADD COLUMN endpoint_url TEXT DEFAULT ''"))
            if "request_type" not in localops_run_cols:
                conn.execute(text("ALTER TABLE localops_runs ADD COLUMN request_type TEXT DEFAULT 'chat'"))
            if "telemetry_json" not in localops_run_cols:
                conn.execute(text("ALTER TABLE localops_runs ADD COLUMN telemetry_json TEXT DEFAULT '{}'"))
        promoted_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('promoted_idea')"))]
        if promoted_cols:
            if "idea_type" not in promoted_cols:
                conn.execute(text("ALTER TABLE promoted_idea ADD COLUMN idea_type TEXT DEFAULT 'app'"))
            if "problem_summary" not in promoted_cols:
                conn.execute(text("ALTER TABLE promoted_idea ADD COLUMN problem_summary TEXT DEFAULT ''"))
            if "target_user" not in promoted_cols:
                conn.execute(text("ALTER TABLE promoted_idea ADD COLUMN target_user TEXT DEFAULT ''"))
            if "why_now" not in promoted_cols:
                conn.execute(text("ALTER TABLE promoted_idea ADD COLUMN why_now TEXT DEFAULT ''"))
            if "first_build_step" not in promoted_cols:
                conn.execute(text("ALTER TABLE promoted_idea ADD COLUMN first_build_step TEXT DEFAULT ''"))
        remoteops_node_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('remoteops_nodes')"))]
        if remoteops_node_cols:
            if "max_concurrent_jobs" not in remoteops_node_cols:
                conn.execute(text("ALTER TABLE remoteops_nodes ADD COLUMN max_concurrent_jobs INTEGER DEFAULT 1"))
            if "capabilities_json" not in remoteops_node_cols:
                conn.execute(text("ALTER TABLE remoteops_nodes ADD COLUMN capabilities_json TEXT DEFAULT '{}'"))
        discord_settings_cols = [row[1] for row in conn.execute(text("PRAGMA table_info('discord_integration_settings')"))]
        if discord_settings_cols:
            if "allowed_approver_ids_json" not in discord_settings_cols:
                conn.execute(text("ALTER TABLE discord_integration_settings ADD COLUMN allowed_approver_ids_json TEXT DEFAULT '[]'"))
            if "policy_deterministic_enabled" not in discord_settings_cols:
                conn.execute(text("ALTER TABLE discord_integration_settings ADD COLUMN policy_deterministic_enabled INTEGER DEFAULT 1"))
            if "llm_reviewer_enabled" not in discord_settings_cols:
                conn.execute(text("ALTER TABLE discord_integration_settings ADD COLUMN llm_reviewer_enabled INTEGER DEFAULT 0"))
            if "llm_reviewer_model" not in discord_settings_cols:
                conn.execute(text("ALTER TABLE discord_integration_settings ADD COLUMN llm_reviewer_model TEXT DEFAULT 'qwen3:14b'"))
            if "isolated_execution_required_for_risky" not in discord_settings_cols:
                conn.execute(text("ALTER TABLE discord_integration_settings ADD COLUMN isolated_execution_required_for_risky INTEGER DEFAULT 1"))
            if "direct_execution_disabled" not in discord_settings_cols:
                conn.execute(text("ALTER TABLE discord_integration_settings ADD COLUMN direct_execution_disabled INTEGER DEFAULT 1"))
            if "raw_shell_disabled" not in discord_settings_cols:
                conn.execute(text("ALTER TABLE discord_integration_settings ADD COLUMN raw_shell_disabled INTEGER DEFAULT 1"))


def get_session():
    with Session(engine) as session:
        yield session
