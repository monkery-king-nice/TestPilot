"""Wire format shared with Agent and frontend; incomplete drafts can be saved."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Assertion(StrictModel):
    type: str = Field(min_length=1, max_length=64)
    path: str | None = Field(default=None, max_length=512)
    expected: JsonValue = None


class CaseStep(StrictModel):
    name: str = Field(min_length=1, max_length=64)
    phase: Literal["setup", "test"]
    endpoint_id: str = Field(min_length=1, max_length=128)
    endpoint_version: int = Field(ge=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: JsonValue = None
    assertions: list[Assertion] = Field(default_factory=list, max_length=30)
    extract: dict[str, str] = Field(default_factory=dict)


class CaseDraft(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    requirement_id: str = Field(min_length=1, max_length=128)
    requirement_version: int = Field(ge=1)
    expected_basis: str = Field(default="", max_length=8000)
    steps: list[CaseStep] = Field(default_factory=list, max_length=5)

    def document(self) -> dict:
        document = self.model_dump(mode="json")
        for item, step in zip(document["steps"], self.steps):
            # Missing expected differs from an explicit JSON null equality.
            item["assertions"] = [a.model_dump(exclude_unset=True) for a in step.assertions]
        return document


class ConfirmRequest(StrictModel):
    version: int = Field(ge=1)


class ManualCheckItem(StrictModel):
    check: str = Field(min_length=1, max_length=1000)
    pass_condition: str = Field(min_length=1, max_length=2000)
    outcome: Literal["PASS", "FAIL", "NOT_CHECKED"]
    evidence: str = Field(default="", max_length=8000)


class ManualCheckRequest(StrictModel):
    version: int = Field(ge=1)
    items: list[ManualCheckItem] = Field(min_length=1, max_length=30)
