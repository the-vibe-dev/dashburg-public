from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.module_system import (
    activate_modules,
    bootstrap_all_runtimes,
    bootstrap_runtime,
    catalog_payload,
    get_installed_keys,
    install_modules,
    install_runtime,
    install_runtime_service,
    runtime_service_status,
    runtime_status,
    start_runtime,
    start_runtime_service,
    stop_runtime,
    uninstall_module,
    validate_module,
)

router = APIRouter(prefix="/api/module-system", tags=["module-system"])


class ModuleRequest(BaseModel):
    key: str = Field(min_length=2)


@router.get("/catalog")
def get_catalog() -> list[dict[str, Any]]:
    return catalog_payload()


@router.get("/installed")
def get_installed() -> dict[str, Any]:
    return {"installed": get_installed_keys()}


@router.post("/install")
def post_install(payload: ModuleRequest, request: Request) -> dict[str, Any]:
    result = install_modules([payload.key])
    activated = activate_modules(request.app, result["resolved"])
    result["activated"] = activated
    result["validation"] = [validate_module(key) for key in result["resolved"]]
    return result


@router.post("/uninstall")
def post_uninstall(payload: ModuleRequest) -> dict[str, Any]:
    return uninstall_module(payload.key)


@router.post("/validate")
def post_validate(payload: ModuleRequest) -> dict[str, Any]:
    return validate_module(payload.key)


@router.post("/smoke")
def post_smoke(payload: ModuleRequest) -> dict[str, Any]:
    validation = validate_module(payload.key)
    validation["smoke_ran"] = True
    return validation


@router.post("/sync")
def post_sync(payload: ModuleRequest | None = None) -> dict[str, Any]:
    if payload is None:
        return {"catalog": catalog_payload(), "installed": get_installed_keys()}
    return validate_module(payload.key)


@router.post("/runtime/install")
def post_runtime_install(payload: ModuleRequest) -> dict[str, Any]:
    return install_runtime(payload.key)


@router.post("/runtime/start")
def post_runtime_start(payload: ModuleRequest) -> dict[str, Any]:
    return start_runtime(payload.key)


@router.post("/runtime/stop")
def post_runtime_stop(payload: ModuleRequest) -> dict[str, Any]:
    return stop_runtime(payload.key)


@router.post("/runtime/bootstrap")
def post_runtime_bootstrap(payload: ModuleRequest) -> dict[str, Any]:
    return bootstrap_runtime(payload.key)


@router.post("/runtime/bootstrap-all")
def post_runtime_bootstrap_all() -> dict[str, Any]:
    return bootstrap_all_runtimes()


@router.post("/runtime/install-service")
def post_runtime_install_service(payload: ModuleRequest) -> dict[str, Any]:
    return install_runtime_service(payload.key)


@router.post("/runtime/start-service")
def post_runtime_start_service(payload: ModuleRequest) -> dict[str, Any]:
    return start_runtime_service(payload.key)


@router.post("/runtime/status")
def post_runtime_status(payload: ModuleRequest) -> dict[str, Any]:
    return runtime_status(payload.key)


@router.post("/runtime/service-status")
def post_runtime_service_status(payload: ModuleRequest) -> dict[str, Any]:
    return runtime_service_status(payload.key)
