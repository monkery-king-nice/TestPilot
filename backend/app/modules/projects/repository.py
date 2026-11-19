"""Project-scoped data access, also used internally by Agent/cases/executor."""

import json
import sqlite3
from uuid import uuid4

from fastapi import HTTPException

from ...core.database import Database
from .archives import inspect_archive, preview_text
from .models import RequirementSource

ENVIRONMENTS_TABLE = """CREATE TABLE IF NOT EXISTS environments (
    project_id TEXT PRIMARY KEY REFERENCES projects(id),
    target TEXT NOT NULL CHECK(target IN ('demo', 'local')),
    service_id TEXT, base_url TEXT, secrets_json TEXT NOT NULL,
    environment_version INTEGER NOT NULL DEFAULT 1)"""

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
    ENVIRONMENTS_TABLE,
    """CREATE TABLE IF NOT EXISTS project_imports (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
        filename TEXT NOT NULL, archive BLOB NOT NULL, manifest TEXT NOT NULL,
        UNIQUE (project_id, id))""",
    """CREATE TABLE IF NOT EXISTS requirement_import_sources (
        requirement_id TEXT PRIMARY KEY REFERENCES requirements(id),
        project_id TEXT NOT NULL, import_id TEXT NOT NULL, path TEXT NOT NULL,
        start INTEGER NOT NULL, end INTEGER NOT NULL,
        FOREIGN KEY (project_id, import_id) REFERENCES project_imports(project_id, id))""",
    """CREATE TABLE IF NOT EXISTS project_import_endpoints (
        import_id TEXT NOT NULL REFERENCES project_imports(id),
        candidate_id TEXT NOT NULL, endpoint_id TEXT NOT NULL REFERENCES endpoints(id),
        PRIMARY KEY (import_id, candidate_id))""",
)


