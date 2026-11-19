"""Real loopback HTTP evidence for project-scoped targets and frozen batches."""

import json
import secrets as secret_values
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from demo_service.server import DemoHandler, make_server, same

from .conftest import login_step, me_step
from .phase2_evidence import loopback_no_proxy, temporary_sqlite_directory


@dataclass
class LocalTarget:
    server: object
    thread: threading.Thread
    requests: list[str]
    lock: threading.Lock
    service_id: str

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def received(self):
        with self.lock:
            return self.requests.copy()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def start_target(service_id, password):
    request_log = []
    request_lock = threading.Lock()

    class TargetHandler(DemoHandler):
        def parse_request(self):
            if not super().parse_request():
                return False
            with request_lock:
                request_log.append(f"{self.command} {self.path}")
            return True

        def do_GET(self):
            if self.path != "/me":
                return self.respond(404, {"code": "NOT_FOUND"})
            if not same(
                self.headers.get("Authorization"), "Bearer " + self.server.token
            ):
                return self.respond(401, {"code": "UNAUTHORIZED"})
            return self.respond(200, {"user": {"id": self.server.user_id}})

    server = make_server(service_id, password, port=0)
    server.user_id = service_id
    server.RequestHandlerClass = TargetHandler
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return LocalTarget(server, thread, request_log, request_lock, service_id)


def call(client, method, path, payload=None, status=200):
    response = client.request(method, path, json=payload)
    assert response.status_code == status, (
        f"{method} {path}: expected {status}, got {response.status_code}: {response.text}"
    )
    return response.json()


def create_project(client, name, target=None, password=None):
    project = call(client, "POST", "/api/projects", {"name": name}, 201)
    base = f"/api/projects/{project['id']}"
    requirement = call(
        client,
        "POST",
        base + "/requirements",
        {"text": "正确登录返回非空token，查询本人返回当前服务的唯一用户标识"},
        201,
    )
    login = call(
        client,
        "POST",
        base + "/endpoints",
        {"method": "POST", "path": "/auth/login"},
        201,
    )
    me = call(
        client,
        "POST",
        base + "/endpoints",
        {"method": "GET", "path": "/me"},
        201,
    )
    if target is not None:
        call(
            client,
            "PUT",
            base + "/environment",
            {
                "target": "local",
                "service_id": target.service_id,
                "base_url": target.base_url,
                "secrets": {"username": target.service_id, "password": password},
            },
        )
    return {
        "project": project,
        "base": base,
        "requirement": requirement,
        "login": login,
        "me": me,
    }


def create_case(
    client, context, expected_user, title, authenticated=True, single_login=False
):
    if authenticated:
        login = login_step()
        login["endpoint_id"] = context["login"]["id"]
        login["endpoint_version"] = context["login"]["version"]
        if single_login:
            login["phase"] = "test"
            login["extract"] = {}
            steps = [login]
        else:
            me = me_step(expected_user)
            me["endpoint_id"] = context["me"]["id"]
            me["endpoint_version"] = context["me"]["version"]
            steps = [login, me]
    else:
        # This draft needs no environment variables, so confirmation can succeed
        # before we verify that run creation still rejects the missing target.
        steps = [
            {
                "name": "probe",
                "phase": "test",
                "endpoint_id": context["me"]["id"],
                "endpoint_version": context["me"]["version"],
                "headers": {},
                "body": None,
                "assertions": [{"type": "status", "expected": 200}],
                "extract": {},
            }
        ]
    draft = {
        "title": title,
        "requirement_id": context["requirement"]["id"],
        "requirement_version": context["requirement"]["version"],
        "expected_basis": f"本人编号应为 {expected_user}",
        "steps": steps,
    }
    case = call(client, "POST", context["base"] + "/cases", draft, 201)
    confirmed = call(
        client,
        "POST",
        context["base"] + f"/cases/{case['id']}/confirm",
        {"version": case["version"]},
    )
    assert confirmed["status"] == "CONFIRMED", confirmed
    return confirmed


