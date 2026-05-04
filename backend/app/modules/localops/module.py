from __future__ import annotations

from app.modules.base import BackendModule
from app.modules.localops.router import router


localops_module = BackendModule(
    key="localops",
    name="LocalOps",
    sidebar_label="LocalOps",
    router=router,
    routes=[
        {"path": "/modules/local-ops/chat", "label": "Chat"},
        {"path": "/modules/local-ops/settings", "label": "Settings"},
    ],
    cards=[
        {
            "title": "LocalOps",
            "description": "Local chat orchestration with OpenAI API keys, Ollama providers, and workspace agents.",
            "href": "/modules/local-ops/chat",
        }
    ],
)
