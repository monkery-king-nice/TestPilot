from fastapi.testclient import TestClient

from app.modules.runs.app_factory import create_runs_app

from .conftest import FakeDependencies, case_snapshot, login_step, me_step


def execute(client, service, case_id):
    response = client.post(
        "/api/projects/project-1/runs", json={"cases": [{"id": case_id, "version": 1}]}
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    assert response.json() == {"run_id": run_id, "status": "QUEUED"}
    service.execute_run(run_id)
    detail = client.get(f"/api/projects/project-1/runs/{run_id}")
    assert detail.status_code == 200, detail.text
    return run_id, detail.json()


def test_real_demo_success_and_frozen_snapshot(demo_server, service_factory):
    case = case_snapshot("case-pass", "登录后获取本人信息", [login_step(), me_step()])
    dependencies = FakeDependencies([case])
    service = service_factory(dependencies, base_url=demo_server)
    with TestClient(create_runs_app(service)) as client:
        run_id, detail = execute(client, service, "case-pass")
        assert detail["status"] == "COMPLETED"
        assert detail["counts"] == {"PASS": 1, "FAIL": 0, "ERROR": 0, "BLOCKED": 0}
        assert detail["results"][0]["outcome"] == "PASS"
        assert all(step["http_status"] == 200 for step in detail["results"][0]["steps"])
        persisted = str(detail) + str(service.get_frozen_snapshot("project-1", run_id))
        assert "local-demo-only" not in persisted
        assert "[REDACTED]" in persisted


def test_real_demo_business_assertion_fail(demo_server, service_factory):
    case = case_snapshot("case-fail", "本人编号不符合预期", [login_step(), me_step("another-user")])
    service = service_factory(FakeDependencies([case]), base_url=demo_server)
    with TestClient(create_runs_app(service)) as client:
        _, detail = execute(client, service, "case-fail")
        assert detail["counts"]["FAIL"] == 1
        step = detail["results"][0]["steps"][1]
        assert step["http_status"] == 200
        assert step["error_stage"] == "assertion"
        assert any("another-user" in diff for diff in step["assertion_diffs"])


def test_real_demo_setup_failure_blocks_main_step(demo_server, service_factory):
    case = case_snapshot("case-blocked", "准备失败", [login_step(), me_step()])
    dependencies = FakeDependencies(
        [case], environment={"username": "demo-user", "password": "wrong-password"}
    )
    service = service_factory(dependencies, base_url=demo_server)
    with TestClient(create_runs_app(service)) as client:
        _, detail = execute(client, service, "case-blocked")
        result = detail["results"][0]
        assert detail["counts"]["BLOCKED"] == 1
        assert result["outcome"] == "BLOCKED"
        assert result["steps"][0]["http_status"] == 401
        assert result["steps"][1]["http_status"] is None
        assert result["steps"][1]["error_stage"] == "setup_failed"


def test_real_demo_wrong_password_expected_401_passes(demo_server, service_factory):
    case = case_snapshot(
        "case-invalid-login", "错误密码返回约定错误", [login_step(phase="test", expected=401, extract=False)]
    )
    dependencies = FakeDependencies(
        [case], environment={"username": "demo-user", "password": "wrong-password"}
    )
    service = service_factory(dependencies, base_url=demo_server)
    with TestClient(create_runs_app(service)) as client:
        _, detail = execute(client, service, "case-invalid-login")
        assert detail["counts"]["PASS"] == 1
        assert detail["results"][0]["steps"][0]["http_status"] == 401


def test_unconfirmed_case_rejects_whole_batch_without_request(service_factory):
    unconfirmed = case_snapshot("case-draft", "未确认", [login_step()], status="DRAFT")
    confirmed = case_snapshot("case-ready", "已确认", [login_step()])
    dependencies = FakeDependencies([unconfirmed, confirmed])
    service = service_factory(dependencies)
    with TestClient(create_runs_app(service)) as client:
        response = client.post(
            "/api/projects/project-1/runs",
            json={"cases": [{"id": "case-ready", "version": 1}, {"id": "case-draft", "version": 1}]},
        )
        assert response.status_code == 422
        assert "尚未确认" in response.json()["detail"]
        # No run was created and no executor/background request was scheduled.
        assert not service._futures


def test_cross_project_run_read_is_404(demo_server, service_factory):
    case = case_snapshot("case-pass", "登录后获取本人信息", [login_step(), me_step()])
    service = service_factory(FakeDependencies([case]), base_url=demo_server)
    with TestClient(create_runs_app(service)) as client:
        run_id, _ = execute(client, service, "case-pass")
        response = client.get(f"/api/projects/another-project/runs/{run_id}")
        assert response.status_code == 404

def test_create_run_rejects_changed_environment_version(service_factory):
    case = case_snapshot("case-pass", "登录后获取本人信息", [login_step(), me_step()])
    dependencies = FakeDependencies(
        [case],
        execution_target={
            "target": "demo",
            "service_id": "demo",
            "base_url": None,
            "environment_version": 2,
        },
    )
    service = service_factory(dependencies)
    with TestClient(create_runs_app(service)) as client:
        response = client.post(
            "/api/projects/project-1/runs",
            json={"cases": [{"id": "case-pass", "version": 1}], "environment_version": 1},
        )
        assert response.status_code == 409
        assert "环境已变更" in response.json()["detail"]
        assert not service._futures


def test_create_run_accepts_matching_environment_version(demo_server, service_factory):
    case = case_snapshot("case-pass", "登录后获取本人信息", [login_step(), me_step()])
    dependencies = FakeDependencies(
        [case],
        execution_target={
            "target": "demo",
            "service_id": "demo",
            "base_url": None,
            "environment_version": 2,
        },
    )
    service = service_factory(dependencies, base_url=demo_server)
    with TestClient(create_runs_app(service)) as client:
        response = client.post(
            "/api/projects/project-1/runs",
            json={"cases": [{"id": "case-pass", "version": 1}], "environment_version": 2},
        )
        assert response.status_code == 202, response.text