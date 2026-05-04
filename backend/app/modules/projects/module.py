from fastapi import APIRouter

from app.modules.base import BackendModule
from app.modules.projects.router import router, tasks_router

api_router = APIRouter()
api_router.include_router(router)
api_router.include_router(tasks_router)

projects_module = BackendModule(
    key="projects",
    name="TaskVault",
    sidebar_label="TaskVault",
    router=api_router,
    routes=[
        {"path": "/projects", "label": "TaskVault"},
        {"path": "/projects/:id", "label": "TaskVault Detail"},
        {"path": "/projects/:id/workspace", "label": "TaskVault Workspace"},
    ],
    cards=[
        {
            "title": "TaskVault",
            "description": "Track plans and implementation notes in a Notion-like block editor.",
            "href": "/projects",
        }
    ],
)
