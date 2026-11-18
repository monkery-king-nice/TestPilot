"""Small host used by module tests and by the eventual backend composition root."""

from fastapi import FastAPI

from .router import router
from .service import RunService


def create_runs_app(service: RunService) -> FastAPI:
    app = FastAPI(title="TestPilot Runs Module")
    app.state.run_service = service
    app.include_router(router)
    return app
