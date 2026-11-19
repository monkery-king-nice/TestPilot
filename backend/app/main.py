"""Composition root. Register reviewed modules explicitly, never scan/import drafts."""

from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from .core.config import Settings
from .core.database import Database
from .core.errors import install_error_handlers
from .modules.agent.router import build_router as build_agent_router
from .modules.agent.workflow import router as workflow_router
from .modules.cases.router import router as cases_router
from .modules.cases.service import CaseService
from .modules.projects.repository import ProjectRepository
from .modules.projects.router import router as projects_router
from .modules.reports.router import router as reports_router
from .modules.runs.repository import RunRepository
from .modules.runs.router import router as runs_router
from .modules.runs.service import RunService, RunSettings


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
    cases = CaseService(database, repository)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database.initialize()
        repository.initialize()
        cases.initialize()
        runs = RunService(
            RunRepository(settings.database_path), cases,
            RunSettings(demo_base_url=settings.demo_base_url),
        )
        application.state.run_service = runs
        try:
            for hook in startup_hooks:
                hook(application)
            yield
        finally:
            runs.close()

    application = FastAPI(title="TestPilot Alpha", version="0.1.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.database = database
    application.state.project_repository = repository
    application.state.cases_service = cases
    install_error_handlers(application)
    application.include_router(projects_router)
    application.include_router(build_agent_router(repository.load_text, provider=agent_provider, repository=repository))
    application.include_router(workflow_router)
    application.include_router(cases_router)
    application.include_router(runs_router)
    application.include_router(reports_router)
    for router in routers:
        application.include_router(router)

    @application.get("/api/health", tags=["服务状态"])
    def health():
        with database.connection() as connection:
            connection.execute("SELECT 1")
        return {"status": "ok"}

    return application


app = create_app()
