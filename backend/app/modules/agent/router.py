"""Register build_router(load_text) in the shared FastAPI app."""
from hashlib import sha256
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .clarify import ModelError, clarify, clarify_project
from .project_context import project_context


class ClarifyInput(BaseModel):
    requirement_id: str = Field(min_length=1)
    requirement_version: int | None = Field(default=None, ge=1)
    context_digest: str | None = Field(default=None, min_length=64, max_length=64)


def context_digest(context):
    return sha256(json.dumps(context, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def checked_context(repository, project_id, payload):
    requirement = repository.get_requirement(
        project_id, payload.requirement_id, expected_version=payload.requirement_version,
    )
    context = project_context(repository, project_id, requirement, repository.list_endpoints(project_id))
    digest = context_digest(context)
    if payload.context_digest is not None and payload.context_digest != digest:
        raise HTTPException(409, "项目资料已变化，请重新预览发送内容")
    return context, digest


def build_router(load_text, provider=None, *, repository=None):
    """load_text(project_id, requirement_id) -> str or None; must scope by both IDs."""
    router = APIRouter()

    if repository is not None:
        @router.post("/api/projects/{project_id}/agent/preview")
        def preview(project_id: str, payload: ClarifyInput):
            context, digest = checked_context(repository, project_id, payload)
            return {"context": context, "digest": digest}

    @router.post("/api/projects/{project_id}/agent/clarify")
    def post_clarify(project_id: str, payload: ClarifyInput):
        try:
            if repository is None:
                text = load_text(project_id, payload.requirement_id)
                if text is None:
                    raise HTTPException(404, "项目下没有这条需求")
                return clarify(text) if provider is None else clarify(text, provider)
            context, _ = checked_context(repository, project_id, payload)
            requirement = context["requirement"]
            if provider is not None and "source_excerpt" not in context:
                response = clarify(context["requirement"]["text"], provider)
            else:
                response = clarify_project(context, provider)
            repository.get_requirement(project_id, requirement["id"], expected_version=requirement["version"])
            return response
        except ModelError as exc:
            raise HTTPException(502, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return router
