from typing import Annotated

from fastapi import APIRouter, Depends, Request

from .models import CaseDraft, ConfirmRequest, ManualCheckRequest
from .service import CaseService

router = APIRouter(prefix="/api/projects/{project_id}/cases", tags=["用例与人工检查"])


def get_service(request: Request) -> CaseService:
    return request.app.state.cases_service


Service = Annotated[CaseService, Depends(get_service)]


@router.get("")
def list_cases(project_id: str, service: Service):
    return service.list_cases(project_id)


@router.post("", status_code=201)
def create_case(project_id: str, payload: CaseDraft, service: Service):
    return service.create_case(project_id, payload)


@router.get("/{case_id}")
def get_case(project_id: str, case_id: str, service: Service):
    return service.get_case(project_id, case_id)


@router.patch("/{case_id}")
def update_case(project_id: str, case_id: str, payload: CaseDraft, service: Service):
    return service.update_case(project_id, case_id, payload)


@router.post("/{case_id}/confirm")
def confirm_case(project_id: str, case_id: str, payload: ConfirmRequest, service: Service):
    return service.confirm(project_id, case_id, payload.version)


@router.post("/{case_id}/manual-checks", status_code=201)
def add_manual_check(
    project_id: str, case_id: str, payload: ManualCheckRequest, service: Service
):
    return service.add_manual_check(project_id, case_id, payload)


@router.get("/{case_id}/manual-checks")
def list_manual_checks(project_id: str, case_id: str, service: Service):
    return service.list_manual_checks(project_id, case_id)
