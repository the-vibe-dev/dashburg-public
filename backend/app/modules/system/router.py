import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/modules/system", tags=["system"])

HOST_MONITOR_BASE_URL = os.getenv("HOST_MONITOR_BASE_URL", "http://127.0.0.1:19444").rstrip("/")
HOST_MONITOR_TOKEN = os.getenv("HOST_MONITOR_TOKEN", "").strip()


class HostRebootRequest(BaseModel):
    reason: str = "manual_dashgithub_request"


def _host_monitor_request(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{HOST_MONITOR_BASE_URL}{path}"
    headers = {"Accept": "application/json"}
    if HOST_MONITOR_TOKEN:
        headers["X-Host-Monitor-Token"] = HOST_MONITOR_TOKEN

    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
        raise HTTPException(status_code=exc.code, detail=detail or str(exc)) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Host monitor unavailable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Invalid host monitor JSON response: {exc}") from exc


@router.get("/status")
def system_status() -> dict:
    return {
        "module": "system",
        "status": "ok",
        "timestamp": datetime.utcnow(),
        "message": "System module online.",
    }


@router.get("/host-monitor/status")
def host_monitor_status() -> dict[str, Any]:
    payload = _host_monitor_request("/status")
    payload.setdefault("proxy_ok", True)
    payload.setdefault("proxy_source", HOST_MONITOR_BASE_URL)
    return payload


@router.post("/host-monitor/reboot")
def host_monitor_reboot(req: HostRebootRequest) -> dict[str, Any]:
    payload = _host_monitor_request("/reboot", method="POST", payload={"reason": req.reason})
    payload.setdefault("proxy_ok", True)
    payload.setdefault("proxy_source", HOST_MONITOR_BASE_URL)
    return payload
