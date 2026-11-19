import copy
import json
from html import unescape

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.modules.runs.dependencies import PreflightRejected
from backend.app.modules.runs.models import CaseRef

from .conftest import create_context, run_cases, save


def test_download_masks_sensitive_assertion_values_in_new_and_historical_runs(client):
    base, draft = create_context(client)
    marker = "FICTIONAL_PRIVATE_MARKER"
    service = client.app.state.run_service
    service.transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "token": f"{marker}_ACTUAL_TOKEN",
        "auth": {"password": f"{marker}_ACTUAL_PASSWORD"},
        "user": {"id": "ordinary-actual-id"},
    }))
    step = draft["steps"][1]
    step["headers"] = {}
    step["assertions"] = [
        {"type": "json_equals", "path": "token", "expected": f"{marker}_EXPECTED_TOKEN"},
        {"type": "json_equals", "path": "auth.password",
         "expected": f"{marker}_EXPECTED_PASSWORD"},
        {"type": "json_equals", "path": "user.id", "expected": "ordinary-expected-id"},
    ]
    draft["steps"] = [step]
    case = save(client, base, draft, confirm=True)
    run_id, result = run_cases(client, base, [case])
    assert result["counts"]["FAIL"] == 1
    report_url = base + f"/runs/{run_id}/report"

    def assert_safe_download():
        response = client.get(report_url)
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        html = unescape(response.text)
        assert marker not in html
        for path in ("token", "auth.password"):
            assert f'"path": "{path}"' in html
            assert f"{path}：期望 [REDACTED]，实际 [REDACTED]" in html
        assert html.count('"expected": "[REDACTED]"') == 2
        assert "user.id：期望 'ordinary-expected-id'，实际 'ordinary-actual-id'" in html

    assert_safe_download()
    assert marker not in json.dumps(result)

    # Reproduce the evidence format persisted before path-aware redaction.
    project_id = base.rsplit("/", 1)[1]
    stored_result = service.get_run(project_id, run_id).results[0]
    stored_result.steps[0].assertion_diffs[:2] = [
        f"token：期望 '{marker}_EXPECTED_TOKEN'，实际 '{marker}_ACTUAL_TOKEN'",
        f"auth.password：期望 '{marker}_EXPECTED_PASSWORD'，实际 '{marker}_ACTUAL_PASSWORD'",
    ]
    service.repository.save_case_result(run_id, stored_result)
    assert_safe_download()


def test_saved_case_survives_restart_and_edit_requires_new_confirmation(settings):
    with TestClient(create_app(settings)) as first:
        base, draft = create_context(first)
        case = save(first, base, draft, confirm=True)
        assert case["status"] == "CONFIRMED"
        assert case["confirmed_at"]
    with TestClient(create_app(settings)) as second:
        url = base + f"/cases/{case['id']}"
        assert second.get(url).json() == case
        draft["title"] = "修改后的用例"
        updated = second.patch(url, json=draft).json()
        assert (updated["version"], updated["status"]) == (2, "NEEDS_REVIEW")
        assert second.post(url + "/confirm", json={"version": 1}).status_code == 409
        result = second.post(url + "/confirm", json={"version": 2})
        assert result.status_code == 200
        assert result.json()["confirmed_version"] == 2
        with second.app.state.database.connection() as db:
            old = db.execute("SELECT draft_json FROM case_revisions WHERE case_id=? AND version=1",
                             (case["id"],)).fetchone()
        assert json.loads(old[0])["title"] == case["title"]