def run_case(client, context, case, expected_status=202):
    accepted = call(
        client,
        "POST",
        context["base"] + "/runs",
        {"cases": [{"id": case["id"], "version": case["version"]}]},
        expected_status,
    )
    if expected_status != 202:
        return accepted
    route = context["base"] + f"/runs/{accepted['run_id']}"
    deadline = time.monotonic() + 15
    while True:
        detail = call(client, "GET", route)
        if detail["status"] in {"COMPLETED", "INTERRUPTED"}:
            return detail
        if time.monotonic() >= deadline:
            raise TimeoutError("运行批次未在15秒内结束")
        time.sleep(0.05)


def result_item(scenario, context, case, detail, requests, intentionally_induced=False):
    result = detail["results"][0]
    return {
        "scenario": scenario,
        "intentionally_induced": intentionally_induced,
        "project_id": context["project"]["id"],
        "requirement_id": context["requirement"]["id"],
        "requirement_version": context["requirement"]["version"],
        "case_id": case["id"],
        "case_version": case["version"],
        "run_id": detail["run_id"],
        "target": detail["target"],
        "outcome": result["outcome"],
        "counts": detail["counts"],
        "steps": [
            {
                "name": step["name"],
                "phase": step["phase"],
                "http_status": step["http_status"],
                "error_stage": step["error_stage"],
                "assertion_diffs": step["assertion_diffs"],
                "response_summary": step["response_summary"],
            }
            for step in result["steps"]
        ],
        "target_requests_received": requests,
    }


