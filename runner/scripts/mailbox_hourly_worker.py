#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

RECIPIENT_RE = re.compile(r"^node:(?P<node_id>[a-zA-Z0-9._-]+)/(?P<target>runner|agent:[a-zA-Z0-9._-]+)$")


def _load_cfg(path: str) -> dict[str, Any]:
    cfg_path = Path(path).expanduser().resolve()
    payload = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("invalid config")
    return payload


def _node_aliases(cfg: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    env_aliases = str(os.getenv("MAILBOX_WORKER_NODE_IDS", "")).strip()
    if env_aliases:
        aliases.update({row.strip() for row in env_aliases.split(",") if row.strip()})
    cfg_node = str(cfg.get("node_id") or "").strip()
    if cfg_node:
        aliases.add(cfg_node)
    aliases.add(socket.gethostname())
    aliases.add(socket.gethostname().split(".")[0])
    return {row.lower() for row in aliases if row}


def _parse_recipient(value: str) -> dict[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return {"node_id": "", "kind": "", "agent_slug": ""}
    match = RECIPIENT_RE.match(raw)
    if not match:
        return {"node_id": "", "kind": "", "agent_slug": ""}
    node_id = str(match.group("node_id") or "").strip().lower()
    target = str(match.group("target") or "").strip().lower()
    if target == "runner":
        return {"node_id": node_id, "kind": "runner", "agent_slug": ""}
    return {
        "node_id": node_id,
        "kind": "agent",
        "agent_slug": target.split(":", 1)[1] if ":" in target else "",
    }


def _load_memory() -> tuple[str, str]:
    nfs = Path("/mnt/nas_ai/shared/MEM.md")
    if nfs.exists() and nfs.is_file():
        try:
            return ("nfs", nfs.read_text(encoding="utf-8", errors="replace")[:14000])
        except OSError:
            pass
    home_mem = Path.home() / "MEM.md"
    if home_mem.exists() and home_mem.is_file():
        try:
            return ("home", home_mem.read_text(encoding="utf-8", errors="replace")[:14000])
        except OSError:
            pass
    return ("none", "")


class LocalRunnerClient:
    def __init__(self, cfg: dict[str, Any]) -> None:
        host = str(cfg.get("host") or "127.0.0.1").strip()
        if host in {"0.0.0.0", "::"}:
            host = "127.0.0.1"
        port = int(cfg.get("port") or 8844)
        self.base_url = f"http://{host}:{port}"
        self.key_id = str(cfg.get("key_id") or "").strip()
        self.secret = str(cfg.get("shared_secret") or "").encode("utf-8")

    def _signature(self, method: str, path: str, ts: str, body: bytes) -> str:
        body_sha = hashlib.sha256(body).hexdigest()
        msg = f"{method}\n{path}\n{ts}\n{body_sha}".encode("utf-8")
        return base64.b64encode(hmac.new(self.secret, msg, hashlib.sha256).digest()).decode("ascii")

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> Any:
        query = ""
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        full_path = path if not query else f"{path}?{query}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        ts = str(int(time.time()))
        sig = self._signature(method.upper(), path, ts, body)
        req = urllib.request.Request(
            url=f"{self.base_url}{full_path}",
            data=body if method.upper() in {"POST", "PUT", "PATCH"} else None,
            method=method.upper(),
        )
        req.add_header("X-Dashburg-KeyId", self.key_id)
        req.add_header("X-Dashburg-Timestamp", ts)
        req.add_header("X-Dashburg-Signature", sig)
        req.add_header("Accept", "application/json")
        if body:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}

    def inbox(self, limit: int = 200) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v1/mailbox/inbox", params={"limit": limit, "include_archived": 0})
        rows = payload.get("items") if isinstance(payload, dict) else []
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def ack(self, item_id: str) -> None:
        self._request("POST", f"/v1/mailbox/{item_id}/ack", payload={})

    def create_job(self, job_type: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = self._request("POST", "/v1/jobs", payload={"type": job_type, "params": params})
        return payload if isinstance(payload, dict) else {}


def _recipient_allowed(
    recipient: dict[str, str],
    *,
    recipients_exact: set[str] | None = None,
    recipient_kind: str = "any",
) -> bool:
    node_id = str(recipient.get("node_id") or "").strip().lower()
    kind = str(recipient.get("kind") or "").strip().lower()
    agent_slug = str(recipient.get("agent_slug") or "").strip().lower()
    if not node_id or not kind:
        return False
    if recipient_kind in {"runner", "agent"} and kind != recipient_kind:
        return False
    if recipients_exact:
        rendered = f"node:{node_id}/runner" if kind == "runner" else f"node:{node_id}/agent:{agent_slug}"
        if rendered not in recipients_exact:
            return False
    return True


def _matches_recipient(
    item: dict[str, Any],
    node_aliases: set[str],
    *,
    recipients_exact: set[str] | None = None,
    recipient_kind: str = "any",
) -> tuple[bool, dict[str, str]]:
    if bool(item.get("archived")) or bool(item.get("acknowledged")):
        return (False, {})
    status = str(item.get("status") or "").strip().lower()
    if status in {"acknowledged", "archived"}:
        return (False, {})
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    if str(meta.get("mail_dispatch_status") or "").lower() == "dispatched":
        return (False, {})
    parsed = _parse_recipient(str(item.get("to") or meta.get("recipient") or ""))
    node_id = str(parsed.get("node_id") or "").strip().lower()
    if not node_id:
        return (False, {})
    if node_id not in node_aliases:
        return (False, {})
    if not _recipient_allowed(parsed, recipients_exact=recipients_exact, recipient_kind=recipient_kind):
        return (False, {})
    return (True, parsed)


def _pick_repo(cfg: dict[str, Any], item: dict[str, Any]) -> str:
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    repo = str(meta.get("repo_path") or "").strip()
    if repo:
        return repo
    allow = cfg.get("allowed_repos") if isinstance(cfg.get("allowed_repos"), list) else []
    allow = [str(row).strip() for row in allow if str(row).strip()]
    return allow[0] if allow else ""


def _pick_workspace(repo: str, item: dict[str, Any]) -> str:
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    ws = str(meta.get("workspace_path") or "").strip()
    return ws or repo


def _build_prompt(item: dict[str, Any], recipient: dict[str, str], memory_source: str, memory_text: str) -> tuple[str, str]:
    subject = str(item.get("subject") or "").strip()
    body = str(item.get("body") or "").strip()
    msg_id = str(item.get("id") or "")
    recipient_desc = "runner"
    if recipient.get("kind") == "agent" and recipient.get("agent_slug"):
        recipient_desc = f"agent `{recipient.get('agent_slug')}`"
    instructions = (
        "Process this inbox message for the addressed recipient, complete requested repo work, and send a concise structured response. "
        "Before finalizing, write findings and next steps in markdown style suitable for mailbox output."
    )
    memory_block = ""
    if memory_text:
        memory_block = f"[CLUSTER MEMORY source={memory_source}]\n{memory_text}\n[/CLUSTER MEMORY]\n\n"
    prompt = (
        f"{memory_block}"
        f"Message ID: {msg_id}\n"
        f"Recipient: {recipient_desc}\n"
        f"Subject: {subject}\n\n"
        f"Message body:\n{body}\n\n"
        "Required output:\n"
        "1) work summary\n"
        "2) changed files\n"
        "3) follow-up questions or blockers\n"
        "4) next actions\n"
    )
    return (instructions, prompt)


def run_once(
    config_path: str,
    dry_run: bool = False,
    limit: int = 200,
    recipients_exact: set[str] | None = None,
    recipient_kind: str = "any",
) -> int:
    cfg = _load_cfg(config_path)
    client = LocalRunnerClient(cfg)
    aliases = _node_aliases(cfg)
    memory_source, memory_text = _load_memory()
    processed = 0
    rows = client.inbox(limit=limit)
    for item in rows:
        matched, recipient = _matches_recipient(
            item,
            aliases,
            recipients_exact=recipients_exact,
            recipient_kind=recipient_kind,
        )
        if not matched:
            continue
        repo = _pick_repo(cfg, item)
        if not repo:
            continue
        workspace = _pick_workspace(repo, item)
        instructions, prompt = _build_prompt(item, recipient, memory_source, memory_text)
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        params = {
            "title": str(item.get("subject") or "Mailbox task").strip() or "Mailbox task",
            "task_type": "mailbox_dispatch",
            "repo_path": repo,
            "workspace_path": workspace,
            "instructions": instructions,
            "prompt": prompt,
            "mode": str(meta.get("codex_mode") or "workspace-write"),
            "metadata": {
                "mail_source_item_id": str(item.get("id") or ""),
                "mail_origin": "mailbox_hourly_worker",
                "recipient": str(item.get("to") or ""),
                "recipient_node_id": str(recipient.get("node_id") or ""),
                "recipient_kind": str(recipient.get("kind") or ""),
                "recipient_agent_slug": str(recipient.get("agent_slug") or ""),
                "memory_source": memory_source,
            },
        }
        if not dry_run:
            client.create_job("orchestration.codex", params)
            client.ack(str(item.get("id") or ""))
        processed += 1
    return processed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Dashburg runner hourly mailbox worker")
    parser.add_argument("--config", default="/etc/dashburg-runner/config.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--recipient", action="append", default=[], help="Exact recipient route (repeatable), e.g. node:aitts/agent:buildbot")
    parser.add_argument("--recipient-kind", choices=["any", "runner", "agent"], default="any")
    args = parser.parse_args(argv)
    recipients_exact = {
        str(raw).strip().lower()
        for raw in (args.recipient or [])
        if str(raw).strip()
    }
    try:
        processed = run_once(
            args.config,
            dry_run=args.dry_run,
            limit=max(1, min(args.limit, 500)),
            recipients_exact=recipients_exact,
            recipient_kind=str(args.recipient_kind or "any"),
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "processed": processed,
                    "dry_run": bool(args.dry_run),
                    "recipient_kind": str(args.recipient_kind or "any"),
                    "recipient_filters": sorted(recipients_exact),
                }
            )
        )
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(json.dumps({"ok": False, "error": f"http:{exc.code}", "detail": detail}))
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