@pytest.mark.parametrize("problem,expected", [
    ("assertions", "缺少断言"), ("basis", "缺少预期依据"),
    ("variable", "未由前序步骤定义"), ("environment", "未定义或未配置"),
    ("forward", "未由前序步骤定义"), ("expression", "变量必须使用"),
    ("duplicate", "步骤名重复"), ("path", "字段路径"),
    ("boolean_status", "状态码"), ("negative_time", "耗时"),
    ("unsupported", "不支持的断言类型"), ("missing_expected", "缺少字段预期值"),
    ("order", "setup 准备步骤"), ("no_test", "主测试步骤"),
    ("header", "请求头"), ("empty_steps", "1–5"),
])
def test_draft_errors_are_readable_and_block_confirmation(client, problem, expected):
    base, draft = create_context(client)
    step = draft["steps"][1]
    if problem == "assertions":
        step["assertions"] = []
    elif problem == "basis":
        draft["expected_basis"] = " "
    elif problem == "variable":
        step["headers"]["Authorization"] = "Bearer {{steps.login.missing}}"
    elif problem == "environment":
        draft["steps"][0]["body"]["username"] = "{{env.absent}}"
    elif problem == "forward":
        draft["steps"][0]["body"]["username"] = "{{steps.me.token}}"
    elif problem == "expression":
        step["body"] = {"value": "{{__import__('os')}}"}
    elif problem == "duplicate":
        step["name"] = "login"
    elif problem == "path":
        step["assertions"][1]["path"] = "$.user[0]"
    elif problem == "boolean_status":
        step["assertions"][0]["expected"] = True
    elif problem == "negative_time":
        step["assertions"][2]["expected"] = -1
    elif problem == "unsupported":
        step["assertions"][0]["type"] = "python_eval"
    elif problem == "missing_expected":
        del step["assertions"][1]["expected"]
    elif problem == "order":
        draft["steps"] = list(reversed(draft["steps"]))
    elif problem == "no_test":
        step["phase"] = "setup"
    elif problem == "header":
        step["headers"]["bad\nheader"] = "x"
    elif problem == "empty_steps":
        draft["steps"] = []
    case = save(client, base, draft)
    assert case["status"] == "NEEDS_INFO"
    assert any(expected in reason for reason in case["reasons"])
    response = client.post(base + f"/cases/{case['id']}/confirm", json={"version": 1})
    assert response.status_code == 422
    assert expected in response.json()["detail"]


def test_explicit_null_expected_is_distinct_from_missing_expected(client):
    base, draft = create_context(client)
    draft["steps"][1]["assertions"][1]["expected"] = None
    case = save(client, base, draft, confirm=True)
    assert case["status"] == "CONFIRMED"


def test_unconfirmed_and_mixed_batch_rejected_without_target_requests(client):
    base, draft = create_context(client)
    ready = save(client, base, draft)
    confirmed = save(client, base, draft, confirm=True)
    response = client.post(base + "/runs", json={"cases": [
        {"id": confirmed["id"], "version": 1}, {"id": ready["id"], "version": 1}
    ]})
    assert response.status_code == 422
    assert "尚未确认" in response.json()["detail"]
    with client.app.state.database.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_requirement_change_is_reviewed_on_read_and_execution(client):
    base, draft = create_context(client)
    case = save(client, base, draft, confirm=True)
    client.patch(base + f"/requirements/{draft['requirement_id']}", json={"text": "新的需求"})
    rejected = client.post(base + "/runs", json={"cases": [{"id": case["id"], "version": 1}]})
    assert rejected.status_code == 422
    assert "需求版本已过期" in rejected.json()["detail"]
    assert client.get(base + "/cases").json()[0]["status"] == "NEEDS_REVIEW"
    url = base + f"/cases/{case['id']}"
    assert client.post(url + "/confirm", json={"version": 1}).status_code == 409
    draft["requirement_version"] = 2
    updated = client.patch(url, json=draft).json()
    assert updated["version"] == 2
    assert client.post(url + "/confirm", json={"version": 2}).status_code == 200


