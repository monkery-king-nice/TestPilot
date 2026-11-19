"""Integration boundary owned jointly by cases and project-data modules.

The cases module implements preflight; the project-data module implements the
internal environment reader. No HTTP route or public environment response is
used by the executor.
"""

from typing import Mapping, Protocol, Sequence

from .models import CaseRef


class PreflightRejected(Exception):
    """Reject the whole batch before a run row or target request is created."""

    def __init__(self, reasons: Sequence[str]):
        self.reasons = list(reasons) or ["用例预检失败"]
        super().__init__("；".join(self.reasons))


class EnvironmentChanged(Exception):
    """The frozen target/version no longer matches the current environment."""


class RunDependencies(Protocol):
    def preflight(self, project_id: str, cases: Sequence[CaseRef]) -> list[dict]:
        """Return frozen case snapshots in request order or raise PreflightRejected.

        Each snapshot contains case_id, title, version, requirement_id,
        requirement_version, expected_basis, steps and endpoints. endpoints maps
        endpoint_id to its frozen {id, method, path, version} object.
        """

    def read_execution_target(self, project_id: str) -> dict:
        """Return project-owned target metadata or raise PreflightRejected."""

    def read_environment(
        self, project_id: str, target: str, expected_version: int | None = None
    ) -> Mapping[str, str]:
        """Atomically validate and read secrets; never persist returned values."""
