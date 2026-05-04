from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import csv
import queue
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
import socket
from pathlib import Path
from typing import Any

from runner_app.config import RunnerConfig, path_is_allowlisted
from runner_app.storage import JobStore


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobExecutor:
    def __init__(self, cfg: RunnerConfig, store: JobStore):
        self.cfg = cfg
        self.store = store
        self._queue: queue.Queue[tuple[str, str, dict[str, Any]]] = queue.Queue()
        self._cancel_events: dict[str, threading.Event] = {}
        self._cancel_lock = threading.Lock()
        self._workers: list[threading.Thread] = []
        for idx in range(max(1, int(self.cfg.max_concurrent_jobs or 1))):
            worker = threading.Thread(target=self._worker_loop, name=f"dashburg-runner-{idx}", daemon=True)
            worker.start()
            self._workers.append(worker)
        self.node_id = str(getattr(self.cfg, "node_id", "") or socket.gethostname()).strip() or socket.gethostname()
        self.runner_name = f"runner@{self.node_id}"

    def _backup_repo_to_nfs(self, job_id: str, repo_path: Path, cancel_event: threading.Event | None = None) -> dict[str, Any]:
        mount = Path("/mnt/nas_ai/shared")
        if not mount.exists() or not mount.is_dir():
            return {"ok": False, "reason": "nfs_mount_missing", "path": ""}
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_dir = mount / "dashburg_backups" / self.node_id / f"{ts}-{job_id}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        repo_name = repo_path.name or "repo"
        bundle = backup_dir / f"{repo_name}.prechange.bundle"
        status_file = backup_dir / "git-status.txt"
        head_file = backup_dir / "head.txt"
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(repo_path), text=True).strip()
        head_file.write_text(f"{head}\n", encoding="utf-8")
        self._run_cmd_checked(
            job_id,
            ["git", "bundle", "create", str(bundle), "--all"],
            cwd=str(repo_path),
            step="git bundle backup",
            cancel_event=cancel_event,
        )
        status = subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=str(repo_path), text=True)
        status_file.write_text(status, encoding="utf-8")
        return {"ok": True, "reason": "", "path": str(backup_dir), "bundle": str(bundle), "head": head}

    def _mailbox_job_metadata(self, params: dict[str, Any]) -> dict[str, Any]:
        raw = params.get("metadata") if isinstance(params.get("metadata"), dict) else {}
        out: dict[str, Any] = {}
        for key in (
            "mail_source_item_id",
            "mail_thread_id",
            "recipient",
            "recipient_node_id",
            "recipient_kind",
            "recipient_agent_slug",
            "mail_origin",
        ):
            value = raw.get(key)
            if value is None:
                continue
            out[key] = value
        return out

    def _mailbox_emit(
        self,
        *,
        direction: str,
        msg_type: str,
        subject: str,
        body: str,
        job_id: str = "",
        severity: str = "info",
        status: str = "new",
        attachments: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        sender: str | None = None,
        recipient: str | None = None,
    ) -> dict[str, Any]:
        return self.store.create_mailbox_item(
            item_id=uuid.uuid4().hex,
            node_id=self.node_id,
            direction=direction,
            msg_type=msg_type,
            subject=subject,
            body=body,
            job_id=job_id,
            run_id="",
            severity=severity,
            status=status,
            sender=sender or ("dashburg-hub" if direction == "inbox" else self.runner_name),
            recipient=recipient or (self.runner_name if direction == "inbox" else "dashburg-hub"),
            attachments=attachments or [],
            tags=tags or [],
            metadata=metadata or {},
            now_iso=now_iso(),
        )

    def submit(self, job_type: str, params: dict[str, Any]) -> dict[str, Any]:
        if job_type not in {
            "monitor.snapshot",
            "git.update",
            "systemd.restart",
            "docker.compose.up",
            "apt.upgrade",
            "codex.exec",
            "orchestration.codex",
            "webagent.run",
            "webagent.action",
        }:
            raise ValueError("Unsupported job type")

        job_id = uuid.uuid4().hex
        self.store.create_job(job_id, job_type, json.dumps(params), now_iso())
        if job_type == "orchestration.codex":
            title = str(params.get("title") or "Delegated orchestration job").strip() or "Delegated orchestration job"
            repo = str(params.get("repo_path") or "").strip()
            mail_meta = self._mailbox_job_metadata(params)
            self._mailbox_emit(
                direction="outbox",
                msg_type="job_assigned",
                subject=f"Accepted {title}",
                body=f"Runner queued delegated job `{job_id}` for repo `{repo or '-'}`.",
                job_id=job_id,
                tags=["orchestration", "job_assigned"],
                metadata={**mail_meta, "job_type": job_type, "repo_path": repo, "task_type": params.get("task_type", "codex_task")},
            )
        self._queue.put((job_id, job_type, params))
        return {"job_id": job_id, "status": "queued"}

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        row = self.store.request_cancel(job_id, now_iso())
        if row:
            self._mailbox_emit(
                direction="outbox",
                msg_type="job_warning",
                subject=f"Cancel requested for {job_id}",
                body="Dashburg requested cancellation for this runner job.",
                job_id=job_id,
                severity="warning",
                status="acknowledged",
                tags=["cancel", "orchestration"],
                metadata={"job_type": row.get("type", "")},
            )
        with self._cancel_lock:
            event = self._cancel_events.get(job_id)
            if event:
                event.set()
        return row

    def _worker_loop(self) -> None:
        while True:
            job_id, job_type, params = self._queue.get()
            row = self.store.get_job(job_id)
            if not row or str(row.get("status")) == "canceled":
                self._queue.task_done()
                continue
            self._run_job(job_id, job_type, params)
            self._queue.task_done()

    def _emit(self, job_id: str, line: str) -> None:
        self.store.append_log(job_id, line.rstrip("\n"), now_iso())

    def _run_cmd(self, job_id: str, cmd: list[str], cwd: str | None = None, cancel_event: threading.Event | None = None) -> int:
        self._emit(job_id, f"$ {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        while True:
            if cancel_event and cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                self._emit(job_id, "Cancellation requested; terminating process.")
                raise RuntimeError("job canceled")
            line = proc.stdout.readline()
            if line:
                self._emit(job_id, line.rstrip("\n"))
            if not line and proc.poll() is not None:
                break
        return proc.wait()

    def _run_cmd_checked(self, job_id: str, cmd: list[str], cwd: str | None = None, step: str | None = None, cancel_event: threading.Event | None = None) -> int:
        rc = self._run_cmd(job_id, cmd, cwd=cwd, cancel_event=cancel_event)
        if rc != 0:
            label = step or "command"
            raise ValueError(f"{label} failed (rc={rc}): {' '.join(cmd)}")
        return rc

    def _run_job(self, job_id: str, job_type: str, params: dict[str, Any]) -> None:
        cancel_event = threading.Event()
        with self._cancel_lock:
            self._cancel_events[job_id] = cancel_event
        self.store.update_job(job_id, status="preparing", result_json=None, now_iso=now_iso(), started=True)
        if job_type == "orchestration.codex":
            mail_meta = self._mailbox_job_metadata(params)
            self._mailbox_emit(
                direction="outbox",
                msg_type="job_started",
                subject=f"Started delegated job {job_id}",
                body=f"Runner started local Codex execution for `{params.get('repo_path', '')}`.",
                job_id=job_id,
                tags=["orchestration", "job_started"],
                metadata={**mail_meta, "workspace_path": params.get("workspace_path", ""), "mode": params.get("mode", "workspace-write")},
            )
        try:
            result = self._dispatch(job_id, job_type, params, cancel_event)
            status = "canceled" if cancel_event.is_set() else "completed"
            self.store.update_job(job_id, status=status, result_json=json.dumps(result), now_iso=now_iso(), finished=True)
            if job_type == "orchestration.codex":
                mail_meta = self._mailbox_job_metadata(params)
                if cancel_event.is_set():
                    self._mailbox_emit(
                        direction="outbox",
                        msg_type="job_warning",
                        subject=f"Canceled delegated job {job_id}",
                        body="Runner canceled the delegated orchestration job before completion.",
                        job_id=job_id,
                        severity="warning",
                        status="acknowledged",
                        tags=["orchestration", "canceled"],
                        metadata=mail_meta,
                    )
                else:
                    changed_files = result.get("changed_files") if isinstance(result.get("changed_files"), list) else []
                    attachments = [{"path": str(path), "kind": "artifact"} for path in [result.get("manifest_path"), result.get("prompt_path"), result.get("result_path")] if isinstance(path, str) and path]
                    self._mailbox_emit(
                        direction="outbox",
                        msg_type="job_succeeded",
                        subject=f"Completed delegated job {job_id}",
                        body=str(result.get("summary") or "Local Codex execution completed."),
                        job_id=job_id,
                        status="acknowledged",
                        attachments=attachments,
                        tags=["orchestration", "job_succeeded"],
                        metadata={**mail_meta, "changed_files": changed_files, "artifact_dir": result.get("artifact_dir", "")},
                    )
                    if attachments:
                        self._mailbox_emit(
                            direction="outbox",
                            msg_type="artifact_ready",
                            subject=f"Artifacts ready for {job_id}",
                            body="Structured result files were written for this delegated job.",
                            job_id=job_id,
                            status="acknowledged",
                            attachments=attachments,
                            tags=["orchestration", "artifact_ready"],
                            metadata={**mail_meta, "artifact_dir": result.get("artifact_dir", "")},
                        )
        except Exception as exc:
            if "canceled" in str(exc).lower():
                self.store.update_job(job_id, status="canceled", result_json=json.dumps({"error": str(exc)}), now_iso=now_iso(), finished=True)
                if job_type == "orchestration.codex":
                    mail_meta = self._mailbox_job_metadata(params)
                    self._mailbox_emit(
                        direction="outbox",
                        msg_type="job_warning",
                        subject=f"Canceled delegated job {job_id}",
                        body=str(exc),
                        job_id=job_id,
                        severity="warning",
                        status="acknowledged",
                        tags=["orchestration", "canceled"],
                        metadata=mail_meta,
                    )
            else:
                self._emit(job_id, f"ERROR: {exc}")
                self.store.update_job(
                    job_id,
                    status="failed",
                    result_json=json.dumps({"error": str(exc)}),
                    now_iso=now_iso(),
                    finished=True,
                )
                if job_type == "orchestration.codex":
                    mail_meta = self._mailbox_job_metadata(params)
                    self._mailbox_emit(
                        direction="outbox",
                        msg_type="job_failed",
                        subject=f"Failed delegated job {job_id}",
                        body=str(exc),
                        job_id=job_id,
                        severity="error",
                        status="acknowledged",
                        tags=["orchestration", "job_failed"],
                        metadata={**mail_meta, "repo_path": params.get("repo_path", ""), "workspace_path": params.get("workspace_path", "")},
                    )
        finally:
            with self._cancel_lock:
                self._cancel_events.pop(job_id, None)

    def _webagent_api_base(self, params: dict[str, Any]) -> str:
        cfg = params.get("webagent_connection") if isinstance(params.get("webagent_connection"), dict) else {}
        base = str(
            params.get("node_api_base")
            or cfg.get("node_api_base")
            or self.cfg.webagent_node_api_base
            or "http://127.0.0.1:9477"
        ).strip()
        return base.rstrip("/")

    def _webagent_api_token(self, params: dict[str, Any]) -> str:
        cfg = params.get("webagent_connection") if isinstance(params.get("webagent_connection"), dict) else {}
        direct = str(params.get("node_api_token") or cfg.get("node_api_token") or "").strip()
        if direct:
            return direct
        token_env_name = str(
            params.get("node_api_token_env")
            or cfg.get("node_api_token_env")
            or self.cfg.webagent_node_api_token_env
            or "WEBAGENT_NODE_API_TOKEN"
        ).strip()
        if token_env_name:
            env_token = str(os.getenv(token_env_name, "")).strip()
            if env_token:
                return env_token
        return str(self.cfg.webagent_node_api_token or "").strip()

    def _redact_payload(self, value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, row in value.items():
                lower = str(key).lower()
                if any(token in lower for token in ("token", "secret", "password", "api_key", "authorization")):
                    out[str(key)] = "***REDACTED***"
                else:
                    out[str(key)] = self._redact_payload(row)
            return out
        if isinstance(value, list):
            return [self._redact_payload(row) for row in value]
        return value

    def _webagent_request(
        self,
        job_id: str,
        *,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None,
        timeout_seconds: int,
    ) -> tuple[int, Any]:
        data = None
        headers: dict[str, str] = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-API-Key"] = token
            headers["X-Auth-Token"] = token

        req = urllib.request.Request(url=url, method=method.upper(), data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=max(5, timeout_seconds)) as resp:
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace")
                try:
                    decoded = json.loads(text) if text else {}
                except Exception:
                    decoded = {"raw": text}
                return int(resp.status), decoded
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw) if raw else {}
            except Exception:
                detail = {"raw": raw}
            self._emit(job_id, f"webagent node HTTP {exc.code}: {url}")
            return int(exc.code), detail
        except urllib.error.URLError as exc:
            raise ValueError(f"webagent node unavailable: {exc}") from exc

    def _webagent_action_calls(self, action: str, session_id: str) -> list[tuple[str, str]]:
        sid = session_id.strip()
        action = action.strip().lower()
        if action == "start_session":
            return [
                ("POST", "/sessions"),
                ("POST", "/browser/sessions"),
                ("POST", "/agent/sessions"),
                ("POST", "/v1/sessions"),
                ("POST", "/actions"),
            ]
        if action == "stop_session":
            return [
                ("DELETE", f"/sessions/{sid}"),
                ("POST", f"/sessions/{sid}/close"),
                ("POST", f"/sessions/{sid}/stop"),
                ("POST", "/actions"),
            ]
        if action == "session_status":
            return [
                ("GET", f"/sessions/{sid}"),
                ("GET", f"/sessions/{sid}/status"),
                ("POST", "/actions"),
            ]
        return [
            ("POST", f"/sessions/{sid}/actions"),
            ("POST", f"/sessions/{sid}/{action}"),
            ("POST", "/actions"),
        ]

    def _create_runner_test_asset(self, job_id: str, params: dict[str, Any]) -> dict[str, Any]:
        asset_kind = str(params.get("kind") or "text").strip().lower()
        asset_name = str(params.get("name") or f"{asset_kind}-asset").strip() or f"{asset_kind}-asset"
        target_size = int(params.get("target_size_bytes") or 0)
        rows = int(params.get("rows") or 10)
        output_dir = Path(str(params.get("output_dir") or Path(self.cfg.data_dir) / "webagent" / "assets")).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        ext_map = {"text": ".txt", "csv": ".csv", "json": ".json", "pdf": ".pdf", "binary": ".bin", "image": ".png", "video": ".mp4"}
        suffix = ext_map.get(asset_kind, ".dat")
        filename = asset_name if asset_name.endswith(suffix) else f"{asset_name}{suffix}"
        path = output_dir / filename

        if asset_kind == "text":
            path.write_text(str(params.get("content") or "Dashburg WebAgent text fixture\n"), encoding="utf-8")
        elif asset_kind == "csv":
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["id", "name", "email"])
                for i in range(rows):
                    writer.writerow([i + 1, f"User {i+1}", f"user{i+1}@example.test"])
        elif asset_kind == "json":
            payload = {"fixture": True, "job_id": job_id, "records": [{"id": i + 1, "value": f"row-{i+1}"} for i in range(rows)]}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        elif asset_kind == "pdf":
            pdf = b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
            path.write_bytes(pdf)
        elif asset_kind == "binary":
            path.write_bytes(os.urandom(1024))
        elif asset_kind == "image":
            path.write_bytes(
                bytes.fromhex(
                    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000A49444154789C6360000002000154A24F5D0000000049454E44AE426082"
                )
            )
        elif asset_kind == "video":
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg and str(params.get("use_ffmpeg", "true")).lower() in {"1", "true", "yes", "on"}:
                duration = int(params.get("duration_seconds") or 2)
                width = int(params.get("width") or 320)
                height = int(params.get("height") or 240)
                cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c=blue:s={width}x{height}:d={duration}", "-pix_fmt", "yuv420p", str(path)]
                self._run_cmd_checked(job_id, cmd, step="ffmpeg fake video generation")
            else:
                path.write_bytes(b"DASHBURG_FAKE_VIDEO_PLACEHOLDER")
        else:
            path.write_text(str(params.get("content") or "generic fixture\n"), encoding="utf-8")

        if target_size > 0:
            current = path.stat().st_size
            if current < target_size:
                with path.open("ab") as fh:
                    fh.write(b"0" * (target_size - current))
        return {"ok": True, "kind": asset_kind, "path": str(path), "size_bytes": path.stat().st_size, "ffmpeg_available": shutil.which("ffmpeg") is not None}

    def _run_webagent_action(self, job_id: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.cfg.webagent_enabled:
            raise ValueError("webagent.action is disabled")

        action = str(params.get("action") or "").strip().lower()
        if not action:
            raise ValueError("action is required")

        session_id = str(params.get("session_id") or "").strip()
        timeout_seconds = int(params.get("timeout_seconds") or self.cfg.webagent_action_timeout_seconds or 45)
        api_base = self._webagent_api_base(params)
        api_token = self._webagent_api_token(params)

        aliases = {
            "navigate": "goto",
            "upload": "set_input_files",
            "select": "select_option",
            "wait_for": "wait_for_selector",
            "refresh": "reload",
            "new_tab": "new_page",
            "switch_tab": "switch_page",
            "close_tab": "close_page",
            "right_click": "click",
        }
        action = aliases.get(action, action)

        allowed_actions = {
            "start_session",
            "stop_session",
            "session_status",
            "goto",
            "go_back",
            "go_forward",
            "reload",
            "wait_for_load_state",
            "click",
            "dblclick",
            "fill",
            "type",
            "keyboard_type",
            "select_option",
            "check",
            "uncheck",
            "set_input_files",
            "press",
            "hover",
            "focus",
            "blur",
            "drag_and_drop",
            "scroll",
            "wait_for_selector",
            "wait_for_timeout",
            "screenshot",
            "evaluate",
            "extract",
            "capture_html",
            "capture_text",
            "network_log",
            "console_log",
            "js_errors",
            "performance_timing",
            "dom_summary",
            "accessibility_snapshot",
            "scan_page",
            "inventory_actions",
            "inventory_forms",
            "inventory_uploads",
            "discover_navigation",
            "discover_modals",
            "discover_iframes",
            "summarize_page",
            "summarize_run",
            "analyze_form",
            "analyze_upload_flow",
            "analyze_failures",
            "fill_form",
            "fill_all_forms",
            "deep_explore_page",
            "deep_explore_site",
            "assert_text_present",
            "assert_selector_present",
            "assert_upload_success",
            "assert_navigation_happened",
            "assert_console_clean",
            "assert_no_js_errors",
            "assert_file_preview_visible",
            "export_run_json",
            "export_run_markdown",
            "export_artifacts_bundle",
            "generate_test_asset",
            "upload_test_asset",
            "upload_matrix_test",
            "pdf",
            "new_page",
            "switch_page",
            "close_page",
        }
        if action not in allowed_actions:
            raise ValueError(f"unsupported webagent.action: {action}")
        session_optional_actions = {
            "start_session",
            "session_status",
            "generate_test_asset",
            "scan_page",
            "summarize_run",
            "export_run_json",
            "export_run_markdown",
        }
        if action not in session_optional_actions and not session_id:
            raise ValueError("session_id is required for this action")
        if action == "generate_test_asset":
            result = self._create_runner_test_asset(job_id, params)
            return {
                "ok": True,
                "action": action,
                "session_id": session_id,
                "node_api_base": api_base,
                "request_path": "runner-local",
                "status_code": 200,
                "result": result,
            }

        payload: dict[str, Any] = {
            "action": action,
            "session_id": session_id,
            "target_url": str(params.get("target_url") or "").strip(),
            "url": str(params.get("url") or "").strip(),
            "selector": str(params.get("selector") or "").strip(),
            "value": params.get("value"),
            "text": params.get("text"),
            "files": params.get("files"),
            "key": params.get("key"),
            "button": params.get("button"),
            "count": params.get("count"),
            "index": params.get("index"),
            "label": params.get("label"),
            "x": params.get("x"),
            "y": params.get("y"),
            "delta_x": params.get("delta_x"),
            "delta_y": params.get("delta_y"),
            "state": params.get("state"),
            "timeout_ms": params.get("timeout_ms"),
            "wait_for": params.get("wait_for"),
            "script": params.get("script"),
            "expression": params.get("expression"),
            "screenshot_name": params.get("screenshot_name"),
            "options": params.get("options") if isinstance(params.get("options"), dict) else {},
            "metadata": params.get("metadata") if isinstance(params.get("metadata"), dict) else {},
            "safety": params.get("safety") if isinstance(params.get("safety"), dict) else {},
            "selector_strategy": params.get("selector_strategy"),
            "strict_targeting": params.get("strict_targeting"),
            "targeting": params.get("targeting") if isinstance(params.get("targeting"), dict) else {},
            "assertions": params.get("assertions") if isinstance(params.get("assertions"), list) else [],
            "run_mode": params.get("run_mode"),
            "retries": params.get("retries"),
            "retry_backoff_ms": params.get("retry_backoff_ms"),
        }
        payload = {k: v for k, v in payload.items() if v is not None and v != ""}

        calls = self._webagent_action_calls(action, session_id)
        last_status = 0
        last_detail: Any = None
        for method, path in calls:
            url = f"{api_base}{path}"
            # Some endpoints are resource-oriented and do not expect an action envelope.
            sent_payload = payload if method.upper() != "GET" else None
            if path.endswith(f"/{action}") and isinstance(sent_payload, dict):
                sent_payload = {k: v for k, v in sent_payload.items() if k not in {"action", "session_id"}}
            status, detail = self._webagent_request(
                job_id,
                method=method,
                url=url,
                token=api_token,
                payload=sent_payload,
                timeout_seconds=timeout_seconds,
            )
            last_status = status
            last_detail = detail
            if status < 400:
                if not isinstance(detail, dict):
                    detail = {"result": detail}
                return {
                    "ok": True,
                    "action": action,
                    "session_id": str(detail.get("session_id") or detail.get("id") or session_id),
                    "node_api_base": api_base,
                    "request_path": path,
                    "status_code": status,
                    "result": detail,
                }
            if status not in {404, 405}:
                break

        raise ValueError(f"webagent action failed (status={last_status}): {last_detail}")

    def _dispatch(self, job_id: str, job_type: str, params: dict[str, Any], cancel_event: threading.Event | None = None) -> dict[str, Any]:
        if job_type == "monitor.snapshot":
            return {"ok": True, "message": "snapshot captured"}

        if job_type == "git.update":
            repo = str(params.get("repo_path", ""))
            branch = str(params.get("branch", "")).strip()
            if not path_is_allowlisted(repo, self.cfg.allowed_repos):
                raise ValueError("repo_path not allowlisted")
            if branch:
                self._run_cmd(job_id, ["git", "-C", repo, "checkout", branch])
            rc = self._run_cmd(job_id, ["git", "-C", repo, "pull", "--ff-only"])
            return {"ok": rc == 0, "rc": rc}

        if job_type == "systemd.restart":
            service = str(params.get("service_name", ""))
            if service not in self.cfg.allowed_services:
                raise ValueError("service_name not allowlisted")
            rc = self._run_cmd(job_id, ["sudo", "systemctl", "restart", service])
            return {"ok": rc == 0, "service": service, "rc": rc}

        if job_type == "docker.compose.up":
            project_dir = str(params.get("project_dir", ""))
            if not path_is_allowlisted(project_dir, self.cfg.allowed_compose_dirs):
                raise ValueError("project_dir not allowlisted")
            rc1 = self._run_cmd(job_id, ["docker", "compose", "pull"], cwd=project_dir, cancel_event=cancel_event)
            rc2 = self._run_cmd(job_id, ["docker", "compose", "up", "-d"], cwd=project_dir, cancel_event=cancel_event)
            return {"ok": rc1 == 0 and rc2 == 0, "pull_rc": rc1, "up_rc": rc2}

        if job_type == "apt.upgrade":
            if not self.cfg.apt_upgrade_enabled:
                raise ValueError("apt.upgrade is disabled")
            rc1 = self._run_cmd(job_id, ["sudo", "apt-get", "update"], cancel_event=cancel_event)
            rc2 = self._run_cmd(job_id, ["sudo", "apt-get", "-y", "upgrade"], cancel_event=cancel_event)
            return {"ok": rc1 == 0 and rc2 == 0, "update_rc": rc1, "upgrade_rc": rc2}

        if job_type == "codex.exec":
            if not self.cfg.codex_enabled:
                raise ValueError("codex.exec is disabled")
            if shutil.which("codex") is None:
                raise ValueError("codex is not installed on runner")

            repo = str(params.get("repo_path", ""))
            prompt = str(params.get("prompt", "")).strip()
            mode = str(params.get("mode") or "workspace-write").strip().lower()
            if mode not in {"read-only", "workspace-write", "danger-full-access"}:
                raise ValueError("mode must be one of: read-only, workspace-write, danger-full-access")
            if not prompt:
                raise ValueError("prompt is required")
            if not path_is_allowlisted(repo, self.cfg.allowed_repos):
                raise ValueError("repo_path not allowlisted")
            repo_path = Path(repo)
            if not repo_path.exists():
                raise ValueError(f"repo_path does not exist: {repo}")
            if not repo_path.is_dir():
                raise ValueError(f"repo_path is not a directory: {repo}")
            rc_git = self._run_cmd(job_id, ["git", "-C", repo, "rev-parse", "--is-inside-work-tree"], cancel_event=cancel_event)
            if rc_git != 0:
                raise ValueError(f"repo_path is not a git repository: {repo}")

            rc = self._run_cmd_checked(
                job_id,
                ["codex", "exec", "-s", mode, prompt],
                cwd=str(repo_path),
                step="codex exec",
                cancel_event=cancel_event,
            )

            self._run_cmd(job_id, ["git", "status", "--porcelain"], cwd=str(repo_path), cancel_event=cancel_event)
            self._run_cmd(job_id, ["git", "diff", "--stat"], cwd=str(repo_path), cancel_event=cancel_event)

            changed_files = subprocess.check_output(["git", "status", "--porcelain"], cwd=str(repo_path), text=True)
            diffstat = subprocess.check_output(["git", "diff", "--stat"], cwd=str(repo_path), text=True)

            return {
                "ok": rc == 0,
                "rc": rc,
                "repo_path": repo,
                "mode": mode,
                "sandbox": mode,
                "diffstat": diffstat,
                "changed_files": [ln.strip() for ln in changed_files.splitlines() if ln.strip()],
                "next_steps": "Review changes and commit or discard.",
            }

        if job_type == "orchestration.codex":
            if not self.cfg.codex_enabled:
                raise ValueError("orchestration.codex is disabled")
            if shutil.which("codex") is None:
                raise ValueError("codex is not installed on runner")
            repo = str(params.get("repo_path", "")).strip()
            workspace_path = str(params.get("workspace_path", "")).strip()
            prompt = str(params.get("prompt", "")).strip()
            instructions = str(params.get("instructions", "")).strip()
            mode = str(params.get("mode") or "workspace-write").strip().lower()
            if not prompt:
                raise ValueError("prompt is required")
            if not path_is_allowlisted(repo, self.cfg.allowed_repos):
                raise ValueError("repo_path not allowlisted")
            repo_path = Path(repo).expanduser().resolve()
            if not repo_path.exists() or not repo_path.is_dir():
                raise ValueError(f"repo_path is invalid: {repo}")
            if workspace_path:
                ws = Path(workspace_path).expanduser().resolve()
            else:
                ws = repo_path
            if not path_is_allowlisted(str(ws), [str(repo_path), *self.cfg.allowed_repos, self.cfg.workspace_root]):
                raise ValueError("workspace_path not allowlisted")
            ws.mkdir(parents=True, exist_ok=True)
            artifacts_dir = Path(self.cfg.data_dir).expanduser().resolve() / "orchestration" / "jobs" / job_id
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            manifest = {
                "job_id": job_id,
                "title": str(params.get("title") or ""),
                "task_type": str(params.get("task_type") or "codex_task"),
                "repo_path": str(repo_path),
                "workspace_path": str(ws),
                "mode": mode,
                "prompt": prompt,
                "instructions": instructions,
                "metadata": params.get("metadata", {}),
                "created_at": now_iso(),
            }
            manifest_path = artifacts_dir / "task_manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            full_prompt = prompt if not instructions else f"{instructions}\n\nTask:\n{prompt}"
            prompt_path = artifacts_dir / "prompt.txt"
            prompt_path.write_text(full_prompt, encoding="utf-8")
            backup_info: dict[str, Any] = {"ok": False, "reason": "skipped", "path": ""}
            if mode in {"workspace-write", "danger-full-access"}:
                try:
                    self._emit(job_id, "Preparing pre-change backup on NFS before Codex execution.")
                    backup_info = self._backup_repo_to_nfs(job_id, repo_path, cancel_event=cancel_event)
                    if backup_info.get("ok"):
                        self._emit(job_id, f"Backup created at {backup_info.get('path')}")
                    else:
                        self._emit(job_id, f"Backup skipped: {backup_info.get('reason')}")
                except Exception as exc:
                    backup_info = {"ok": False, "reason": f"backup_failed:{exc}", "path": ""}
                    self._emit(job_id, f"Backup failed: {exc}")
            self.store.update_job(job_id, status="running", result_json=None, now_iso=now_iso(), started=True)
            rc = self._run_cmd_checked(
                job_id,
                ["codex", "exec", "-s", mode, full_prompt],
                cwd=str(ws),
                step="orchestration codex exec",
                cancel_event=cancel_event,
            )
            status_out = subprocess.check_output(["git", "status", "--porcelain"], cwd=str(repo_path), text=True)
            diffstat_out = subprocess.check_output(["git", "diff", "--stat"], cwd=str(repo_path), text=True)
            result = {
                "ok": rc == 0,
                "summary": diffstat_out.strip() or "Codex completed without git diffstat output.",
                "changed_files": [line.strip() for line in status_out.splitlines() if line.strip()],
                "artifact_dir": str(artifacts_dir),
                "prompt_path": str(prompt_path),
                "manifest_path": str(manifest_path),
                "result_path": str(artifacts_dir / "result.json"),
                "workspace_path": str(ws),
                "repo_path": str(repo_path),
                "mode": mode,
                "backup": backup_info,
            }
            (artifacts_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            return result

        if job_type == "webagent.run":
            if not self.cfg.webagent_enabled:
                raise ValueError("webagent.run is disabled")
            command = str(params.get("runner_command") or self.cfg.webagent_command or "").strip()
            if not command:
                raise ValueError("webagent_command is not configured on runner")
            target_url = str(params.get("target_url", "")).strip()
            run_type = str(params.get("run_type", "")).strip()
            if not target_url:
                raise ValueError("target_url is required")
            if not run_type:
                raise ValueError("run_type is required")
            api_base = self._webagent_api_base(params)
            api_token = self._webagent_api_token(params)
            node_artifacts_dir = str(params.get("node_artifacts_dir") or self.cfg.webagent_node_artifacts_dir or "").strip()
            timeout_seconds = int(params.get("timeout_seconds") or self.cfg.webagent_timeout_seconds or 900)
            poll_interval_seconds = float(params.get("poll_interval_seconds") or self.cfg.webagent_poll_interval_seconds or 2.0)

            artifacts_dir = Path(self.cfg.data_dir).expanduser().resolve() / "webagent" / "runs" / job_id
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            request_path = artifacts_dir / "request.json"
            result_path = artifacts_dir / "result.json"
            request_payload = {
                "job_id": job_id,
                "target_url": target_url,
                "run_type": run_type,
                "options": params.get("options", {}),
                "notes": params.get("notes", ""),
                "params": self._redact_payload(params),
            }
            request_path.write_text(json.dumps(request_payload, indent=2), encoding="utf-8")

            env = os.environ.copy()
            env["WEBAGENT_JOB_ID"] = job_id
            env["WEBAGENT_TARGET_URL"] = target_url
            env["WEBAGENT_RUN_TYPE"] = run_type
            env["WEBAGENT_REQUEST_JSON"] = str(request_path)
            env["WEBAGENT_RESULT_JSON"] = str(result_path)
            env["WEBAGENT_ARTIFACT_DIR"] = str(artifacts_dir)
            env["WEBAGENT_NODE_API_BASE"] = api_base
            env["WEBAGENT_NODE_API_TOKEN"] = api_token
            env["WEBAGENT_NODE_ARTIFACTS_DIR"] = node_artifacts_dir
            env["WEBAGENT_TIMEOUT_SECONDS"] = str(timeout_seconds)
            env["WEBAGENT_POLL_INTERVAL_SECONDS"] = str(poll_interval_seconds)

            cmd = ["bash", "-lc", command]
            self._emit(job_id, f"$ {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                self._emit(job_id, line.rstrip("\n"))
            rc = proc.wait()
            if rc != 0:
                raise ValueError(f"webagent command failed (rc={rc})")

            result: dict[str, Any] = {}
            if result_path.exists():
                try:
                    loaded = json.loads(result_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        result = loaded
                except Exception:
                    result = {}
            if not result:
                result = {
                    "summary": f"WebAgent run `{run_type}` completed for {target_url}.",
                    "artifact_manifest": [],
                }
            result.setdefault("artifact_dir", str(artifacts_dir))
            result.setdefault("request_json", str(request_path))
            result.setdefault("result_json", str(result_path))
            return result

        if job_type == "webagent.action":
            return self._run_webagent_action(job_id, params)

        raise ValueError("Unsupported job type")