def test_endpoint_change_and_environment_removal_invalidate_confirmation(client):
    base, draft = create_context(client)
    case = save(client, base, draft, confirm=True)
    # No public endpoint edit API exists yet: simulate its future version bump.
    with client.app.state.database.connection(write=True) as db:
        db.execute("UPDATE endpoints SET version=2 WHERE id=?", (draft["steps"][1]["endpoint_id"],))
    response = client.get(base + f"/cases/{case['id']}").json()
    assert response["status"] == "NEEDS_REVIEW"
    assert any("接口版本" in reason for reason in response["reasons"])
    with client.app.state.database.connection(write=True) as db:
        db.execute("UPDATE endpoints SET version=1 WHERE id=?", (draft["steps"][1]["endpoint_id"],))
        db.execute("DELETE FROM environments")
    response = client.get(base + f"/cases/{case['id']}").json()
    assert response["status"] == "NEEDS_REVIEW"
    assert any("环境变量" in reason for reason in response["reasons"])


def test_cross_project_references_and_case_operations_are_rejected(client):
    base, draft = create_context(client)
    foreign, other_draft = create_context(client)
    for field in ("requirement", "endpoint"):
        invalid = copy.deepcopy(draft)
        if field == "requirement":
            invalid["requirement_id"] = other_draft["requirement_id"]
        else:
            invalid["steps"][0]["endpoint_id"] = other_draft["steps"][0]["endpoint_id"]
        assert client.post(base + "/cases", json=invalid).status_code == 404
    case = save(client, base, draft, confirm=True)
    url = foreign + f"/cases/{case['id']}"
    assert client.get(url).status_code == 404
    assert client.patch(url, json=other_draft).status_code == 404
    assert client.post(url + "/confirm", json={"version": 1}).status_code == 404
    assert client.get(url + "/manual-checks").status_code == 404
    response = client.post(foreign + "/runs", json={"cases": [{"id": case["id"], "version": 1}]})
    assert response.status_code == 422
    assert client.get("/api/projects/missing/cases").status_code == 404


def test_preflight_preserves_order_freezes_sources_and_aggregates_reasons(client):
    base, draft = create_context(client)
    first = save(client, base, draft, confirm=True)
    second = save(client, base, draft, confirm=True)
    pid = base.split("/")[-1]
    service = client.app.state.cases_service
    snapshots = service.preflight(pid, [CaseRef(id=item["id"], version=1)
                                       for item in (second, first)])
    assert [s["case_id"] for s in snapshots] == [second["id"], first["id"]]
    assert "正确密码" in snapshots[0]["requirement"]["text"]
    assert "case-test-only" not in json.dumps(snapshots)
    with pytest.raises(PreflightRejected) as error:
        service.preflight(pid, [CaseRef(id=first["id"], version=2), CaseRef(id="missing", version=1)])
    assert len(error.value.reasons) == 2
    for refs in ([], [CaseRef(id=first["id"], version=1)] * 2):
        with pytest.raises(PreflightRejected):
            service.preflight(pid, refs)


def test_manual_checks_are_evidenced_versioned_and_separate_from_runs(client):
    base, draft = create_context(client)
    case = save(client, base, draft)
    url = base + f"/cases/{case['id']}"
    payload = {"version": 1, "items": [{
        "check": "登录按钮", "pass_condition": "点击后显示结果", "outcome": "PASS", "evidence": ""
    }]}
    assert client.post(url + "/manual-checks", json=payload).status_code == 422
    payload["items"][0]["evidence"] = "人工验收截图：login.png"
    response = client.post(url + "/manual-checks", json=payload)
    assert response.status_code == 201
    record = response.json()
    draft["title"] = "新版本"
    client.patch(url, json=draft)
    assert client.post(url + "/manual-checks", json=payload).status_code == 409
    assert client.get(url + "/manual-checks").json() == [record]
    assert record["case"]["title"] != "新版本"
    with client.app.state.database.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_strict_request_types_and_extra_fields(client):
    base, draft = create_context(client)
    for version in (True, "1", 0):
        draft["requirement_version"] = version
        assert client.post(base + "/cases", json=draft).status_code == 422
    draft["requirement_version"] = 1
    draft["status"] = "CONFIRMED"
    assert client.post(base + "/cases", json=draft).status_code == 422


