from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from .archives import MAX_UPLOAD, upload_name
from .models import (
    ConfirmImportEndpoints,
    DocumentPreviewInput,
    Endpoint,
    EndpointInput,
    EnvironmentInput,
    EnvironmentView,
    Project,
    ProjectInput,
    Requirement,
    RequirementCreateInput,
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


@router.get(
    "/{project_id}/requirements", response_model=list[Requirement], response_model_exclude_none=True
)
def list_requirements(project_id: str, repository: Repository):
    return repository.list_requirements(project_id)


@router.post(
    "/{project_id}/requirements",
    response_model=Requirement,
    response_model_exclude_none=True,
    status_code=201,
)
def create_requirement(project_id: str, payload: RequirementCreateInput, repository: Repository):
    return repository.create_requirement(project_id, payload.text, payload.source)


@router.patch(
    "/{project_id}/requirements/{requirement_id}",
    response_model=Requirement,
    response_model_exclude_none=True,
)
def update_requirement(
    project_id: str,
    requirement_id: str,
    payload: RequirementInput,
    repository: Repository,
):
    return repository.update_requirement(project_id, requirement_id, payload.text)


@router.post(
    "/{project_id}/imports",
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def upload_project_import(
    project_id: str,
    request: Request,
    repository: Repository,
    filename: Annotated[str, Query(min_length=1, max_length=512)],
):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"application/zip", "application/octet-stream"}:
        raise HTTPException(415, "请以 application/zip 上传 ZIP 原始二进制内容")
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            length = int(declared)
        except ValueError as exc:
            raise HTTPException(400, "上传长度无效") from exc
        if length < 0:
            raise HTTPException(400, "上传长度无效")
        if length > MAX_UPLOAD:
            raise HTTPException(413, "ZIP 上传最多 8 MiB")
    filename = upload_name(filename)
    await run_in_threadpool(repository.require_project, project_id)
    data = bytearray()
    try:
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "ZIP 上传最多 8 MiB")
            data.extend(chunk)
    except ClientDisconnect as exc:
        raise HTTPException(400, "上传中断，请重新上传 ZIP") from exc
    if declared is not None and length != len(data):
        raise HTTPException(400, "上传长度与实际数据不一致，请重新上传 ZIP")
    return await run_in_threadpool(repository.create_import, project_id, filename, bytes(data))


@router.get("/{project_id}/imports/{import_id}")
def get_project_import(project_id: str, import_id: str, repository: Repository):
    return repository.get_import(project_id, import_id)


@router.post("/{project_id}/imports/{import_id}/preview")
def preview_project_document(
    project_id: str,
    import_id: str,
    payload: DocumentPreviewInput,
    repository: Repository,
):
    return repository.preview_import_document(
        project_id, import_id, payload.path, payload.start, payload.end
    )


@router.post("/{project_id}/imports/{import_id}/confirm-endpoints")
def confirm_project_endpoints(
    project_id: str,
    import_id: str,
    payload: ConfirmImportEndpoints,
    repository: Repository,
):
    return repository.confirm_import_endpoints(project_id, import_id, payload.candidate_ids)


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
