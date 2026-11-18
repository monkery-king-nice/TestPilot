from app.modules.runs.models import CaseResult, StepResult
from app.modules.runs.repository import RunRepository

from .conftest import case_snapshot, login_step, me_step


def test_restart_preserves_finished_and_marks_unknown_without_resend(tmp_path):
    database = tmp_path / "recovery.sqlite3"
    repository = RunRepository(database)
    finished = case_snapshot("case-finished", "已完成", [login_step(phase="test")])
    unknown = case_snapshot("case-unknown", "已发出但未知", [login_step(), me_step()])
    pending = case_snapshot("case-pending", "未开始", [login_step(phase="test")])
    run_id = repository.create_run("project-1", [finished, unknown, pending])
    repository.mark_running(run_id)
    completed_step = StepResult(
        name="login",
        phase="test",
        http_status=200,
        elapsed_ms=8,
        request_summary="POST /auth/login 已脱敏",
        response_summary="HTTP 200 已脱敏",
    )
    repository.save_case_result(
        run_id,
        CaseResult(case_id="case-finished", title="已完成", outcome="PASS", steps=[completed_step]),
    )
    repository.mark_step_sent(run_id, "case-unknown", 0)

    # Simulates a process crash: constructing a repository performs no target I/O.
    recovered = RunRepository(database)
    assert recovered.recover_interrupted() == [run_id]
    detail = recovered.get_detail("project-1", run_id)
    assert detail.status == "INTERRUPTED"
    assert detail.counts.model_dump() == {"PASS": 1, "FAIL": 0, "ERROR": 1, "BLOCKED": 1}
    assert detail.results[0].outcome == "PASS"
    assert detail.results[1].steps[0].error_stage == "interrupted"
    assert "未重发" in detail.results[1].steps[0].response_summary
    assert detail.results[1].steps[1].error_stage == "not_started"
    assert detail.results[2].steps[0].error_stage == "not_started"


def test_queued_batch_is_interrupted_on_startup(tmp_path):
    database = tmp_path / "queued.sqlite3"
    repository = RunRepository(database)
    case = case_snapshot("case-queued", "排队中", [login_step(phase="test")])
    run_id = repository.create_run("project-1", [case])
    RunRepository(database).recover_interrupted()
    detail = repository.get_detail("project-1", run_id)
    assert detail.status == "INTERRUPTED"
    assert detail.counts.BLOCKED == 1
    assert detail.results[0].steps[0].error_stage == "not_started"