def verify_project_targets(output_dir: Path):
    """Run PASS/FAIL/ERROR against two live targets and one stopped target."""
    output_dir.mkdir(parents=True, exist_ok=True)
    password = secret_values.token_urlsafe(24)
    first = start_target("service-a", password)
    second = start_target("service-b", password)
    stopped = start_target("service-stopped", password)
    stopped_url = stopped.base_url
    stopped.stop()
    try:
        with loopback_no_proxy(), temporary_sqlite_directory() as temp:
            settings = Settings(database_path=Path(temp) / "project-targets.sqlite3")
            observations = []
            with TestClient(create_app(settings)) as client:
                context_a = create_project(client, "项目 A", first, password)
                context_b = create_project(client, "项目 B", second, password)

                case_b = create_case(client, context_b, "service-b", "项目 B 登录并查询本人")
                detail_b = run_case(client, context_b, case_b)
                assert detail_b["counts"] == {"PASS": 1, "FAIL": 0, "ERROR": 0, "BLOCKED": 0}
                assert detail_b["target"] == {
                    "kind": "local",
                    "service_id": "service-b",
                    "base_url": second.base_url,
                    "environment_version": 1,
                }
                assert second.received() == ["POST /auth/login", "GET /me"]
                assert first.received() == [], "选择 B 时项目 A 的服务不得收到请求"
                item_b = result_item(
                    "PASS_PROJECT_B", context_b, case_b, detail_b, second.received()
                )
                item_b["selection_proof"] = "B 收到登录和 /me；此时 A 的请求数为 0"
                observations.append(item_b)

                frozen = client.app.state.run_service.get_frozen_snapshot(
                    context_b["project"]["id"], detail_b["run_id"]
                )
                assert frozen["target"] == detail_b["target"]
                call(
                    client,
                    "PUT",
                    context_b["base"] + "/environment",
                    {
                        "target": "local",
                        "service_id": "replacement-after-run",
                        "base_url": first.base_url,
                        "secrets": {"username": "service-a", "password": password},
                    },
                )
                historical = call(
                    client,
                    "GET",
                    context_b["base"] + f"/runs/{detail_b['run_id']}",
                )
                assert historical["target"] == detail_b["target"]
                frozen_after_change = client.app.state.run_service.get_frozen_snapshot(
                    context_b["project"]["id"], detail_b["run_id"]
                )
                assert frozen_after_change["target"] == detail_b["target"]
                call(
                    client,
                    "GET",
                    context_a["base"] + f"/runs/{detail_b['run_id']}",
                    status=404,
                )

                case_a = create_case(
                    client, context_a, "intentionally-wrong-user", "项目 A 人为断言失败"
                )
                detail_a = run_case(client, context_a, case_a)
                assert detail_a["counts"] == {"PASS": 0, "FAIL": 1, "ERROR": 0, "BLOCKED": 0}
                assert detail_a["target"]["service_id"] == "service-a"
                fail_step = detail_a["results"][0]["steps"][1]
                assert fail_step["http_status"] == 200
                assert fail_step["error_stage"] == "assertion"
                assert any("intentionally-wrong-user" in diff for diff in fail_step["assertion_diffs"])
                item_a = result_item(
                    "FAIL_PROJECT_A",
                    context_a,
                    case_a,
                    detail_a,
                    first.received(),
                    intentionally_induced=True,
                )
                item_a["failure_source"] = "人为把 user.id 预期写成 intentionally-wrong-user"
                observations.append(item_a)

                stopped_context = create_project(client, "独立停止服务项目")
                call(
                    client,
                    "PUT",
                    stopped_context["base"] + "/environment",
                    {
                        "target": "local",
                        "service_id": "service-stopped",
                        "base_url": stopped_url,
                        "secrets": {"username": "service-stopped", "password": password},
                    },
                )
                stopped_case = create_case(
                    client,
                    stopped_context,
                    "service-stopped",
                    "已停止服务的真实连接失败",
                    single_login=True,
                )
                stopped_detail = run_case(client, stopped_context, stopped_case)
                assert stopped_detail["counts"] == {
                    "PASS": 0,
                    "FAIL": 0,
                    "ERROR": 1,
                    "BLOCKED": 0,
                }
                stopped_step = stopped_detail["results"][0]["steps"][0]
                assert stopped_step["http_status"] is None
                assert stopped_step["error_stage"] == "connection"
                item_stopped = result_item(
                    "ERROR_STOPPED_SERVICE",
                    stopped_context,
                    stopped_case,
                    stopped_detail,
                    stopped.received(),
                    intentionally_induced=True,
                )
                item_stopped["failure_source"] = "独立本地实例已停止；真实 connection 错误"
                observations.append(item_stopped)

                missing = create_project(client, "未配置环境项目")
                missing_case = create_case(
                    client,
                    missing,
                    "anything",
                    "缺少环境时拒绝预检",
                    authenticated=False,
                )
                missing_response = run_case(client, missing, missing_case, expected_status=422)
                assert "尚未配置项目测试环境" in missing_response["detail"]
                with client.app.state.database.connection() as connection:
                    count = connection.execute(
                        "SELECT COUNT(*) FROM runs WHERE project_id=?",
                        (missing["project"]["id"],),
                    ).fetchone()[0]
                assert count == 0, "缺环境预检失败不得留下运行批次"
                missing_evidence = {
                    "scenario": "MISSING_ENVIRONMENT",
                    "project_id": missing["project"]["id"],
                    "http_status": 422,
                    "detail": missing_response["detail"],
                    "run_rows_created": 0,
                }

            evidence = {
                "transport": "平台 API 使用 TestClient；三个被测目标使用真实本机 HTTP",
                "database": "独立临时 SQLite；退出后回收连接并清理",
                "model_called": False,
                "shared_final_execution": "未代替郭泽强执行正式项目批次",
                "loopback_proxy": "客户端 trust_env=False，并在验证进程显式设置回环 NO_PROXY",
                "results": observations,
                "missing_environment": missing_evidence,
                "historical_target": {
                    "run_id": detail_b["run_id"],
                    "before": detail_b["target"],
                    "after_environment_change": historical["target"],
                    "frozen_snapshot_target": frozen_after_change["target"],
                    "cross_project_read_status": 404,
                },
                "summary": {item["scenario"]: item["outcome"] for item in observations},
            }
            serialized = json.dumps(evidence, ensure_ascii=False, indent=2)
            assert password not in serialized
            assert all(target.server.token not in serialized for target in (first, second, stopped))
            (output_dir / "evidence.json").write_text(serialized, encoding="utf-8")
            return evidence
    finally:
        first.stop()
        second.stop()


def test_two_project_targets_and_stopped_service(tmp_path):
    evidence = verify_project_targets(tmp_path / "project-target-evidence")
    assert evidence["summary"] == {
        "PASS_PROJECT_B": "PASS",
        "FAIL_PROJECT_A": "FAIL",
        "ERROR_STOPPED_SERVICE": "ERROR",
    }
