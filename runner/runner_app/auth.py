from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException, Request

from runner_app.config import RunnerConfig


def verify_signed_request(request: Request, cfg: RunnerConfig, body: bytes) -> None:
    if not cfg.auth_required:
        return

    key_id = request.headers.get("X-Dashburg-KeyId", "")
    ts = request.headers.get("X-Dashburg-Timestamp", "")
    sig = request.headers.get("X-Dashburg-Signature", "")

    if not key_id or not ts or not sig:
        raise HTTPException(status_code=401, detail="Missing signature headers")
    if key_id != cfg.key_id:
        raise HTTPException(status_code=401, detail="Invalid key id")

    try:
        ts_i = int(ts)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid timestamp") from exc

    now = int(time.time())
    if abs(now - ts_i) > cfg.auth_max_skew_seconds:
        raise HTTPException(status_code=401, detail="Stale timestamp")

    body_sha = hashlib.sha256(body).hexdigest()
    msg = f"{request.method.upper()}\n{request.url.path}\n{ts}\n{body_sha}".encode("utf-8")
    digest = hmac.new(cfg.shared_secret.encode("utf-8"), msg, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")

    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
