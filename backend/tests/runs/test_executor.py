import threading

import httpx
from fastapi.testclient import TestClient

from app.modules.runs.app_factory import create_runs_app
from app.modules.runs.models import CaseRef

from .conftest import FakeDependencies, case_snapshot, login_step, me_step


def slow_step():
    return {
        "name": "slow",
        "phase": "test",
        "endpoint_id": "ep-slow",
        "endpoint_version": 1,
        "headers": {},
        "body": None,
        "assertions": [{"type": "status", "expected": 200}],
        "extract": {},
    }


def test_timeout_becomes_error_with_evidence(service_factory):
    def timeout(request):
        raise httpx.ConnectTimeout("fixture timeout", request=request)

    case = case_snapshot("case-timeout", "超时", [slow_step()])
    service = service_factory(
        FakeDependencies([case]), transport=httpx.MockTransport(timeout), timeout=0.02
    )
    with TestClient(create_runs_app(service)) as client:
        response = client.post(
            "/api/projects/project-1/runs", json={"cases": [{"id": "case-timeout", "version": 1}]}
        )
        run_id = response.json()["run_id"]
        service.execute_run(run_id)
        detail = client.get(f"/api/projects/project-1/runs/{run_id}").json()
    assert detail["counts"] == {"PASS": 0, "FAIL": 0, "ERROR": 1, "BLOCKED": 0}
    step = detail["results"][0]["steps"][0]
    assert step["error_stage"] == "timeout"
    assert step["http_status"] is None
    assert "超时" in step["response_summary"]


def test_redirect_is_not_followed(service_factory):
    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "http://example.com/steal"})

    case = case_snapshot("case-redirect", "禁止自动跳转", [slow_step()])
    service = service_factory(FakeDependencies([case]), transport=httpx.MockTransport(redirect))
    run_id = service.create_run("project-1", [CaseRef(id="case-redirect", version=1)])
    service.execute_run(run_id)
    detail = service.get_run("project-1", run_id)
    assert detail.counts.FAIL == 1
    assert detail.results[0].steps[0].http_status == 302
    assert len(requests) == 1


def test_snapshot_survives_later_case_edit(demo_server, service_factory):
    from app.modules.runs.models import CaseRef

    case = case_snapshot("case-frozen", "冻结快照", [login_step(), me_step()])
    dependencies = FakeDependencies([case])
    service = service_factory(dependencies, base_url=demo_server)
    run_id = service.create_run("project-1", [CaseRef(id="case-frozen", version=1)])
    dependencies.snapshots["case-frozen"]["endpoints"]["ep-me"]["path"] = "/not-me"
    dependencies.snapshots["case-frozen"]["title"] = "修改后的标题"
    service.execute_run(run_id)
    detail = service.get_run("project-1", run_id)
    frozen = service.get_frozen_snapshot("project-1", run_id)
    assert detail.counts.PASS == 1
    assert detail.results[0].title == "冻结快照"
    assert frozen["cases"][0]["endpoints"]["ep-me"]["path"] == "/me"


def test_only_one_active_batch_is_allowed(service_factory):
    entered = threading.Event()
    release = threading.Event()

    def blocking(request):
        entered.set()
        assert release.wait(3)
        return httpx.Response(200, json={"token": "fixture-token"})

    case = case_snapshot("case-mutex", "互斥", [login_step(phase="test")])
    service = service_factory(
        FakeDependencies([case]), background=True, transport=httpx.MockTransport(blocking)
    )
    with TestClient(create_runs_app(service)) as client:
        first = client.post(
            "/api/projects/project-1/runs", json={"cases": [{"id": "case-mutex", "version": 1}]}
        )
        assert first.status_code == 202
        assert entered.wait(2)
        second = client.post(
            "/api/projects/project-1/runs", json={"cases": [{"id": "case-mutex", "version": 1}]}
        )
        assert second.status_code == 409
        release.set()
        service.wait_for_idle()
        detail = client.get(f"/api/projects/project-1/runs/{first.json()['run_id']}").json()
        assert detail["counts"]["PASS"] == 1
