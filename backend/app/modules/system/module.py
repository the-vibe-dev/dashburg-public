from app.modules.base import BackendModule
from app.modules.system.router import router

system_module = BackendModule(
    key="system",
    name="System",
    sidebar_label="System",
    router=router,
    routes=[{"path": "/settings", "label": "Settings"}],
    cards=[
        {
            "title": "System Health",
            "description": "Configuration, health checks, and runtime metrics.",
            "href": "/settings",
        }
    ],
)
