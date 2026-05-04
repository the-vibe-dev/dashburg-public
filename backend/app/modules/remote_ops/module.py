from app.modules.base import BackendModule
from app.modules.remote_ops.router import router

remote_ops_module = BackendModule(
    key="remote_ops",
    name="RemoteOps",
    sidebar_label="RemoteOps",
    router=router,
    routes=[
        {"path": "/modules/remote-ops/nodes", "label": "Nodes"},
        {"path": "/modules/remote-ops/jobs", "label": "Jobs"},
        {"path": "/modules/remote-ops/codex", "label": "Codex Jobs"},
        {"path": "/modules/remote-ops/terminal", "label": "Terminal"},
        {"path": "/modules/remote-ops/settings", "label": "Settings"},
    ],
    cards=[
        {
            "title": "RemoteOps",
            "description": "Control Center for nodes, jobs, and interactive main-terminal sessions.",
            "href": "/modules/remote-ops/nodes",
        }
    ],
)
