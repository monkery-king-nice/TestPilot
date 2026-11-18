"""Project-scoped data access, also used internally by Agent/cases/executor."""

import json
import sqlite3
from uuid import uuid4

from fastapi import HTTPException

from ...core.database import Database

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS requirements (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id),
        text TEXT NOT NULL, version INTEGER NOT NULL CHECK(version >= 1))""",
    """CREATE INDEX IF NOT EXISTS requirements_project_idx
        ON requirements(project_id)""",
    """CREATE TABLE IF NOT EXISTS requirement_revisions (
        requirement_id TEXT NOT NULL REFERENCES requirements(id),
        version INTEGER NOT NULL CHECK(version >= 1), text TEXT NOT NULL,
        PRIMARY KEY(requirement_id, version))""",
    """CREATE TABLE IF NOT EXISTS endpoints (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id),
        method TEXT NOT NULL, path TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1))""",
    """CREATE INDEX IF NOT EXISTS endpoints_project_idx ON endpoints(project_id)""",
    """CREATE TABLE IF NOT EXISTS environments (
        project_id TEXT PRIMARY KEY REFERENCES projects(id),
        target TEXT NOT NULL CHECK(target = 'demo'), secrets_json TEXT NOT NULL)""",
)


class ProjectRepository:
    def __init__(self, database: Database):
        self.database = database

    def initialize(self) -> None:
        with self.database.connection(write=True) as connection:
            for statement in SCHEMA:
                connection.execute(statement)

    def require_project(self, project_id: str, *, connection=None) -> dict:
        if connection is None:
            with self.database.connection() as opened:
                return self.require_project(project_id, connection=opened)
        row = connection.execute(
            "SELECT id, name FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "项目不存在")
        return dict(row)

    def list_projects(self) -> list[dict]:
        with self.database.connection() as connection:
            return [
                dict(row)
                for row in connection.execute("SELECT id, name FROM projects ORDER BY rowid")
            ]

    def create_project(self, name: str) -> dict:
        project = {"id": str(uuid4()), "name": name}
        with self.database.connection(write=True) as connection:
            connection.execute(
                "INSERT INTO projects(id, name) VALUES (?, ?)",
                (project["id"], name),
            )
        return project

    def list_requirements(self, project_id: str) -> list[dict]:
        with self.database.connection() as connection:
            self.require_project(project_id, connection=connection)
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT id, text, version FROM requirements WHERE project_id=? ORDER BY rowid",
                    (project_id,),
                )
            ]

    def create_requirement(self, project_id: str, text: str) -> dict:
        requirement_id = str(uuid4())
        with self.database.connection(write=True) as connection:
            self.require_project(project_id, connection=connection)
            connection.execute(
                "INSERT INTO requirements(id, project_id, text, version) VALUES (?, ?, ?, 1)",
                (requirement_id, project_id, text),
            )
            connection.execute(
                "INSERT INTO requirement_revisions VALUES (?, 1, ?)", (requirement_id, text)
            )
        return {"id": requirement_id, "text": text, "version": 1}

    def get_requirement(
        self,
        project_id: str,
        requirement_id: str,
        *,
        expected_version: int | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict:
        if connection is None:
            with self.database.connection() as opened:
                return self.get_requirement(
                    project_id,
                    requirement_id,
                    expected_version=expected_version,
                    connection=opened,
                )
        self.require_project(project_id, connection=connection)
        row = connection.execute(
            "SELECT id, text, version FROM requirements WHERE id=? AND project_id=?",
            (requirement_id, project_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "项目下没有这条需求")
        if expected_version is not None and row["version"] != expected_version:
            raise HTTPException(409, "需求版本已变更，请复核关联用例")
        return dict(row)

    def update_requirement(self, project_id: str, requirement_id: str, text: str) -> dict:
        with self.database.connection(write=True) as connection:
            current = self.get_requirement(project_id, requirement_id, connection=connection)
            version = current["version"] + 1
            connection.execute(
                "UPDATE requirements SET text=?, version=? WHERE id=? AND project_id=?",
                (text, version, requirement_id, project_id),
            )
            connection.execute(
                "INSERT INTO requirement_revisions VALUES (?, ?, ?)",
                (requirement_id, version, text),
            )
        return {"id": requirement_id, "text": text, "version": version}

    def get_requirement_version(self, project_id: str, requirement_id: str, version: int) -> dict:
        """Historical source for internal snapshots; still checks project ownership."""
        with self.database.connection() as connection:
            self.get_requirement(project_id, requirement_id, connection=connection)
            row = connection.execute(
                "SELECT text, version FROM requirement_revisions WHERE requirement_id=? AND version=?",
                (requirement_id, version),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "需求历史版本不存在")
            return {"id": requirement_id, **dict(row)}

    def load_text(self, project_id: str, requirement_id: str) -> str | None:
        """Agent build_router(load_text) adapter: absent/foreign IDs return None."""
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT text FROM requirements WHERE id=? AND project_id=?",
                (requirement_id, project_id),
            ).fetchone()
            return None if row is None else row["text"]

    def list_endpoints(self, project_id: str) -> list[dict]:
        with self.database.connection() as connection:
            self.require_project(project_id, connection=connection)
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT id, method, path, version FROM endpoints WHERE project_id=? ORDER BY rowid",
                    (project_id,),
                )
            ]

    def create_endpoint(self, project_id: str, method: str, path: str) -> dict:
        endpoint_id = str(uuid4())
        with self.database.connection(write=True) as connection:
            self.require_project(project_id, connection=connection)
            connection.execute(
                "INSERT INTO endpoints(id, project_id, method, path, version) VALUES (?, ?, ?, ?, 1)",
                (endpoint_id, project_id, method, path),
            )
        return {"id": endpoint_id, "method": method, "path": path, "version": 1}

    def get_endpoint(
        self,
        project_id: str,
        endpoint_id: str,
        *,
        expected_version: int | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict:
        if connection is None:
            with self.database.connection() as opened:
                return self.get_endpoint(
                    project_id,
                    endpoint_id,
                    expected_version=expected_version,
                    connection=opened,
                )
        self.require_project(project_id, connection=connection)
        row = connection.execute(
            "SELECT id, method, path, version FROM endpoints WHERE id=? AND project_id=?",
            (endpoint_id, project_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "项目下没有这个接口")
        if expected_version is not None and row["version"] != expected_version:
            raise HTTPException(409, "接口版本不匹配，请复核关联用例")
        return dict(row)

    def get_environment(self, project_id: str) -> dict:
        with self.database.connection() as connection:
            self.require_project(project_id, connection=connection)
            row = connection.execute(
                "SELECT target, secrets_json FROM environments WHERE project_id=?", (project_id,)
            ).fetchone()
            return {
                "target": "demo",
                "configured_keys": [] if row is None else sorted(json.loads(row["secrets_json"])),
            }

    def put_environment(self, project_id: str, target: str, secrets: dict[str, str]) -> dict:
        with self.database.connection(write=True) as connection:
            self.require_project(project_id, connection=connection)
            connection.execute(
                "INSERT INTO environments(project_id, target, secrets_json) VALUES (?, ?, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET "
                "target=excluded.target, secrets_json=excluded.secrets_json",
                (project_id, target, json.dumps(secrets, ensure_ascii=False)),
            )
        return {"target": target, "configured_keys": sorted(secrets)}

    def read_environment(self, project_id: str, target: str = "demo") -> dict[str, str]:
        """Internal executor adapter. NEVER expose this mapping in an HTTP response."""
        with self.database.connection() as connection:
            self.require_project(project_id, connection=connection)
            if target != "demo":
                raise HTTPException(422, "不支持的执行目标")
            row = connection.execute(
                "SELECT secrets_json FROM environments WHERE project_id=? AND target=?",
                (project_id, target),
            ).fetchone()
            if row is None:
                raise HTTPException(422, "尚未配置演示环境")
            return json.loads(row["secrets_json"])
