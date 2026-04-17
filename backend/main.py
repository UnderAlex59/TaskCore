from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from anyio import Path as AnyPath
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agents.graph_export import export_agent_graph_images
from app.core.config import get_settings
from app.core.database import is_database_ready
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.projects import router as projects_router
from app.routers.proposals import router as proposals_router
from app.routers.tasks import router as tasks_router
from app.routers.users import router as users_router
from app.routers.validation import router as validation_router

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await AnyPath(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    try:
        export_agent_graph_images(Path(settings.LANGGRAPH_IMAGES_DIR))
    except Exception:
        logger.exception("Failed to export LangGraph PNG files into %s", settings.LANGGRAPH_IMAGES_DIR)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Интеллектуальная платформа управления задачами",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(admin_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(projects_router)
    app.include_router(tasks_router)
    app.include_router(validation_router)
    app.include_router(chat_router)
    app.include_router(proposals_router)
    uploads_app = StaticFiles(directory=settings.UPLOAD_DIR, check_dir=False)
    app.mount("/uploads", uploads_app, name="uploads")
    app.mount("/api/uploads", StaticFiles(directory=settings.UPLOAD_DIR, check_dir=False), name="api-uploads")

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["system"])
    async def readyz() -> dict[str, str]:
        if await is_database_ready():
            return {"status": "ok", "database": "ok"}

        raise HTTPException(status_code=503, detail="database unavailable")

    return app


app = create_app()
