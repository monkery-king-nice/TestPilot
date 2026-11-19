"""Register build_router(load_text) in the shared FastAPI app."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .clarify import ModelError, clarify, clarify_project
from .project_context import project_context


class ClarifyInput(BaseModel):
    requirement_id: str = Field(min_length=1)
    requirement_version: int | None = Field(default=None, ge=1)


def build_router(load_text, provider=None, *, repository=None):
    """load_text(project_id, requirement_id) -> str or None; must scope by both IDs."""
    router = APIRouter()

    @router.post("/api/projects/{project_id}/agent/clarify")
    def post_clarify(project_id: str, payload: ClarifyInput):
        try:
            if repository is None:
                text = load_text(project_id, payload.requirement_id)
                if text is None:
                    raise HTTPException(404, "项目下没有这条需求")
                return clarify(text) if provider is None else clarify(text, provider)
            requirement = repository.get_requirement(
                project_id, payload.requirement_id, expected_version=payload.requirement_version,
            )
            context = project_context(repository, project_id, requirement, repository.list_endpoints(project_id))
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
