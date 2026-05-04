#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.module_system import (  # noqa: E402
    bootstrap_all_runtimes,
    bootstrap_runtime,
    catalog_payload,
    install_modules,
    install_runtime,
    install_runtime_service,
    runtime_health,
    runtime_service_status,
    runtime_status,
    save_state,
    start_runtime,
    start_runtime_service,
    stop_runtime,
    uninstall_module,
    validate_module,
    discover_manifests,
)


def _print(payload: object) -> int:
    print(json.dumps(payload, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage optional Dashburg public modules")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List catalog entries")
    install_parser = sub.add_parser("install", help="Install a module and its dependencies")
    install_parser.add_argument("key")
    validate_parser = sub.add_parser("validate", help="Validate a module")
    validate_parser.add_argument("key")
    uninstall_parser = sub.add_parser("uninstall", help="Uninstall a module")
    uninstall_parser.add_argument("key")
    reset_parser = sub.add_parser("reset", help="Reset installed module state")
    reset_parser.add_argument("keys", nargs="*", help="Optional installed keys to keep")

    runtime_install_parser = sub.add_parser("runtime-install", help="Install bundled local runtime for a module")
    runtime_install_parser.add_argument("key")
    runtime_start_parser = sub.add_parser("runtime-start", help="Start bundled local runtime for a module")
    runtime_start_parser.add_argument("key")
    runtime_stop_parser = sub.add_parser("runtime-stop", help="Stop bundled local runtime for a module")
    runtime_stop_parser.add_argument("key")
    runtime_status_parser = sub.add_parser("runtime-status", help="Get runtime status for a module")
    runtime_status_parser.add_argument("key")
    runtime_health_parser = sub.add_parser("runtime-health", help="Get runtime health for a module")
    runtime_health_parser.add_argument("key")
    runtime_bootstrap_parser = sub.add_parser("runtime-bootstrap", help="Install and start bundled local runtime for a module")
    runtime_bootstrap_parser.add_argument("key")
    sub.add_parser("runtime-bootstrap-all", help="Install and start all installed bundled local runtimes")
    runtime_service_install_parser = sub.add_parser("runtime-install-service", help="Install a user systemd service for a module runtime")
    runtime_service_install_parser.add_argument("key")
    runtime_service_start_parser = sub.add_parser("runtime-start-service", help="Start a user systemd service for a module runtime")
    runtime_service_start_parser.add_argument("key")
    runtime_service_status_parser = sub.add_parser("runtime-service-status", help="Get user systemd service status for a module runtime")
    runtime_service_status_parser.add_argument("key")

    args = parser.parse_args()
    if args.command == "list":
        return _print(catalog_payload())
    if args.command == "install":
        return _print(install_modules([args.key]))
    if args.command == "validate":
        return _print(validate_module(args.key))
    if args.command == "uninstall":
        return _print(uninstall_module(args.key))
    if args.command == "reset":
        return _print(save_state(args.keys))
    if args.command == "runtime-install":
        return _print(install_runtime(args.key))
    if args.command == "runtime-start":
        return _print(start_runtime(args.key))
    if args.command == "runtime-stop":
        return _print(stop_runtime(args.key))
    if args.command == "runtime-status":
        return _print(runtime_status(args.key))
    if args.command == "runtime-health":
        manifests = discover_manifests()
        return _print(runtime_health(manifests[args.key]))
    if args.command == "runtime-bootstrap":
        return _print(bootstrap_runtime(args.key))
    if args.command == "runtime-bootstrap-all":
        return _print(bootstrap_all_runtimes())
    if args.command == "runtime-install-service":
        return _print(install_runtime_service(args.key))
    if args.command == "runtime-start-service":
        return _print(start_runtime_service(args.key))
    if args.command == "runtime-service-status":
        return _print(runtime_service_status(args.key))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