class ProjectRepository:
    def __init__(self, database: Database):
        self.database = database

    def initialize(self) -> None:
        with self.database.connection(write=True) as connection:
            for statement in SCHEMA:
                connection.execute(statement)
            self._migrate_environments(connection)

    @staticmethod
    def _migrate_environments(connection) -> None:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='environments'"
        ).fetchone()
        if row and "CHECK(target = 'demo')" in row["sql"]:
            connection.execute("ALTER TABLE environments RENAME TO environments_demo_legacy")
            connection.execute(ENVIRONMENTS_TABLE)
            connection.execute(
                "INSERT INTO environments(project_id, target, service_id, base_url, secrets_json) "
                "SELECT project_id, target, 'demo', NULL, secrets_json "
                "FROM environments_demo_legacy"
            )
            connection.execute("DROP TABLE environments_demo_legacy")
        columns = {
            item["name"] for item in connection.execute("PRAGMA table_info(environments)")
        }
        if "service_id" not in columns:
            connection.execute("ALTER TABLE environments ADD COLUMN service_id TEXT")
        if "base_url" not in columns:
            connection.execute("ALTER TABLE environments ADD COLUMN base_url TEXT")
        if "environment_version" not in columns:
            connection.execute(
                "ALTER TABLE environments ADD COLUMN environment_version "
                "INTEGER NOT NULL DEFAULT 1"
            )
        connection.execute(
            "UPDATE environments SET service_id='demo' "
            "WHERE target='demo' AND service_id IS NULL"
        )

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
                self._requirement_with_source(row)
                for row in connection.execute(
                    """SELECT r.id, r.text, r.version, s.import_id, s.path, s.start, s.end
                       FROM requirements AS r LEFT JOIN requirement_import_sources AS s
                       ON s.requirement_id = r.id AND s.project_id = r.project_id
                       WHERE r.project_id = ? ORDER BY r.rowid""",
                    (project_id,),
                )
            ]

    @staticmethod
    def _requirement_with_source(row: sqlite3.Row) -> dict:
        item = {key: row[key] for key in ("id", "text", "version")}
        if row["import_id"] is not None:
            item["source"] = {key: row[key] for key in ("import_id", "path", "start", "end")}
        return item

    def create_requirement(
        self, project_id: str, text: str, source: RequirementSource | None = None
    ) -> dict:
        if source is not None:
            self.preview_import_document(
                project_id, source.import_id, source.path, source.start, source.end
            )
        requirement_id = str(uuid4())
        result = {"id": requirement_id, "text": text, "version": 1}
        with self.database.connection(write=True) as connection:
            self.require_project(project_id, connection=connection)
            connection.execute(
                "INSERT INTO requirements(id, project_id, text, version) VALUES (?, ?, ?, 1)",
                (requirement_id, project_id, text),
            )
            connection.execute(
                "INSERT INTO requirement_revisions VALUES (?, 1, ?)", (requirement_id, text)
            )
            if source is not None:
                connection.execute(
                    """INSERT INTO requirement_import_sources
                       (requirement_id, project_id, import_id, path, start, end)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        requirement_id,
                        project_id,
                        source.import_id,
                        source.path,
                        source.start,
                        source.end,
                    ),
                )
                result["source"] = source.model_dump()
        return result

    def _requirement_source(self, connection, project_id: str, requirement_id: str):
        row = connection.execute(
            """SELECT import_id, path, start, end FROM requirement_import_sources
               WHERE project_id = ? AND requirement_id = ?""",
            (project_id, requirement_id),
        ).fetchone()
        return dict(row) if row else None

    def get_requirement_source(self, project_id: str, requirement_id: str) -> dict | None:
        """Selected provenance for the Agent adapter. Manual requirements have no ZIP source."""
        with self.database.connection() as connection:
            self.get_requirement(project_id, requirement_id, connection=connection)
            return self._requirement_source(connection, project_id, requirement_id)

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
            source = self._requirement_source(connection, project_id, requirement_id)
        result = {"id": requirement_id, "text": text, "version": version}
        if source is not None:
            result["source"] = source
        return result

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
        with self.database.connection(write=True) as connection:
            self.require_project(project_id, connection=connection)
            return self._insert_endpoint(connection, project_id, method, path)

    def _insert_endpoint(self, connection, project_id: str, method: str, path: str) -> dict:
        endpoint_id = str(uuid4())
        connection.execute(
            "INSERT INTO endpoints(id, project_id, method, path, version) VALUES (?, ?, ?, ?, 1)",
            (endpoint_id, project_id, method, path),
        )
        return {"id": endpoint_id, "method": method, "path": path, "version": 1}

    def create_import(self, project_id: str, filename: str, archive: bytes) -> dict:
        manifest = inspect_archive(archive)
        import_id = str(uuid4())
        with self.database.connection(write=True) as connection:
            self.require_project(project_id, connection=connection)
            connection.execute(
                "INSERT INTO project_imports(id, project_id, filename, archive, manifest) VALUES (?, ?, ?, ?, ?)",
                (
                    import_id,
                    project_id,
                    filename,
                    archive,
                    json.dumps(manifest, ensure_ascii=False),
                ),
            )
        return {
            "id": import_id,
            "project_id": project_id,
            "filename": filename,
            **manifest,
            "confirmed_endpoints": [],
        }

    def _import_row(self, connection, project_id: str, import_id: str):
        row = connection.execute(
            "SELECT id, project_id, filename, manifest FROM project_imports WHERE project_id = ? AND id = ?",
            (project_id, import_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "当前项目中找不到该导入记录")
        return row

    def get_import(self, project_id: str, import_id: str) -> dict:
        with self.database.connection() as connection:
            row = dict(self._import_row(connection, project_id, import_id))
            confirmed = connection.execute(
                """SELECT c.candidate_id, e.id, e.method, e.path, e.version
                   FROM project_import_endpoints AS c JOIN endpoints AS e ON e.id = c.endpoint_id
                   WHERE c.import_id = ? AND e.project_id = ? ORDER BY c.rowid""",
                (import_id, project_id),
            )
            result = []
            for record in confirmed:
                endpoint = dict(record)
                result.append({"candidate_id": endpoint.pop("candidate_id"), "endpoint": endpoint})
            return {**json.loads(row.pop("manifest")), **row, "confirmed_endpoints": result}

    def preview_import_document(
        self, project_id: str, import_id: str, path: str, start: int = 0, end: int | None = None
    ) -> dict:
        with self.database.connection() as connection:
            row = self._import_row(connection, project_id, import_id)
            if not any(doc["path"] == path for doc in json.loads(row["manifest"])["documents"]):
                raise HTTPException(404, "导入记录中没有这个可预览的文档")
            archive = connection.execute(
                "SELECT archive FROM project_imports WHERE project_id = ? AND id = ?",
                (project_id, import_id),
            ).fetchone()["archive"]
        return {"import_id": import_id, **preview_text(archive, path, start, end)}

    def confirm_import_endpoints(self, project_id: str, import_id: str, candidate_ids: list[str]):
        with self.database.connection(write=True) as connection:
            row = self._import_row(connection, project_id, import_id)
            candidates = {
                item["candidate_id"]: item
                for item in json.loads(row["manifest"])["endpoint_candidates"]
            }
            selected = []
            for candidate_id in dict.fromkeys(candidate_ids):
                candidate = candidates.get(candidate_id)
                if candidate is None:
                    raise HTTPException(422, "选择包含当前导入中不存在的接口")
                if candidate["requires_manual_registration"]:
                    raise HTTPException(
                        422, "所选接口包含模板或查询参数，请填写实际相对路径并手工登记"
                    )
                selected.append(candidate)
            results = []
            for candidate in selected:
                candidate_id = candidate["candidate_id"]
                method, path = candidate["method"], candidate["path"]
                found = connection.execute(
                    """SELECT id, method, path, version FROM endpoints
                       WHERE project_id = ? AND method = ? AND path = ? ORDER BY rowid LIMIT 1""",
                    (project_id, method, path),
                ).fetchone()
                endpoint = (
                    dict(found)
                    if found
                    else self._insert_endpoint(connection, project_id, method, path)
                )
                connection.execute(
                    """INSERT INTO project_import_endpoints(import_id, candidate_id, endpoint_id)
                       VALUES (?, ?, ?) ON CONFLICT(import_id, candidate_id) DO NOTHING""",
                    (import_id, candidate_id, endpoint["id"]),
                )
                results.append({"candidate_id": candidate_id, "endpoint": endpoint})
        return {"project_id": project_id, "import_id": import_id, "endpoints": results}

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
                "SELECT target, service_id, base_url, secrets_json, environment_version "
                "FROM environments WHERE project_id=?",
                (project_id,),
            ).fetchone()
            return {
                "target": "demo" if row is None else row["target"],
                "service_id": None if row is None else row["service_id"],
                "base_url": None if row is None else row["base_url"],
                "environment_version": None if row is None else row["environment_version"],
                "configured_keys": [] if row is None else sorted(json.loads(row["secrets_json"])),
            }

    def put_environment(
        self,
        project_id: str,
        target: str,
        secrets: dict[str, str],
        service_id: str | None = None,
        base_url: str | None = None,
    ) -> dict:
        service_id = "demo" if target == "demo" else service_id
        with self.database.connection(write=True) as connection:
            self.require_project(project_id, connection=connection)
            connection.execute(
                "INSERT INTO environments(project_id, target, service_id, base_url, "
                "secrets_json, environment_version) VALUES (?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(project_id) DO UPDATE SET "
                "target=excluded.target, service_id=excluded.service_id, "
                "base_url=excluded.base_url, secrets_json=excluded.secrets_json, "
                "environment_version=environments.environment_version+1",
                (project_id, target, service_id, base_url, json.dumps(secrets, ensure_ascii=False)),
            )
            environment_version = connection.execute(
                "SELECT environment_version FROM environments WHERE project_id=?",
                (project_id,),
            ).fetchone()[0]
        return {
            "target": target,
            "service_id": service_id,
            "base_url": base_url,
            "environment_version": environment_version,
            "configured_keys": sorted(secrets),
        }

    def read_execution_target(self, project_id: str) -> dict:
        """Return only public target metadata; secrets use read_environment()."""
        with self.database.connection() as connection:
            self.require_project(project_id, connection=connection)
            row = connection.execute(
                "SELECT target, service_id, base_url, environment_version "
                "FROM environments WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(422, "尚未配置项目测试环境，不能回退到默认演示服务")
            return dict(row)

    def read_environment(
        self,
        project_id: str,
        target: str = "demo",
        expected_version: int | None = None,
    ) -> dict[str, str]:
        """Atomically validate target/version and read internal secrets."""
        if target not in {"demo", "local"}:
            raise HTTPException(422, "不支持的执行目标")
        with self.database.connection() as connection:
            self.require_project(project_id, connection=connection)
            row = connection.execute(
                "SELECT target, secrets_json, environment_version "
                "FROM environments WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(422, f"项目尚未配置 {target} 测试环境")
            if expected_version is not None and (
                row["target"] != target or row["environment_version"] != expected_version
            ):
                raise HTTPException(409, "项目测试环境已变更，请重新预检并创建运行批次")
            if row["target"] != target:
                raise HTTPException(422, f"项目尚未配置 {target} 测试环境")
            return json.loads(row["secrets_json"])
