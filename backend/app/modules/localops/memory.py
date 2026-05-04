from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.modules.memory.storage import append_with_fallback, shared_available, shared_root
from app.models.remoteops import RemoteOpsNode


def _fmt_host(base_url: str) -> str:
    try:
        parsed = urlparse(base_url)
        return parsed.hostname or base_url
    except Exception:
        return base_url


def _load_json_array(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
    except Exception:
        pass
    return []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _home_dir() -> Path:
    return Path.home()


def _shared_root_or_none() -> Path | None:
    root_raw = str(os.getenv("DASHBURG_SHARED_MEMORY_ROOT", "") or "").strip()
    if not root_raw:
        return None
    if not shared_available():
        return None
    return shared_root()


def _mem_path() -> Path:
    shared = _shared_root_or_none()
    if shared:
        return shared / "routing" / "MEM.md"
    return _home_dir() / "MEM.md"


def _locations_json_path() -> Path:
    shared = _shared_root_or_none()
    if shared:
        return shared / "routing" / "LOCATIONS.json"
    return _home_dir() / "LOCATIONS.json"


def _locations_md_path() -> Path:
    shared = _shared_root_or_none()
    if shared:
        return shared / "routing" / "LOCATIONS.md"
    return _home_dir() / "LOCATIONS.md"


def _deltas_path() -> Path:
    shared = _shared_root_or_none()
    if shared:
        return shared / "memory" / "MEMORY_DELTAS.jsonl"
    return _home_dir() / "MEMORY_DELTAS.jsonl"


def _safe_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _safe_load(path: Path, default: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def _default_locations_index(nodes: list[RemoteOpsNode], ssh_user: str, ssh_key_path: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": _now_iso(),
        "nodes": {},
    }
    for node in nodes:
        host = _fmt_host(node.base_url)
        repos = _load_json_array(node.allowed_repos_json)
        default_repo = repos[0] if repos else "/"
        repo_rows = []
        for repo in repos or [default_repo]:
            repo_rows.append(
                {
                    "repo_path": repo,
                    "repo_purpose": "pending",
                    "last_investigation_file": "pending",
                    "last_profile_file": "pending",
                    "updated_at": "pending",
                    "notes": "",
                }
            )
        payload["nodes"][node.id] = {
            "label": node.label or node.id,
            "host": host,
            "ssh": f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes {ssh_user}@{host}",
            "investigations_root": "~/runner/investigations",
            "repos": repo_rows,
        }
    return payload


def _render_locations_md(index_payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# LOCATIONS")
    lines.append("")
    lines.append(f"Last updated: {datetime.now(timezone.utc).date().isoformat()}")
    lines.append("")
    lines.append("Purpose:")
    lines.append("- Dense navigation map for remote nodes and repos.")
    lines.append("- Tracks latest investigation/profile memory locations and concise repo purpose.")
    lines.append("")
    lines.append("## Update Rules")
    lines.append("- Keep repo entries dense and current; avoid long narratives.")
    lines.append("- Prefer absolute remote paths for `last_investigation_file` and `last_profile_file`.")
    lines.append("- Update `updated_at` and `notes` whenever a node adjustment is made.")
    lines.append("")
    nodes = index_payload.get("nodes") if isinstance(index_payload, dict) else {}
    if not isinstance(nodes, dict) or not nodes:
        lines.append("_No nodes recorded yet._")
        return "\n".join(lines) + "\n"

    for node_id in sorted(nodes.keys()):
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            continue
        lines.append(f"## Node: {node_id}")
        lines.append(f"- Label: {str(node.get('label') or node_id)}")
        lines.append(f"- Host: {str(node.get('host') or '')}")
        lines.append(f"- SSH: `{str(node.get('ssh') or '')}`")
        lines.append(f"- Investigations root: `{str(node.get('investigations_root') or '~/runner/investigations')}`")
        lines.append("")
        lines.append("| repo_path | repo_purpose | last_investigation_file | last_profile_file | updated_at | notes |")
        lines.append("|---|---|---|---|---|---|")
        repos = node.get("repos")
        if isinstance(repos, list) and repos:
            for row in repos:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    f"| {str(row.get('repo_path') or 'pending')} | "
                    f"{str(row.get('repo_purpose') or 'pending')} | "
                    f"{str(row.get('last_investigation_file') or 'pending')} | "
                    f"{str(row.get('last_profile_file') or 'pending')} | "
                    f"{str(row.get('updated_at') or 'pending')} | "
                    f"{str(row.get('notes') or '')} |"
                )
        else:
            lines.append("| pending | pending | pending | pending | pending | pending |")
        lines.append("")
    return "\n".join(lines) + "\n"


def ensure_locations_index(session: Session) -> dict[str, Any]:
    ssh_key_path = os.getenv("LOCALOPS_MEM_SSH_KEY_PATH", "~/.ssh/dashburg_remoteops")
    ssh_user = os.getenv("LOCALOPS_MEM_SSH_USER", "operator")
    nodes = session.exec(select(RemoteOpsNode).order_by(RemoteOpsNode.id.asc())).all()
    path = _locations_json_path()
    seeded = _default_locations_index(nodes, ssh_user, ssh_key_path)
    if path.exists():
        current = _safe_load(path, {})
        if isinstance(current, dict):
            nodes_cur = current.get("nodes")
            if not isinstance(nodes_cur, dict):
                nodes_cur = {}
                current["nodes"] = nodes_cur
            nodes_seed = seeded.get("nodes") if isinstance(seeded, dict) else {}
            if isinstance(nodes_seed, dict):
                for node_id, node_payload in nodes_seed.items():
                    if node_id not in nodes_cur or not isinstance(nodes_cur.get(node_id), dict):
                        nodes_cur[node_id] = node_payload
            write_locations_index(current)
            return current
    payload = seeded
    _safe_dump(path, payload)
    _locations_md_path().write_text(_render_locations_md(payload), encoding="utf-8")
    return payload


def write_locations_index(index_payload: dict[str, Any]) -> None:
    if not isinstance(index_payload, dict):
        return
    index_payload["generated_at"] = _now_iso()
    _safe_dump(_locations_json_path(), index_payload)
    _locations_md_path().write_text(_render_locations_md(index_payload), encoding="utf-8")


def upsert_location_entry(
    *,
    node_id: str,
    repo_path: str,
    repo_purpose: str = "",
    last_investigation_file: str = "",
    last_profile_file: str = "",
    notes: str = "",
) -> None:
    node = str(node_id or "").strip()
    if not node:
        return
    repo = str(repo_path or "").strip() or "/"
    payload = _safe_load(_locations_json_path(), {})
    if not isinstance(payload, dict):
        payload = {"generated_at": _now_iso(), "nodes": {}}
    nodes = payload.get("nodes")
    if not isinstance(nodes, dict):
        nodes = {}
        payload["nodes"] = nodes
    if node not in nodes or not isinstance(nodes.get(node), dict):
        nodes[node] = {
            "label": node,
            "host": "",
            "ssh": "",
            "investigations_root": "~/runner/investigations",
            "repos": [],
        }
    node_row = nodes[node]
    repos = node_row.get("repos")
    if not isinstance(repos, list):
        repos = []
        node_row["repos"] = repos
    match: dict[str, Any] | None = None
    for row in repos:
        if isinstance(row, dict) and str(row.get("repo_path") or "").strip() == repo:
            match = row
            break
    if match is None:
        match = {
            "repo_path": repo,
            "repo_purpose": "pending",
            "last_investigation_file": "pending",
            "last_profile_file": "pending",
            "updated_at": "pending",
            "notes": "",
        }
        repos.append(match)
    if str(repo_purpose or "").strip():
        match["repo_purpose"] = str(repo_purpose).strip()
    if str(last_investigation_file or "").strip():
        match["last_investigation_file"] = str(last_investigation_file).strip()
    if str(last_profile_file or "").strip():
        match["last_profile_file"] = str(last_profile_file).strip()
    if str(notes or "").strip():
        match["notes"] = str(notes).strip()
    match["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    write_locations_index(payload)


def append_memory_delta(delta: dict[str, Any], max_lines: int = 2000) -> None:
    _ = max_lines
    row = dict(delta or {})
    row["ts"] = row.get("ts") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    shared = _shared_root_or_none()
    if shared:
        append_with_fallback("memory/MEMORY_DELTAS.jsonl", row)
        return
    path = _deltas_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True) + "\n")


def ensure_localops_mem_file(session: Session) -> str:
    home_dir = _home_dir()
    mem_path = _mem_path()
    ssh_key_path = os.getenv("LOCALOPS_MEM_SSH_KEY_PATH", "~/.ssh/dashburg_remoteops")
    ssh_user = os.getenv("LOCALOPS_MEM_SSH_USER", "operator")
    _ = ensure_locations_index(session)

    nodes = session.exec(select(RemoteOpsNode).order_by(RemoteOpsNode.id.asc())).all()
    lines: list[str] = []
    lines.append("# MEM")
    lines.append("")
    lines.append(f"Generated: {_now_iso()}")
    lines.append("")
    lines.append("## Local Host")
    lines.append(f"- Home: {home_dir}")
    lines.append("- Dashburg root: ~/apps/dashgithub")
    lines.append("- Preferred SSH key path: " + ssh_key_path)
    lines.append("- Runner root: ~/runner")
    lines.append("- Runner venv: ~/runner/.venv")
    lines.append("- Activate runner venv: `source ~/runner/.venv/bin/activate`")
    lines.append(f"- Locations registry (dense routing): `{_locations_md_path()}`")
    lines.append(f"- Structured locations index: `{_locations_json_path()}`")
    lines.append(f"- Memory deltas (append-only): `{_deltas_path()}`")
    lines.append("")
    lines.append("## Dense Memory Loading")
    lines.append("- Load `LOCATIONS.md` first to route to relevant node + repo.")
    lines.append("- Load only latest matching delta lines from `MEMORY_DELTAS.jsonl` for node/repo context.")
    lines.append("- Open full investigation/profile markdown only when needed.")
    lines.append("")
    lines.append("## Remote Node Inventory")
    if not nodes:
        lines.append("- No RemoteOps nodes configured yet.")
    else:
        for node in nodes:
            host = _fmt_host(node.base_url)
            repos = _load_json_array(node.allowed_repos_json)
            default_repo = repos[0] if repos else f"/home/{ssh_user}"
            lines.append(f"### {node.id}")
            lines.append(f"- Label: {node.label or node.id}")
            lines.append(f"- Enabled: {str(node.enabled).lower()}")
            lines.append(f"- Runner URL: {node.base_url}")
            lines.append(f"- Host: {host}")
            lines.append(f"- Supports codex: {str(node.supports_codex).lower()}")
            lines.append(f"- Supports terminal: {str(node.supports_terminal).lower()}")
            if node.key_id:
                lines.append(f"- Runner key_id: {node.key_id}")
            lines.append(f"- SSH: `ssh -i {ssh_key_path} -o IdentitiesOnly=yes {ssh_user}@{host}`")
            lines.append(f"- Default repo: `{default_repo}`")
            if repos:
                lines.append("- Allowed repos:")
                for repo in repos:
                    lines.append(f"  - `{repo}`")
            lines.append("")

    lines.append("## How To Execute On Remote Nodes")
    lines.append("- Prefer RemoteOps jobs instead of ad-hoc shell on remote boxes.")
    lines.append("- For debugging on a node, open one persistent SSH session and run multiple commands in that same session.")
    lines.append("- Avoid repeated one-off `ssh host command` patterns when investigating complex issues.")
    lines.append("- Before remote work, open `LOCATIONS.md` and use the node section to find last investigation/profile files.")
    lines.append("- In local terminal, use:")
    lines.append("  - `remoteops nodes list`")
    lines.append("  - `remoteops node info <node_id>`")
    lines.append("  - `remoteops job create <node_id> <job_type> --json '{...}'`")
    lines.append("  - `remoteops job tail <job_id>`")
    lines.append("")
    lines.append("## Runner Execution Context")
    lines.append("- RemoteOps runner scripts are always in `~/runner`.")
    lines.append("- Use runner venv before running runner utilities:")
    lines.append("  - `cd ~/runner`")
    lines.append("  - `source ~/runner/.venv/bin/activate`")
    lines.append("- If a command depends on runner Python packages, execute from this venv.")
    lines.append("")
    lines.append("## Remote Investigation Conclusion Files")
    lines.append("- After remote debugging, write conclusion notes on the remote node for later review.")
    lines.append("- Default location on remote node: `~/runner/investigations/`")
    lines.append("- Write two files:")
    lines.append("  - timestamped conclusion: `<YYYYMMDD-HHMMSS>-<short-topic>.md`")
    lines.append("  - durable profile: `<host>-<repo>-profile.md`")
    lines.append("- Conclusion content: scope, commands run, findings, root cause, next actions.")
    lines.append("- Durable profile content:")
    lines.append("  - system observations (OS/services/versions)")
    lines.append("  - discovered settings/config paths")
    lines.append("  - repo layout and important entrypoints")
    lines.append("  - recurring issues and known-good fixes")
    lines.append("- Example command sequence on remote:")
    lines.append("  - `mkdir -p ~/runner/investigations`")
    lines.append("  - `cat > ~/runner/investigations/$(date +%Y%m%d-%H%M%S)-issue.md <<\\'MD\\'`")
    lines.append("  - `# write summary markdown here`")
    lines.append("  - `MD`")
    lines.append("  - `cat > ~/runner/investigations/<host>-<repo>-profile.md <<\\'MD\\'`")
    lines.append("  - `# write durable host/repo notes here`")
    lines.append("  - `MD`")
    lines.append("")
    lines.append("## Security")
    lines.append("- Never print or paste private keys into chat output.")
    lines.append("- This file stores key paths and topology, not raw secrets.")
    lines.append("")

    mem_path.write_text("\n".join(lines), encoding="utf-8")
    return str(mem_path)
