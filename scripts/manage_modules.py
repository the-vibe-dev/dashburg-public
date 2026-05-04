#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.module_system import catalog_payload, install_modules, save_state, uninstall_module, validate_module  # noqa: E402


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

    args = parser.parse_args()
    if args.command == "list":
        print(json.dumps(catalog_payload(), indent=2))
        return 0
    if args.command == "install":
        print(json.dumps(install_modules([args.key]), indent=2))
        return 0
    if args.command == "validate":
        print(json.dumps(validate_module(args.key), indent=2))
        return 0
    if args.command == "uninstall":
        print(json.dumps(uninstall_module(args.key), indent=2))
        return 0
    if args.command == "reset":
        print(json.dumps(save_state(args.keys), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