def test_real_http_execution_and_historical_report_are_immutable(client, settings):
    base, draft = create_context(client)
    draft["title"] = '<script>alert("x")</script>中文用例'
    case = save(client, base, draft, confirm=True)
    run_id, result = run_cases(client, base, [case])
    assert result["status"] == "COMPLETED"
    assert result["counts"] == {"PASS": 1, "FAIL": 0, "ERROR": 0, "BLOCKED": 0}
    url = base + f"/runs/{run_id}/report"
    response = client.get(url)
    original = response.content
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "attachment" in response.headers["content-disposition"]
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text
    assert "case-test-only" not in response.text
    assert "[REDACTED]" in response.text
    assert "通过率：100.0%" in response.text
    draft["title"] = "新的标题"
    draft["expected_basis"] = "新依据，不应进入旧报告"
    client.patch(base + f"/cases/{case['id']}", json=draft)
    client.patch(base + f"/requirements/{draft['requirement_id']}", json={"text": "新的需求正文"})
    assert client.get(url).content == original
    # Also check the saved batch through another application process lifecycle.
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(url).content == original
    other, _ = create_context(client)
    assert client.get(other + f"/runs/{run_id}/report").status_code == 404


def test_real_fail_blocked_error_and_wrong_password_pass_are_reported(client):
    base, draft = create_context(client)
    fail = copy.deepcopy(draft)
    fail["steps"][1]["assertions"][1]["expected"] = "different-user"
    fail["expected_basis"] = "故意设置不匹配预期，验收失败证据"
    blocked = copy.deepcopy(draft)
    blocked["steps"][0]["body"]["password"] = "incorrect-fixture-password"
    error = copy.deepcopy(draft)
    error["steps"] = [error["steps"][1]]
    error["steps"][0]["headers"] = {}
    error["steps"][0]["assertions"] = [{"type": "status", "expected": 401}]
    error["steps"][0]["extract"] = {"missing": "absent"}
    negative = copy.deepcopy(draft)
    negative["steps"] = [negative["steps"][0]]
    negative["steps"][0].update({
        "phase": "test", "extract": {}, "assertions": [
            {"type": "status", "expected": 401},
            {"type": "json_equals", "path": "code", "expected": "INVALID_CREDENTIALS"}],
    })
    negative["steps"][0]["body"]["password"] = "incorrect-fixture-password"
    cases = [save(client, base, item, confirm=True) for item in (fail, blocked, error, negative)]
    run_id, result = run_cases(client, base, cases)
    assert result["counts"] == {"PASS": 1, "FAIL": 1, "ERROR": 1, "BLOCKED": 1}
    blocked_result = result["results"][1]["steps"][1]
    assert blocked_result["http_status"] is None
    assert blocked_result["error_stage"] == "setup_failed"
    report = client.get(base + f"/runs/{run_id}/report")
    assert report.status_code == 200
    assert "different-user" in report.text
    assert "断言差异" in report.text
    assert "25.0%" in report.text
    assert "incorrect-fixture-password" not in report.text


def test_queued_batch_cannot_be_downloaded_as_final_report(client):
    base, draft = create_context(client)
    case = save(client, base, draft, confirm=True)
    client.app.state.run_service.background = False
    response = client.post(base + "/runs", json={"cases": [{"id": case["id"], "version": 1}]})
    run_id = response.json()["run_id"]
    assert client.get(base + f"/runs/{run_id}/report").status_code == 409
    assert client.get(base + "/runs/missing/report").status_code == 404

def test_report_records_frozen_target(client):
    base, draft = create_context(client)
    case = save(client, base, draft, confirm=True)
    run_id, _ = run_cases(client, base, [case])
    html = client.get(base + f"/runs/{run_id}/report").text
    assert "目标：" in html
    assert "演示服务 demo" in html
    assert "环境 v1" in html