"""Alpha run routes. The host application supplies app.state.run_service."""

from fastapi import APIRouter, HTTPException, Request, status

from .dependencies import PreflightRejected
from .models import CreateRunRequest, RunAccepted, RunDetail
from .repository import RunConflict, RunNotFound
from .service import RunService

router = APIRouter(prefix="/api/projects/{project_id}/runs", tags=["runs"])


def _service(request: Request) -> RunService:
    return request.app.state.run_service


@router.post("", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_run(project_id: str, payload: CreateRunRequest, request: Request) -> RunAccepted:
    try:
        run_id = _service(request).create_run(project_id, payload.cases)
    except PreflightRejected as error:
        raise HTTPException(status_code=422, detail="；".join(error.reasons)) from error
    except RunConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RunAccepted(run_id=run_id)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(project_id: str, run_id: str, request: Request) -> RunDetail:
    try:
        return _service(request).get_run(project_id, run_id)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
