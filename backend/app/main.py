"""Composition root. Register reviewed modules explicitly, never scan/import drafts."""

from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from .core.config import Settings
from .core.database import Database
from .core.errors import install_error_handlers
from .modules.agent.router import build_router as build_agent_router
from .modules.projects.repository import ProjectRepository
from .modules.projects.router import router as projects_router


def create_app(
    settings: Settings | None = None,
    *,
    routers: Sequence[APIRouter] = (),
    startup_hooks: Sequence[Callable[[FastAPI], None]] = (),
    agent_provider: Callable[[str], dict] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_path)
    repository = ProjectRepository(database)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database.initialize()
        repository.initialize()
        for hook in startup_hooks:
            hook(application)
        yield

    application = FastAPI(title="TestPilot Alpha", version="0.1.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.database = database
    application.state.project_repository = repository
    install_error_handlers(application)
    application.include_router(projects_router)
    application.include_router(build_agent_router(repository.load_text, provider=agent_provider))
    for router in routers:
        application.include_router(router)

    @application.get("/api/health", tags=["服务状态"])
    def health():
        with database.connection() as connection:
            connection.execute("SELECT 1")
        return {"status": "ok"}

    return application


app = create_app()
