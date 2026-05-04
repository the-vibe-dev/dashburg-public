from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.module_system import activate_modules, catalog_payload, get_installed_keys, install_modules, uninstall_module, validate_module

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
