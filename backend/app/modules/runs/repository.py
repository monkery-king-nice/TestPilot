"""SQLite persistence for frozen runs and append-only execution evidence."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CaseResult, Counts, RunDetail, StepResult


class RunConflict(Exception):
    pass


class RunNotFound(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class RunRepository:
    """Owns only runs tables; each operation uses a short SQLite transaction."""

    def __init__(self, database: str | Path):
        self.database = str(database)
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total INTEGER NOT NULL,
                    counts_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runs_active_idx ON runs(status);
                CREATE TABLE IF NOT EXISTS run_cases (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    case_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    result_json TEXT,
                    PRIMARY KEY (run_id, case_id),
                    UNIQUE (run_id, position)
                );
                CREATE TABLE IF NOT EXISTS run_steps (
                    run_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    result_json TEXT,
                    PRIMARY KEY (run_id, case_id, step_index),
                    FOREIGN KEY (run_id, case_id)
                        REFERENCES run_cases(run_id, case_id)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def create_run(self, project_id: str, snapshots: list[dict]) -> str:
        run_id = str(uuid.uuid4())
        now = _now()
        counts = Counts().model_dump()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                active = connection.execute(
                    "SELECT 1 FROM runs WHERE status IN ('QUEUED', 'RUNNING') LIMIT 1"
                ).fetchone()
                if active:
                    raise RunConflict("已有运行批次正在排队或执行，请等待其结束")
                connection.execute(
                    "INSERT INTO runs VALUES (?, ?, 'QUEUED', ?, ?, ?, ?)",
                    (run_id, project_id, len(snapshots), _json(counts), now, now),
                )
                for position, snapshot in enumerate(snapshots):
                    case_id = snapshot["case_id"]
                    connection.execute(
                        "INSERT INTO run_cases "
                        "(run_id, case_id, position, title, snapshot_json) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (run_id, case_id, position, snapshot["title"], _json(snapshot)),
                    )
                    for index, _step in enumerate(snapshot["steps"]):
                        connection.execute(
                            "INSERT INTO run_steps (run_id, case_id, step_index, state) "
                            "VALUES (?, ?, ?, 'PENDING')",
                            (run_id, case_id, index),
                        )
        except sqlite3.IntegrityError as error:
            raise ValueError("运行快照包含重复用例或无效步骤") from error
        return run_id

    def mark_running(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status='RUNNING', updated_at=? "
                "WHERE run_id=? AND status='QUEUED'",
                (_now(), run_id),
            )

    def mark_step_sent(self, run_id: str, case_id: str, index: int) -> None:
        """Persist intent before I/O so restart recovery never resends blindly."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE run_steps SET state='SENT' WHERE run_id=? AND case_id=? "
                "AND step_index=? AND state='PENDING'",
                (run_id, case_id, index),
            )

    def save_step_result(
        self, run_id: str, case_id: str, index: int, result: StepResult
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE run_steps SET state='COMPLETED', result_json=? "
                "WHERE run_id=? AND case_id=? AND step_index=?",
                (_json(result.model_dump()), run_id, case_id, index),
            )

    def save_case_result(self, run_id: str, result: CaseResult) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE run_cases SET result_json=? WHERE run_id=? AND case_id=?",
                (_json(result.model_dump()), run_id, result.case_id),
            )
            for index, step in enumerate(result.steps):
                connection.execute(
                    "UPDATE run_steps SET state='COMPLETED', result_json=? "
                    "WHERE run_id=? AND case_id=? AND step_index=?",
                    (_json(step.model_dump()), run_id, result.case_id, index),
                )
            self._update_counts(connection, run_id)

    def complete_run(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._update_counts(connection, run_id)
            connection.execute(
                "UPDATE runs SET status='COMPLETED', updated_at=? WHERE run_id=?",
                (_now(), run_id),
            )

    def _update_counts(self, connection: sqlite3.Connection, run_id: str) -> None:
        counts = {key: 0 for key in ("PASS", "FAIL", "ERROR", "BLOCKED")}
        rows = connection.execute(
            "SELECT result_json FROM run_cases WHERE run_id=? AND result_json IS NOT NULL",
            (run_id,),
        ).fetchall()
        for row in rows:
            counts[json.loads(row["result_json"])["outcome"]] += 1
        connection.execute(
            "UPDATE runs SET counts_json=?, updated_at=? WHERE run_id=?",
            (_json(counts), _now(), run_id),
        )

    def get_detail(self, project_id: str, run_id: str) -> RunDetail:
        with self._connect() as connection:
            run = connection.execute(
                "SELECT * FROM runs WHERE run_id=? AND project_id=?", (run_id, project_id)
            ).fetchone()
            if not run:
                raise RunNotFound("运行批次不存在")
            rows = connection.execute(
                "SELECT result_json FROM run_cases "
                "WHERE run_id=? AND result_json IS NOT NULL ORDER BY position",
                (run_id,),
            ).fetchall()
        return RunDetail(
            run_id=run_id,
            status=run["status"],
            counts=Counts(**json.loads(run["counts_json"])),
            results=[CaseResult(**json.loads(row["result_json"])) for row in rows],
        )

    def get_frozen_snapshot(self, project_id: str, run_id: str) -> dict:
        """Internal read API for reports/analysis; contains no environment values."""
        with self._connect() as connection:
            run = connection.execute(
                "SELECT * FROM runs WHERE run_id=? AND project_id=?", (run_id, project_id)
            ).fetchone()
            if not run:
                raise RunNotFound("运行批次不存在")
            rows = connection.execute(
                "SELECT snapshot_json FROM run_cases WHERE run_id=? ORDER BY position",
                (run_id,),
            ).fetchall()
        return {
            "run_id": run_id,
            "project_id": project_id,
            "status": run["status"],
            "cases": [json.loads(row["snapshot_json"]) for row in rows],
        }

    def get_snapshots_for_execution(self, run_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT snapshot_json FROM run_cases WHERE run_id=? ORDER BY position",
                (run_id,),
            ).fetchall()
        if not rows:
            raise RunNotFound("运行批次不存在")
        return [json.loads(row["snapshot_json"]) for row in rows]

    def recover_interrupted(self) -> list[str]:
        """Finish abandoned local runs without issuing any target requests."""
        with self._connect() as connection:
            run_ids = [
                row["run_id"]
                for row in connection.execute(
                    "SELECT run_id FROM runs WHERE status IN ('QUEUED', 'RUNNING')"
                ).fetchall()
            ]
        for run_id in run_ids:
            self._recover_one(run_id)
        return run_ids

    def _recover_one(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cases = connection.execute(
                "SELECT * FROM run_cases WHERE run_id=? ORDER BY POSITION", (run_id,)
            ).fetchall()
            counts = {key: 0 for key in ("PASS", "FAIL", "ERROR", "BLOCKED")}
            for case in cases:
                if case["result_json"]:
                    result = CaseResult(**json.loads(case["result_json"]))
                    counts[result.outcome] += 1
                    continue
                snapshot = json.loads(case["snapshot_json"])
                step_rows = connection.execute(
                    "SELECT * FROM run_steps WHERE run_id=? AND case_id=? "
                    "ORDER BY step_index",
                    (run_id, case["case_id"]),
                ).fetchall()
                steps: list[StepResult] = []
                unknown = False
                for index, (step, row) in enumerate(zip(snapshot["steps"], step_rows)):
                    if row["result_json"]:
                        steps.append(StepResult(**json.loads(row["result_json"])))
                        continue
                    if row["state"] == "SENT":
                        unknown = True
                        result = StepResult(
                            name=step["name"],
                            phase=step["phase"],
                            assertion_diffs=[],
                            error_stage="interrupted",
                            response_summary="进程中断时已发出请求，结果未知；未重发",
                        )
                    else:
                        result = StepResult(
                            name=step["name"],
                            phase=step["phase"],
                            assertion_diffs=[],
                            error_stage="not_started",
                            response_summary="进程中断前未开始，已标记为 BLOCKED",
                        )
                    steps.append(result)
                    connection.execute(
                        "UPDATE run_steps SET state='COMPLETED', result_json=? "
                        "WHERE run_id=? AND case_id=? AND step_index=?",
                        (_json(result.model_dump()), run_id, case["case_id"], index),
                    )
                case_result = CaseResult(
                    case_id=case["case_id"],
                    title=case["title"],
                    outcome="ERROR" if unknown else "BLOCKED",
                    steps=steps,
                )
                counts[case_result.outcome] += 1
                connection.execute(
                    "UPDATE run_cases SET result_json=? WHERE run_id=? AND case_id=?",
                    (_json(case_result.model_dump()), run_id, case["case_id"]),
                )
            connection.execute(
                "UPDATE runs SET status='INTERRUPTED', counts_json=?, updated_at=? "
                "WHERE run_id=?",
                (_json(counts), _now(), run_id),
            )
