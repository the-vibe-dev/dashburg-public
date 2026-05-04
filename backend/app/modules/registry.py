from __future__ import annotations

from app.modules.base import BackendModule
from app.modules.localops.module import localops_module
from app.modules.mailcenter.module import mailcenter_module
from app.modules.memory.module import memory_module
from app.modules.orchestration.module import orchestration_module
from app.modules.projects.module import projects_module
from app.modules.remote_ops.module import remote_ops_module
from app.modules.system.module import system_module


def get_modules() -> list[BackendModule]:
    return [
        projects_module,
        memory_module,
        localops_module,
        mailcenter_module,
        orchestration_module,
        remote_ops_module,
        system_module,
    ]
