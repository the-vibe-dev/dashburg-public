from __future__ import annotations

import importlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.modules.base import BackendModule

HOST_ROOT = Path(__file__).resolve().parents[2]
MODULE_PACKS_ROOT = HOST_ROOT.parent / "dashburg-modules"
STATE_PATH = HOST_ROOT / "data" / "module-system" / "installed.json"
RUNTIME_PID_DIR = HOST_ROOT / "data" / "module-system" / "pids"
RUNTIME_LOG_DIR = HOST_ROOT / "data" / "module-system" / "logs"

CORE_CAPABILITIES = {
    "projects",
    "memory",
    "remote-ops",
    "localops",
    "mailcenter",
    "orchestration",
    "system",
    "nodehealth",
    "chat-api",
}

OPTIONAL_MODULE_IMPORTS = {
    "ideavault": "app.modules.ideavault.module:ideavault_module",
    "idea-factory": "app.modules.appgen.module:appgen_module",
    "topic-insights": "app.modules.topic_proxy.module:topic_proxy_module",
    "trends-researcher": "app.modules.trends_proxy.module:trends_proxy_module",
    "discord-control": "app.modules.discord.module:discord_module",
    "webagent": "app.modules.webagent.module:webagent_module",
    "skilled-agents": "app.modules.skilled_agents.module:skilled_agents_module",
    "schedule-ops": "app.modules.schedule_ops.module:schedule_ops_module",
}


@dataclass
class ModuleManifest:
    key: str
    name: str
    version: str
    description: str
    module_dependencies: list[str]
    core_capabilities: list[str]
    backend_import: str
    frontend_key: str
    frontend_export: str
    runtime: dict[str, Any]
    module_dir: Path

    @property
    def files_dir(self) -> Path:
        return self.module_dir / "files"


@dataclass
class RuntimeHealthResult:
    ok: bool
    status: str
    url: str
    detail: str
    payload: dict[str, Any] | None


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_state() -> dict[str, Any]:
    return _read_json(STATE_PATH, {"installed": []})


def save_state(installed: list[str]) -> dict[str, Any]:
    unique = sorted({item for item in installed if item})
    payload = {"installed": unique}
    _write_json(STATE_PATH, payload)
    return payload


def get_installed_keys() -> list[str]:
    payload = load_state()
    raw = payload.get("installed") if isinstance(payload, dict) else []
    return [str(item) for item in raw if str(item).strip()]


def discover_manifests() -> dict[str, ModuleManifest]:
    out: dict[str, ModuleManifest] = {}
    if not MODULE_PACKS_ROOT.exists():
        return out
    for path in sorted(MODULE_PACKS_ROOT.glob("*/dashburg-module.json")):
        raw = _read_json(path, {})
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or path.parent.name).strip()
        if not key:
            continue
        deps = raw.get("dependencies") if isinstance(raw.get("dependencies"), dict) else {}
        backend = raw.get("backend") if isinstance(raw.get("backend"), dict) else {}
        frontend = raw.get("frontend") if isinstance(raw.get("frontend"), dict) else {}
        out[key] = ModuleManifest(
            key=key,
            name=str(raw.get("name") or key),
            version=str(raw.get("version") or "0.1.0"),
            description=str(raw.get("description") or ""),
            module_dependencies=[str(item) for item in deps.get("modules", []) if str(item).strip()],
            core_capabilities=[str(item) for item in deps.get("core_capabilities", []) if str(item).strip()],
            backend_import=str(backend.get("import") or OPTIONAL_MODULE_IMPORTS.get(key, "")),
            frontend_key=str(frontend.get("key") or key),
            frontend_export=str(frontend.get("export") or ""),
            runtime=raw.get("runtime") if isinstance(raw.get("runtime"), dict) else {},
            module_dir=path.parent,
        )
    return out


def resolve_install_set(requested: list[str], manifests: dict[str, ModuleManifest] | None = None) -> list[str]:
    catalog = manifests or discover_manifests()
    resolved: list[str] = []
    seen: set[str] = set()

    def visit(key: str) -> None:
        if key in seen:
            return
        seen.add(key)
        manifest = catalog.get(key)
        if not manifest:
            raise KeyError(key)
        for dep in manifest.module_dependencies:
            visit(dep)
        resolved.append(key)

    for key in requested:
        visit(key)
    return resolved


