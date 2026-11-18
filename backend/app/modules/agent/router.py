"""Register build_router(load_text) in the shared FastAPI app."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .clarify import ModelError, clarify


class ClarifyInput(BaseModel):
    requirement_id: str = Field(min_length=1)


def build_router(load_text, provider=None):
    """load_text(project_id, requirement_id) -> str or None; must scope by both IDs."""
    router = APIRouter()

    @router.post("/api/projects/{project_id}/agent/clarify")
    def post_clarify(project_id: str, payload: ClarifyInput):
        text = load_text(project_id, payload.requirement_id)
        if text is None:
            raise HTTPException(404, "项目下没有这条需求")
        try:
            return clarify(text) if provider is None else clarify(text, provider)
        except ModelError as exc:
            raise HTTPException(502, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return router
