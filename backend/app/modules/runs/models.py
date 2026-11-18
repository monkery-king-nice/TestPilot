"""Public API models. Persisted evidence is represented by StepResult."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CaseRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    version: int = Field(ge=1)


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: list[CaseRef] = Field(min_length=1, max_length=20)


class RunAccepted(BaseModel):
    run_id: str
    status: Literal["QUEUED"] = "QUEUED"


class Counts(BaseModel):
    PASS: int = 0
    FAIL: int = 0
    ERROR: int = 0
    BLOCKED: int = 0


class StepResult(BaseModel):
    name: str
    phase: str
    http_status: int | None = None
    elapsed_ms: int | None = None
    request_summary: str | None = None
    response_summary: str | None = None
    assertion_diffs: list[str] = Field(default_factory=list)
    error_stage: str | None = None


class CaseResult(BaseModel):
    case_id: str
    title: str
    outcome: Literal["PASS", "FAIL", "ERROR", "BLOCKED"]
    steps: list[StepResult]


class RunDetail(BaseModel):
    run_id: str
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "INTERRUPTED"]
    counts: Counts
    results: list[CaseResult]
