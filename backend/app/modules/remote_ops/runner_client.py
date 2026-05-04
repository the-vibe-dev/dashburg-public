from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class RunnerClientError(Exception):
    def __init__(self, status: int, detail: Any):
        super().__init__(f"Runner error {status}")
        self.status = status
        self.detail = detail


class RunnerClient:
    def __init__(self, base_url: str, key_id: str, secret: str, timeout: float = 8.0):
        self.base_url = base_url.rstrip("/")
        self.key_id = key_id
        self.secret = secret.encode("utf-8")
        self.timeout = timeout

    def _make_signature(self, method: str, path: str, timestamp: str, body: bytes) -> str:
        body_sha = hashlib.sha256(body).hexdigest()
        msg = f"{method}\n{path}\n{timestamp}\n{body_sha}".encode("utf-8")
        digest = hmac.new(self.secret, msg, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> Any:
        q = ""
        if params:
            q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        full_path = path if not q else f"{path}?{q}"
        data = json.dumps(body).encode("utf-8") if body is not None else b""
        ts = str(int(time.time()))
        sig = self._make_signature(method.upper(), path, ts, data)
        req = urllib.request.Request(
            url=f"{self.base_url}{full_path}",
            data=data if method.upper() in {"POST", "PUT", "PATCH"} else None,
            method=method.upper(),
        )
        req.add_header("X-Dashburg-KeyId", self.key_id)
        req.add_header("X-Dashburg-Timestamp", ts)
        req.add_header("X-Dashburg-Signature", sig)
        req.add_header("Accept", "application/json")
        if data:
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            detail: Any
            try:
                detail = json.loads(raw)
            except Exception:
                detail = {"raw": raw}
            raise RunnerClientError(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise RunnerClientError(502, {"message": str(exc)}) from exc

    def health(self) -> Any:
        return self._request("GET", "/v1/health")

    def metrics(self) -> Any:
        return self._request("GET", "/v1/metrics")

    def services(self) -> Any:
        return self._request("GET", "/v1/services")

    def capabilities(self) -> Any:
        return self._request("GET", "/v1/capabilities")

    def create_job(self, job_type: str, params: dict[str, Any]) -> Any:
        return self._request("POST", "/v1/jobs", body={"type": job_type, "params": params})

    def get_job(self, runner_job_id: str) -> Any:
        return self._request("GET", f"/v1/jobs/{runner_job_id}")

    def cancel_job(self, runner_job_id: str) -> Any:
        return self._request("POST", f"/v1/jobs/{runner_job_id}/cancel", body={})

    def get_logs(self, runner_job_id: str, offset: int, max_lines: int = 200) -> Any:
        return self._request("GET", f"/v1/jobs/{runner_job_id}/logs", params={"offset": offset, "max_lines": max_lines})

    def get_artifacts(self, runner_job_id: str) -> Any:
        return self._request("GET", f"/v1/jobs/{runner_job_id}/artifacts")

    def get_artifact_content(self, runner_job_id: str, artifact_path: str) -> bytes:
        query = urllib.parse.urlencode({"path": artifact_path})
        base_path = f"/v1/jobs/{runner_job_id}/artifacts/content"
        path = f"{base_path}?{query}"
        ts = str(int(time.time()))
        sig = self._make_signature("GET", base_path, ts, b"")
        req = urllib.request.Request(url=f"{self.base_url}{path}", method="GET")
        req.add_header("X-Dashburg-KeyId", self.key_id)
        req.add_header("X-Dashburg-Timestamp", ts)
        req.add_header("X-Dashburg-Signature", sig)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
            except Exception:
                detail = {"raw": raw}
            raise RunnerClientError(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise RunnerClientError(502, {"message": str(exc)}) from exc

    def host_monitor_status(self) -> Any:
        return self._request("GET", "/v1/host-monitor/status")

    def host_monitor_ollama_ps(self, base_url: str | None = None) -> Any:
        return self._request("GET", "/v1/host-monitor/ollama/ps", params={"base_url": base_url})

    def host_monitor_comfyui_queue(self, base_url: str | None = None) -> Any:
        return self._request("GET", "/v1/host-monitor/comfyui/queue", params={"base_url": base_url})

    def host_monitor_wrapper_health(self, base_url: str | None = None) -> Any:
        return self._request("GET", "/v1/host-monitor/wrapper/health", params={"base_url": base_url})

    def host_monitor_reboot(self, reason: str = "dashburg_remote_ops") -> Any:
        return self._request("POST", "/v1/host-monitor/reboot", body={"reason": reason})

    def mailbox_inbox(self, *, limit: int = 100, include_archived: bool = False, job_id: str | None = None) -> Any:
        return self._request("GET", "/v1/mailbox/inbox", params={"limit": limit, "include_archived": int(include_archived), "job_id": job_id})

    def mailbox_outbox(self, *, limit: int = 100, include_archived: bool = False, job_id: str | None = None) -> Any:
        return self._request("GET", "/v1/mailbox/outbox", params={"limit": limit, "include_archived": int(include_archived), "job_id": job_id})

    def mailbox_archive(self, *, limit: int = 100, job_id: str | None = None) -> Any:
        return self._request("GET", "/v1/mailbox/archive", params={"limit": limit, "job_id": job_id})

    def get_mailbox_item(self, item_id: str) -> Any:
        return self._request("GET", f"/v1/mailbox/{item_id}")

    def create_mailbox_note(self, payload: dict[str, Any]) -> Any:
        return self._request("POST", "/v1/mailbox/inbox", body=payload)

    def acknowledge_mailbox_item(self, item_id: str) -> Any:
        return self._request("POST", f"/v1/mailbox/{item_id}/ack", body={})

    def archive_mailbox_item(self, item_id: str) -> Any:
        return self._request("POST", f"/v1/mailbox/{item_id}/archive", body={})

    def get_schedules(self) -> Any:
        return self._request("GET", "/v1/schedules")

    def put_schedules(self, payload: dict[str, Any]) -> Any:
        return self._request("PUT", "/v1/schedules", body=payload)

    def apply_schedules(self) -> Any:
        return self._request("POST", "/v1/schedules/apply", body={})

    def get_schedules_status(self) -> Any:
        return self._request("GET", "/v1/schedules/status")