def copy_module_files(key: str, manifests: dict[str, ModuleManifest] | None = None) -> list[str]:
    catalog = manifests or discover_manifests()
    manifest = catalog[key]
    copied: list[str] = []
    if not manifest.files_dir.exists():
        return copied
    for source in sorted(path for path in manifest.files_dir.rglob("*") if path.is_file()):
        relative = source.relative_to(manifest.files_dir)
        target = HOST_ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(str(relative))
    return copied


def _import_symbol(target: str) -> Any:
    module_name, _, symbol_name = target.partition(":")
    if not module_name or not symbol_name:
        raise ValueError(f"invalid import target: {target}")
    module = importlib.import_module(module_name)
    return getattr(module, symbol_name)


def import_backend_module(key: str, manifests: dict[str, ModuleManifest] | None = None) -> BackendModule:
    catalog = manifests or discover_manifests()
    manifest = catalog[key]
    symbol = _import_symbol(manifest.backend_import)
    if not isinstance(symbol, BackendModule):
        raise TypeError(f"{manifest.backend_import} is not a BackendModule")
    return symbol


def runtime_host_dir(manifest: ModuleManifest) -> Path | None:
    service_dir = str(manifest.runtime.get("service_dir") or "").strip()
    if not service_dir:
        return None
    return HOST_ROOT / service_dir


def runtime_env_file(manifest: ModuleManifest) -> Path | None:
    host_dir = runtime_host_dir(manifest)
    env_name = str(manifest.runtime.get("env_file") or "").strip()
    if not host_dir or not env_name:
        return None
    return host_dir / env_name


def runtime_example_env_file(manifest: ModuleManifest) -> Path | None:
    env_path = runtime_env_file(manifest)
    if not env_path:
        return None
    return env_path.with_name(f"{env_path.name}.example")


def runtime_install_command(manifest: ModuleManifest) -> str:
    explicit = str(manifest.runtime.get("install_command") or "").strip()
    if explicit:
        return explicit
    host_dir = runtime_host_dir(manifest)
    if not host_dir:
        return ""
    if (host_dir / "pyproject.toml").exists():
        return "pip install -e .[dev]"
    if (host_dir / "requirements.txt").exists():
        return "pip install -r requirements.txt"
    return ""


def runtime_post_install(manifest: ModuleManifest) -> list[str]:
    rows = manifest.runtime.get("post_install")
    if isinstance(rows, list):
        return [str(item).strip() for item in rows if str(item).strip()]
    return []


def runtime_health_url(manifest: ModuleManifest) -> str:
    explicit = str(manifest.runtime.get("health_url") or "").strip()
    if explicit:
        return explicit
    health_path = str(manifest.runtime.get("health_path") or "").strip() or "/health"
    port = manifest.runtime.get("default_port")
    if port:
        return f"http://127.0.0.1:{port}{health_path}"
    return ""


def runtime_pid_path(key: str) -> Path:
    RUNTIME_PID_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_PID_DIR / f"{key}.pid"


def runtime_log_path(key: str) -> Path:
    RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_LOG_DIR / f"{key}.log"


