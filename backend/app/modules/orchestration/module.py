from app.modules.base import BackendModule
from app.modules.orchestration.router import router

orchestration_module = BackendModule(
    key="orchestration",
    name="Orchestration",
    sidebar_label="Orchestration",
    router=router,
    routes=[
        {"path": "/modules/orchestration", "label": "Overview"},
        {"path": "/modules/orchestration/jobs", "label": "Jobs"},
    ],
    cards=[
        {
            "title": "Orchestration",
            "description": "Delegated multi-node Codex orchestration with node-local workers and existing xterm launch.",
            "href": "/modules/orchestration",
        }
    ],
)
