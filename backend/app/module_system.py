from __future__ import annotations

import importlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.modules.base import BackendModule

HOST_ROOT = Path(__file__).resolve().parents[2]
MODULE_PACKS_ROOT = HOST_ROOT.parent / "dashburg-modules"
STATE_PATH = HOST_ROOT / "data" / "module-system" / "installed.json"

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
    if runtime_service_dir:
        runtime_service_ok = (manifest.files_dir / runtime_service_dir).exists()
    backend_import_ok = False
    backend_error = ""
    try:
        import_backend_module(key, catalog)
        backend_import_ok = True
    except Exception as exc:  # pragma: no cover
        backend_error = str(exc)
    frontend_dir = HOST_ROOT / "web" / "src" / "modules"
    frontend_exists = (frontend_dir / manifest.frontend_key.replace("-", "")).exists() or any(
        frontend_dir.rglob("module.tsx")
    )
    ok = files_dir_ok and runtime_service_ok and backend_import_ok and not missing_modules and not missing_core and frontend_exists
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
            "mode": str(manifest.runtime.get("mode") or "host-only"),
            "service_dir": runtime_service_dir,
            "service_dir_ok": runtime_service_ok,
            "default_port": manifest.runtime.get("default_port"),
            "start_command": manifest.runtime.get("start_command"),
            "env_file": manifest.runtime.get("env_file"),
            "notes": manifest.runtime.get("notes"),
        },
        "smoke": {
            "solo_harness": bool(files_dir_ok and backend_import_ok),
            "host_install": bool(backend_import_ok and not missing_modules and not missing_core),
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
    reverse = sorted(
        manifest.key
        for manifest in manifests.values()
        if manifest.key in installed and key in manifest.module_dependencies
    )
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
