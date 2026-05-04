from app.modules.base import BackendModule
from app.modules.memory.router import router

memory_module = BackendModule(
    key="memory",
    name="Memory",
    sidebar_label="Memory",
    router=router,
    routes=[
        {"path": "/modules/memory", "label": "Memory"},
    ],
    cards=[
        {
            "title": "Memory",
            "description": "Shared NFS-backed memory, session index, relationships, and compact retrieval briefs.",
            "href": "/modules/memory",
        }
    ],
)
