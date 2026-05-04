#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def _hub_url() -> str:
    return os.getenv("REMOTEOPS_HUB_URL", "http://hub.example.local:8431").rstrip("/")


def _token() -> str:
    token_path = os.getenv("REMOTEOPS_CLIENT_TOKEN_FILE", "/etc/dashburg/remoteops-client-token")
    if os.path.exists(token_path):
        return open(token_path, "r", encoding="utf-8").read().strip()
    return os.getenv("REMOTEOPS_CLIENT_TOKEN", "").strip()


def _request(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{_hub_url()}{path}", method=method, data=data)
    req.add_header("Accept", "application/json")
    token = _token()
    if token:
        req.add_header("X-RemoteOps-Client-Token", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body_raw = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body_raw}", file=sys.stderr)
        sys.exit(2)


def cmd_nodes_list(_: argparse.Namespace) -> int:
    rows = _request("GET", "/api/remote/servers")
    for row in rows:
        print(f"{row.get('id')}\t{row.get('name')}\t{row.get('status')}\tterminal={row.get('supports_terminal')}\tcodex={row.get('codex_enabled')}")
    return 0


def cmd_node_info(args: argparse.Namespace) -> int:
    body = _request("GET", f"/api/remote/servers/{urllib.parse.quote(args.node_id)}")
    print(json.dumps(body, indent=2))
    return 0


def cmd_job_create(args: argparse.Namespace) -> int:
    params = json.loads(args.json or "{}")
    payload = {"type": args.job_type, "params": params}
    body = _request("POST", f"/api/remote/servers/{urllib.parse.quote(args.node_id)}/jobs", payload)
    print(json.dumps(body, indent=2))
    return 0


def cmd_job_tail(args: argparse.Namespace) -> int:
    offset = 0
    print(f"Tailing job {args.job_id} (Ctrl+C to stop)")
    while True:
        data = _request("GET", f"/api/remote/jobs/{urllib.parse.quote(args.job_id)}")
        status = str(data.get("status", "unknown"))

        req = urllib.request.Request(
            f"{_hub_url()}/api/remote/jobs/{urllib.parse.quote(args.job_id)}/stream",
            method="GET",
            headers={"Accept": "text/event-stream", "X-RemoteOps-Client-Token": _token()},
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if "\"line\"" in payload:
                        try:
                            body = json.loads(payload)
                        except Exception:
                            continue
                        text = body.get("line")
                        if text:
                            print(text)
                        offset = int(body.get("offset", offset))
        except Exception:
            pass

        if status in {"completed", "failed", "cancelled"}:
            print(f"Job ended with status={status}")
            break
        time.sleep(1.0)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="remoteops")
    sub = parser.add_subparsers(dest="cmd", required=True)

    nodes = sub.add_parser("nodes")
    nodes_sub = nodes.add_subparsers(dest="nodes_cmd", required=True)
    nodes_list = nodes_sub.add_parser("list")
    nodes_list.set_defaults(func=cmd_nodes_list)

    node = sub.add_parser("node")
    node_sub = node.add_subparsers(dest="node_cmd", required=True)
    node_info = node_sub.add_parser("info")
    node_info.add_argument("node_id")
    node_info.set_defaults(func=cmd_node_info)

    job = sub.add_parser("job")
    job_sub = job.add_subparsers(dest="job_cmd", required=True)
    job_create = job_sub.add_parser("create")
    job_create.add_argument("node_id")
    job_create.add_argument("job_type")
    job_create.add_argument("--json", default="{}")
    job_create.set_defaults(func=cmd_job_create)

    job_tail = job_sub.add_parser("tail")
    job_tail.add_argument("job_id")
    job_tail.set_defaults(func=cmd_job_tail)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
