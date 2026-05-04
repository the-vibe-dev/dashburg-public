from __future__ import annotations

from contextlib import asynccontextmanager

from app.core.env import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.core import router as core_router
from app.api.events import attach_router
from app.api.module_system import router as module_system_router
from app.core.config import ensure_data_dirs
from app.db.session import init_db
from app.module_system import activate_modules, get_installed_keys
from app.modules.registry import get_modules
from app.services.sse import SSEBroker

broker = SSEBroker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_dirs()
    init_db()
    app.state.activated_module_keys = set()
    activate_modules(app, get_installed_keys())
    yield


app = FastAPI(title="Dashgithub API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4174",
        "http://127.0.0.1:4174",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost|192\.168\.\d+\.\d+)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(core_router)
app.include_router(module_system_router)
app.include_router(attach_router(broker))
for module in get_modules():
    app.include_router(module.router)