def _run_bash(command: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", "-lc", command],
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def runtime_status(key: str, manifests: dict[str, ModuleManifest] | None = None) -> dict[str, Any]:
    catalog = manifests or discover_manifests()
    manifest = catalog[key]
    pid_file = runtime_pid_path(key)
    pid: int | None = None
    running = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except Exception:
            pid = None
        if pid is not None:
            running = _pid_is_running(pid)
            if not running:
                pid_file.unlink(missing_ok=True)
    health = runtime_health(manifest)
    return {
        "key": key,
        "mode": str(manifest.runtime.get("mode") or "host-only"),
        "pid": pid,
        "running": running,
        "health": health,
        "log_path": str(runtime_log_path(key)),
    }


def runtime_health(manifest: ModuleManifest) -> dict[str, Any]:
    url = runtime_health_url(manifest)
    if not url:
        return {"ok": True, "status": "n/a", "url": "", "detail": "no runtime health endpoint declared", "payload": None}
    headers: dict[str, str] = {"Accept": "application/json"}
    bridge_key = os.getenv("DISCORD_BRIDGE_API_KEY", "").strip()
    if bridge_key:
        headers["X-Dashburg-Bridge-Key"] = bridge_key
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            raw = response.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw else {}
        status = str((payload or {}).get("status") or "ok")
        return {"ok": True, "status": status, "url": url, "detail": "reachable", "payload": payload if isinstance(payload, dict) else None}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        return {"ok": False, "status": f"http_{exc.code}", "url": url, "detail": detail[:400], "payload": None}
    except Exception as exc:
        return {"ok": False, "status": "unreachable", "url": url, "detail": str(exc), "payload": None}


def install_runtime(key: str, manifests: dict[str, ModuleManifest] | None = None) -> dict[str, Any]:
    catalog = manifests or discover_manifests()
    manifest = catalog[key]
    mode = str(manifest.runtime.get("mode") or "host-only")
    host_dir = runtime_host_dir(manifest)
    if mode != "bundled-local-service":
        return {"ok": True, "key": key, "mode": mode, "detail": "no bundled runtime install required"}
    if not host_dir or not host_dir.exists():
        return {"ok": False, "key": key, "error": "runtime_dir_missing", "runtime_dir": str(host_dir) if host_dir else ""}
    env_example = runtime_example_env_file(manifest)
    env_path = runtime_env_file(manifest)
    install_cmd = runtime_install_command(manifest)
    post_install = runtime_post_install(manifest)
    command_parts = [
        "python3 -m venv .venv",
        "source .venv/bin/activate",
        "pip install -U pip",
    ]
    if install_cmd:
        command_parts.append(install_cmd)
    if env_example and env_path and env_example.exists() and not env_path.exists():
        command_parts.append(f"cp {shlex.quote(str(env_example.name))} {shlex.quote(str(env_path.name))}")
    command_parts.extend(post_install)
    result = _run_bash(" && ".join(command_parts), cwd=host_dir)
    return {
        "ok": result.returncode == 0,
        "key": key,
        "mode": mode,
        "runtime_dir": str(host_dir),
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "install_command": install_cmd,
        "post_install": post_install,
    }


def start_runtime(key: str, manifests: dict[str, ModuleManifest] | None = None) -> dict[str, Any]:
    catalog = manifests or discover_manifests()
    manifest = catalog[key]
    mode = str(manifest.runtime.get("mode") or "host-only")
    if mode != "bundled-local-service":
        return {"ok": True, "key": key, "mode": mode, "detail": "no separate bundled runtime start required"}
    host_dir = runtime_host_dir(manifest)
    start_command = str(manifest.runtime.get("start_command") or "").strip()
    if not host_dir or not host_dir.exists() or not start_command:
        return {"ok": False, "key": key, "error": "runtime_start_config_missing", "runtime_dir": str(host_dir) if host_dir else ""}
    pid_file = runtime_pid_path(key)
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if _pid_is_running(pid):
                return {"ok": True, "key": key, "mode": mode, "pid": pid, "detail": "already running"}
        except Exception:
            pass
        pid_file.unlink(missing_ok=True)
    log_path = runtime_log_path(key)
    log_fp = open(log_path, "ab")
    proc = subprocess.Popen(
        ["/bin/bash", "-lc", f"source .venv/bin/activate && exec {start_command}"],
        cwd=str(host_dir),
        stdout=log_fp,
        stderr=log_fp,
        preexec_fn=os.setsid,
    )
    pid_file.write_text(f"{proc.pid}\n", encoding="utf-8")
    return {"ok": True, "key": key, "mode": mode, "pid": proc.pid, "log_path": str(log_path)}


def stop_runtime(key: str, manifests: dict[str, ModuleManifest] | None = None) -> dict[str, Any]:
    pid_file = runtime_pid_path(key)
    if not pid_file.exists():
        return {"ok": True, "key": key, "detail": "not running"}
    try:
        pid = int(pid_file.read_text().strip())
    except Exception:
        pid_file.unlink(missing_ok=True)
        return {"ok": True, "key": key, "detail": "stale pid file removed"}
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass
    pid_file.unlink(missing_ok=True)
    return {"ok": True, "key": key, "pid": pid, "detail": "stop requested"}


def systemd_service_name(key: str) -> str:
    return f"dashburg-module-{key}.service"


def render_systemd_unit(key: str, manifests: dict[str, ModuleManifest] | None = None) -> str:
    catalog = manifests or discover_manifests()
    manifest = catalog[key]
    host_dir = runtime_host_dir(manifest)
    if not host_dir:
        raise ValueError(f"module {key} has no bundled runtime directory")
    env_path = runtime_env_file(manifest)
    start_command = str(manifest.runtime.get("start_command") or "").strip()
    if not start_command:
        raise ValueError(f"module {key} has no runtime start command")
    lines = [
        "[Unit]",
        f"Description=Dashburg Module Runtime: {manifest.name}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=simple",
        f"WorkingDirectory={host_dir}",
        f"EnvironmentFile=-{HOST_ROOT / '.env'}",
    ]
    if env_path:
        lines.append(f"EnvironmentFile=-{env_path}")
    lines.extend(
        [
            f"ExecStart=/bin/bash -lc 'source .venv/bin/activate && exec {start_command}'",
            "Restart=always",
            "RestartSec=3",
            f"StandardOutput=append:{runtime_log_path(key)}",
            f"StandardError=append:{runtime_log_path(key)}",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    return "\n".join(lines)


def install_runtime_service(key: str, manifests: dict[str, ModuleManifest] | None = None) -> dict[str, Any]:
    catalog = manifests or discover_manifests()
    manifest = catalog[key]
    mode = str(manifest.runtime.get("mode") or "host-only")
    if mode != "bundled-local-service":
        return {"ok": True, "key": key, "mode": mode, "detail": "no bundled runtime service required"}
    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    service_path = systemd_dir / systemd_service_name(key)
    service_path.write_text(render_systemd_unit(key, catalog), encoding="utf-8")
    result = _run_bash(f"systemctl --user daemon-reload && systemctl --user enable {shlex.quote(service_path.name)}")
    return {"ok": result.returncode == 0, "key": key, "service_path": str(service_path), "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}


def start_runtime_service(key: str) -> dict[str, Any]:
    result = _run_bash(f"systemctl --user start {shlex.quote(systemd_service_name(key))}")
    return {"ok": result.returncode == 0, "key": key, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}


def runtime_service_status(key: str) -> dict[str, Any]:
    result = _run_bash(f"systemctl --user status {shlex.quote(systemd_service_name(key))} --no-pager")
    return {"ok": result.returncode == 0, "key": key, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}


def bootstrap_runtime(key: str, manifests: dict[str, ModuleManifest] | None = None) -> dict[str, Any]:
    catalog = manifests or discover_manifests()
    manifest = catalog[key]
    mode = str(manifest.runtime.get("mode") or "host-only")
    if mode != "bundled-local-service":
        return {"ok": True, "key": key, "mode": mode, "detail": "no separate bundled runtime bootstrap required"}
    install_result = install_runtime(key, catalog)
    if not install_result.get("ok"):
        return {"ok": False, "key": key, "step": "install", "result": install_result}
    service_result = install_runtime_service(key, catalog)
    if service_result.get("ok"):
        start_result = start_runtime_service(key)
        health_result = runtime_health(manifest)
        return {"ok": bool(start_result.get("ok")), "key": key, "step": "service", "install": install_result, "service": service_result, "start": start_result, "health": health_result}
    start_result = start_runtime(key, catalog)
    health_result = runtime_health(manifest)
    return {"ok": bool(start_result.get("ok")), "key": key, "step": "direct", "install": install_result, "service": service_result, "start": start_result, "health": health_result}


def installed_bundled_runtime_keys(manifests: dict[str, ModuleManifest] | None = None) -> list[str]:
    catalog = manifests or discover_manifests()
    installed = set(get_installed_keys())
    keys: list[str] = []
    for key in sorted(installed):
        manifest = catalog.get(key)
        if not manifest:
            continue
        if str(manifest.runtime.get("mode") or "host-only") == "bundled-local-service":
            keys.append(key)
    return keys


def bootstrap_all_runtimes(manifests: dict[str, ModuleManifest] | None = None) -> dict[str, Any]:
    catalog = manifests or discover_manifests()
    keys = installed_bundled_runtime_keys(catalog)
    results: list[dict[str, Any]] = []
    ok = True
    for key in keys:
        result = bootstrap_runtime(key, catalog)
        results.append(result)
        if not result.get("ok"):
            ok = False
    return {"ok": ok, "keys": keys, "results": results}


def validate_module(key: str, manifests: dict[str, ModuleManifest] | None = None) -> dict[str, Any]:
    catalog = manifests or discover_manifests()
    manifest = catalog.get(key)
    if not manifest:
        return {"ok": False, "key": key, "error": "manifest_not_found"}
    installed = set(get_installed_keys())
    missing_modules = [dep for dep in manifest.module_dependencies if dep not in installed]
    missing_core = [cap for cap in manifest.core_capabilities if cap not in CORE_CAPABILITIES]
    files_dir_ok = manifest.files_dir.exists()
    runtime_service_dir = str(manifest.runtime.get("service_dir") or "").strip()
    runtime_service_ok = True
    host_runtime_ok = True
    host_runtime_dir = runtime_host_dir(manifest)
    if runtime_service_dir:
        runtime_service_ok = (manifest.files_dir / runtime_service_dir).exists()
        host_runtime_ok = bool(host_runtime_dir and host_runtime_dir.exists())
    backend_import_ok = False
    backend_error = ""
    try:
        import_backend_module(key, catalog)
        backend_import_ok = True
    except Exception as exc:  # pragma: no cover
        backend_error = str(exc)
    frontend_dir = HOST_ROOT / "web" / "src" / "modules"
    frontend_exists = (frontend_dir / manifest.frontend_key.replace("-", "")).exists() or any(frontend_dir.rglob("module.tsx"))
    health = runtime_health(manifest)
    runtime_mode = str(manifest.runtime.get("mode") or "host-only")
    runtime_required = runtime_mode == "bundled-local-service"
    runtime_ready = runtime_service_ok and host_runtime_ok and (health.get("ok") if runtime_required else True)
    runtime_ok_for_validation = True
    if runtime_required and key in installed:
        runtime_ok_for_validation = bool(health.get("ok")) and runtime_ready
    ok = files_dir_ok and runtime_service_ok and backend_import_ok and not missing_modules and not missing_core and frontend_exists and runtime_ok_for_validation
    return {
        "ok": ok,
        "key": key,
        "name": manifest.name,
        "installed": key in installed,
        "missing_modules": missing_modules,
        "missing_core_capabilities": missing_core,
        "files_dir_ok": files_dir_ok,
        "backend_import_ok": backend_import_ok,
        "backend_error": backend_error,
        "frontend_entry_ok": frontend_exists,
        "runtime": {
            "mode": runtime_mode,
            "service_dir": runtime_service_dir,
            "service_dir_ok": runtime_service_ok,
            "host_runtime_dir": str(host_runtime_dir) if host_runtime_dir else "",
            "host_runtime_dir_ok": host_runtime_ok,
            "default_port": manifest.runtime.get("default_port"),
            "start_command": manifest.runtime.get("start_command"),
            "install_command": runtime_install_command(manifest),
            "env_file": manifest.runtime.get("env_file"),
            "notes": manifest.runtime.get("notes"),
            "health": health,
            "runtime_ready": runtime_ready,
        },
        "smoke": {
            "solo_harness": bool(files_dir_ok and backend_import_ok),
            "host_install": bool(backend_import_ok and not missing_modules and not missing_core),
            "runtime_health": bool(health.get("ok")) if runtime_required else True,
        },
    }


def catalog_payload() -> list[dict[str, Any]]:
    manifests = discover_manifests()
    installed = set(get_installed_keys())
    out: list[dict[str, Any]] = []
    for key, manifest in manifests.items():
        validation = validate_module(key, manifests)
        out.append(
            {
                "key": key,
                "name": manifest.name,
                "version": manifest.version,
                "description": manifest.description,
                "installed": key in installed,
                "runtime": manifest.runtime,
                "dependencies": {
                    "modules": manifest.module_dependencies,
                    "core_capabilities": manifest.core_capabilities,
                },
                "validation": validation,
            }
        )
    return out


def install_modules(keys: list[str]) -> dict[str, Any]:
    manifests = discover_manifests()
    resolved = resolve_install_set(keys, manifests)
    copied: dict[str, list[str]] = {}
    for key in resolved:
        copied[key] = copy_module_files(key, manifests)
    next_installed = sorted(set(get_installed_keys()).union(resolved))
    save_state(next_installed)
    return {"requested": keys, "resolved": resolved, "installed": next_installed, "copied": copied}


def uninstall_module(key: str) -> dict[str, Any]:
    manifests = discover_manifests()
    installed = set(get_installed_keys())
    reverse = sorted(manifest.key for manifest in manifests.values() if manifest.key in installed and key in manifest.module_dependencies)
    if reverse:
        return {"ok": False, "key": key, "error": "reverse_dependencies", "dependents": reverse}
    installed.discard(key)
    save_state(sorted(installed))
    return {"ok": True, "key": key, "installed": sorted(installed), "restart_required": True}


def get_enabled_optional_modules() -> list[BackendModule]:
    manifests = discover_manifests()
    out: list[BackendModule] = []
    for key in get_installed_keys():
        if key not in OPTIONAL_MODULE_IMPORTS:
            continue
        try:
            out.append(import_backend_module(key, manifests))
        except Exception:
            continue
    return out


def activate_modules(app: Any, keys: list[str]) -> list[str]:
    manifests = discover_manifests()
    activated = set(getattr(app.state, "activated_module_keys", set()))
    for key in keys:
        if key in activated or key not in OPTIONAL_MODULE_IMPORTS:
            continue
        module = import_backend_module(key, manifests)
        app.include_router(module.router)
        activated.add(key)
    app.state.activated_module_keys = activated
    return sorted(activated)
