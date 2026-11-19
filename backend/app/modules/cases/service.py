"""Case-owned tables; validation and writes share a short SQLite transaction."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from ...core.database import Database
from ..projects.repository import ProjectRepository
from ..runs.dependencies import PreflightRejected
from ..runs.models import CaseRef
from .models import CaseDraft, ManualCheckRequest
from .validation import validate_draft

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS cases (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
        version INTEGER NOT NULL, status TEXT NOT NULL, confirmed_version INTEGER,
        confirmed_at TEXT, draft_json TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS cases_project_idx ON cases(project_id)",
    """CREATE TABLE IF NOT EXISTS case_revisions (
        case_id TEXT NOT NULL REFERENCES cases(id), version INTEGER NOT NULL,
        draft_json TEXT NOT NULL, PRIMARY KEY(case_id, version))""",
    """CREATE TABLE IF NOT EXISTS manual_checks (
        id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
        version INTEGER NOT NULL, recorded_at TEXT NOT NULL, record_json TEXT NOT NULL)""",
)


def encode(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class CaseService:
    def __init__(self, database: Database, projects: ProjectRepository):
        self.database = database
        self.projects = projects

    def initialize(self) -> None:
        with self.database.connection(write=True) as connection:
            for statement in SCHEMA:
                connection.execute(statement)

    def _row(self, project_id, case_id, connection):
        self.projects.require_project(project_id, connection=connection)
        row = connection.execute(
            "SELECT * FROM cases WHERE id=? AND project_id=?", (case_id, project_id)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "项目下没有这条用例")
        return dict(row)

    def _inspect(self, project_id, draft, connection):
        requirement = self.projects.get_requirement(
            project_id, draft["requirement_id"], connection=connection
        )
        reasons, stale, endpoints = [], False, {}
        if requirement["version"] != draft["requirement_version"]:
            stale = True
            reasons.append("需求版本已过期，请复核用例并更新 requirement_version")
        for index, step in enumerate(draft["steps"], 1):
            endpoint = self.projects.get_endpoint(
                project_id, step["endpoint_id"], connection=connection
            )
            endpoints[endpoint["id"]] = endpoint
            if endpoint["version"] != step["endpoint_version"]:
                stale = True
                reasons.append(f"步骤 {index} 的接口版本已过期，请复核用例")
        row = connection.execute(
            "SELECT secrets_json FROM environments WHERE project_id=?", (project_id,)
        ).fetchone()
        keys = set(json.loads(row["secrets_json"])) if row else set()
        reasons.extend(validate_draft(draft, keys))
        return reasons, stale, requirement, endpoints

    def _view(self, row, connection):
        draft = json.loads(row["draft_json"])
        try:
            reasons, stale, _, _ = self._inspect(row["project_id"], draft, connection)
        except HTTPException as exc:
            # Persisted references may be removed by future source modules.
            reasons, stale = [str(exc.detail)], True
        if stale or (reasons and row["confirmed_version"] is not None):
            status = "NEEDS_REVIEW"
        elif reasons:
            status = "NEEDS_INFO"
        elif row["status"] == "CONFIRMED" and row["confirmed_version"] == row["version"]:
            status = "CONFIRMED"
        elif row["status"] == "NEEDS_REVIEW":
            status = "NEEDS_REVIEW"
        else:
            status = "READY"
        if status != row["status"]:
            connection.execute("UPDATE cases SET status=? WHERE id=?", (status, row["id"]))
        return {
            **draft, "id": row["id"], "version": row["version"], "status": status,
            "confirmed_version": row["confirmed_version"], "confirmed_at": row["confirmed_at"],
            "reasons": reasons,
        }

    def list_cases(self, project_id: str) -> list[dict]:
        with self.database.connection(write=True) as connection:
            self.projects.require_project(project_id, connection=connection)
            rows = connection.execute(
                "SELECT * FROM cases WHERE project_id=? ORDER BY rowid", (project_id,)
            ).fetchall()
            return [self._view(dict(row), connection) for row in rows]

    def get_case(self, project_id: str, case_id: str) -> dict:
        with self.database.connection(write=True) as connection:
            return self._view(self._row(project_id, case_id, connection), connection)

    def create_case(self, project_id: str, payload: CaseDraft) -> dict:
        draft = payload.document()
        case_id = str(uuid4())
        with self.database.connection(write=True) as connection:
            # Do not save absent or cross-project references, even as a draft.
            self._inspect(project_id, draft, connection)
            connection.execute(
                "INSERT INTO cases VALUES (?, ?, 1, 'DRAFT', NULL, NULL, ?)",
                (case_id, project_id, encode(draft)),
            )
            connection.execute(
                "INSERT INTO case_revisions VALUES (?, 1, ?)", (case_id, encode(draft))
            )
            return self._view(self._row(project_id, case_id, connection), connection)

    def update_case(self, project_id: str, case_id: str, payload: CaseDraft) -> dict:
        draft = payload.document()
        with self.database.connection(write=True) as connection:
            current = self._row(project_id, case_id, connection)
            self._inspect(project_id, draft, connection)
            version = current["version"] + 1
            status = "NEEDS_REVIEW" if current["confirmed_version"] is not None else "DRAFT"
            connection.execute(
                "UPDATE cases SET version=?, status=?, draft_json=? WHERE id=?",
                (version, status, encode(draft), case_id),
            )
            connection.execute(
                "INSERT INTO case_revisions VALUES (?, ?, ?)", (case_id, version, encode(draft))
            )
            return self._view(self._row(project_id, case_id, connection), connection)

    def _checked_snapshot(self, project_id, row, connection, *, require_confirmed):
        view = self._view(row, connection)
        reasons, stale, requirement, endpoints = self._inspect(
            project_id, json.loads(row["draft_json"]), connection
        )
        if require_confirmed and (
            view["status"] != "CONFIRMED" or row["confirmed_version"] != row["version"]
        ):
            reasons.insert(0, "当前用例版本尚未确认，或确认已失效，需要重新复核确认")
        return reasons, stale, {
            **json.loads(row["draft_json"]), "case_id": row["id"],
            "version": row["version"], "status": view["status"],
            "confirmed_version": row["confirmed_version"], "confirmed_at": row["confirmed_at"],
            "requirement": requirement, "endpoints": endpoints,
        }

    def confirm(self, project_id: str, case_id: str, version: int) -> dict:
        error = None
        with self.database.connection(write=True) as connection:
            row = self._row(project_id, case_id, connection)
            if row["version"] != version:
                raise HTTPException(409, "用例版本已变化，请重新读取后确认")
            reasons, stale, _ = self._checked_snapshot(
                project_id, row, connection, require_confirmed=False
            )
            if reasons:
                error = HTTPException(409 if stale else 422, "；".join(reasons))
            else:
                connection.execute(
                    "UPDATE cases SET status='CONFIRMED', confirmed_version=version, "
                    "confirmed_at=? WHERE id=?", (datetime.now(UTC).isoformat(), case_id)
                )
                result = self._view(self._row(project_id, case_id, connection), connection)
        # Commit NEEDS_REVIEW even when confirmation is rejected.
        if error:
            raise error
        return result

    def preflight(self, project_id: str, cases: Sequence[CaseRef]) -> list[dict]:
        """Shared executor entry: frozen snapshots in order, or per-case reasons.

        Confirmation calls the same _checked_snapshot validator with confirmation
        itself excluded. No environment values are put into the snapshots.
        """
        if not 1 <= len(cases) <= 20:
            raise PreflightRejected(["每批必须选择 1–20 条用例"])
        if len({item.id for item in cases}) != len(cases):
            raise PreflightRejected(["同一批次不能重复选择同一个用例"])
        reasons, snapshots = [], []
        with self.database.connection(write=True) as connection:
            self.projects.require_project(project_id, connection=connection)
            for ref in cases:
                try:
                    row = self._row(project_id, ref.id, connection)
                    errors, _, snapshot = self._checked_snapshot(
                        project_id, row, connection, require_confirmed=True
                    )
                    if row["version"] != ref.version:
                        errors.insert(0, "所选用例版本已过期，请重新选择")
                    reasons.extend(f"用例 {ref.id}：{item}" for item in errors)
                    snapshots.append(snapshot)
                except HTTPException as exc:
                    reasons.append(f"用例 {ref.id}：{exc.detail}")
        if reasons:
            raise PreflightRejected(reasons)
        return snapshots

    def read_environment(self, project_id: str, target: str) -> dict[str, str]:
        return self.projects.read_environment(project_id, target)

    def read_execution_target(self, project_id: str) -> dict:
        try:
            return self.projects.read_execution_target(project_id)
        except HTTPException as error:
            raise PreflightRejected([str(error.detail)]) from error

    def add_manual_check(self, project_id, case_id, payload: ManualCheckRequest):
        with self.database.connection(write=True) as connection:
            row = self._row(project_id, case_id, connection)
            if row["version"] != payload.version:
                raise HTTPException(409, "用例版本已变化，请按当前版本记录人工检查")
            for item in payload.items:
                if not item.check.strip() or not item.pass_condition.strip():
                    raise HTTPException(422, "检查项和通过条件不能为空白")
                if item.outcome != "NOT_CHECKED" and not item.evidence.strip():
                    raise HTTPException(422, "已检查项目必须填写证据")
            record = {
                "id": str(uuid4()), "case_id": case_id, "version": payload.version,
                "recorded_at": datetime.now(UTC).isoformat(),
                "items": payload.model_dump()["items"], "case": json.loads(row["draft_json"]),
            }
            connection.execute(
                "INSERT INTO manual_checks VALUES (?, ?, ?, ?, ?)",
                (record["id"], case_id, payload.version, record["recorded_at"], encode(record)),
            )
            return record

    def list_manual_checks(self, project_id, case_id):
        with self.database.connection() as connection:
            self._row(project_id, case_id, connection)
            rows = connection.execute(
                "SELECT record_json FROM manual_checks WHERE case_id=? ORDER BY rowid", (case_id,)
            ).fetchall()
            return [json.loads(row["record_json"]) for row in rows]
