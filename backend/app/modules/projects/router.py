from typing import Annotated

from fastapi import APIRouter, Depends, Request

from .models import (
    Endpoint,
    EndpointInput,
    EnvironmentInput,
    EnvironmentView,
    Project,
    ProjectInput,
    Requirement,
    RequirementInput,
)
from .repository import ProjectRepository

router = APIRouter(prefix="/api/projects", tags=["项目与基础数据"])


def get_repository(request: Request) -> ProjectRepository:
    return request.app.state.project_repository


Repository = Annotated[ProjectRepository, Depends(get_repository)]


@router.get("", response_model=list[Project])
def list_projects(repository: Repository):
    return repository.list_projects()


@router.post("", response_model=Project, status_code=201)
def create_project(payload: ProjectInput, repository: Repository):
    return repository.create_project(payload.name)


@router.get("/{project_id}/requirements", response_model=list[Requirement])
def list_requirements(project_id: str, repository: Repository):
    return repository.list_requirements(project_id)


@router.post("/{project_id}/requirements", response_model=Requirement, status_code=201)
def create_requirement(project_id: str, payload: RequirementInput, repository: Repository):
    return repository.create_requirement(project_id, payload.text)


@router.patch("/{project_id}/requirements/{requirement_id}", response_model=Requirement)
def update_requirement(
    project_id: str,
    requirement_id: str,
    payload: RequirementInput,
    repository: Repository,
):
    return repository.update_requirement(project_id, requirement_id, payload.text)


@router.get("/{project_id}/endpoints", response_model=list[Endpoint])
def list_endpoints(project_id: str, repository: Repository):
    return repository.list_endpoints(project_id)


@router.post("/{project_id}/endpoints", response_model=Endpoint, status_code=201)
def create_endpoint(project_id: str, payload: EndpointInput, repository: Repository):
    return repository.create_endpoint(project_id, payload.method, payload.path)


@router.get("/{project_id}/environment", response_model=EnvironmentView)
def get_environment(project_id: str, repository: Repository):
    return repository.get_environment(project_id)


@router.put("/{project_id}/environment", response_model=EnvironmentView)
def put_environment(project_id: str, payload: EnvironmentInput, repository: Repository):
    secrets = {
        "username": payload.secrets.username.get_secret_value(),
        "password": payload.secrets.password.get_secret_value(),
    }
    return repository.put_environment(project_id, payload.target, secrets)
