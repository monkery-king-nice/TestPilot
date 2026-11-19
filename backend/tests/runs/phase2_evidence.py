"""Prepare shared Phase 2 drafts or verify four outcomes with isolated data.

Shared preparation uses an already running real API and leaves confirmation and
execution to a human. Developer verification uses temporary SQLite databases,
the real local demo HTTP service, and a separately stopped demo instance.
"""

import argparse
import copy
import gc
import json
import os
import secrets
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from demo_service.server import DemoHandler, make_server  # noqa: E402

OUTCOMES = ("PASS", "FAIL", "BLOCKED", "ERROR")
REQUIREMENT_TEXT = (
    "正确密码登录返回200和非空token，查询本人返回demo-user；"
    "错误密码返回401和INVALID_CREDENTIALS。"
)


@contextmanager
def loopback_no_proxy():
    """Bypass ambient proxies for local targets and restore the process env."""
    names = ("NO_PROXY", "no_proxy")
    previous = {name: os.environ.get(name) for name in names}
    for name in names:
        entries = [item.strip() for item in (previous[name] or "").split(",") if item.strip()]
        entries.extend(host for host in ("127.0.0.1", "localhost") if host not in entries)
        os.environ[name] = ",".join(entries)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@contextmanager
def temporary_sqlite_directory():
    """Release sqlite finalizers before cleanup on success and failure."""
    with tempfile.TemporaryDirectory(prefix="testpilot-phase2-runs-") as temp:
        try:
            yield temp
        finally:
            gc.collect()


def call(client, method, path, payload=None, status=200):
    response = client.request(method, path, json=payload)
    if response.status_code != status:
        raise AssertionError(
            f"{method} {path}: expected {status}, got {response.status_code}: {response.text}"
        )
    return response.json()


def drafts(requirement, login, me):
    login_step = {
        "name": "login",
        "phase": "setup",
        "endpoint_id": login["id"],
        "endpoint_version": login["version"],
        "headers": {},
        "body": {"username": "{{env.username}}", "password": "{{env.password}}"},
        "assertions": [
            {"type": "status", "expected": 200},
            {"type": "nonempty_string", "path": "token"},
        ],
        "extract": {"token": "token"},
    }
    me_step = {
        "name": "me",
        "phase": "test",
        "endpoint_id": me["id"],
        "endpoint_version": me["version"],
        "headers": {"Authorization": "Bearer {{steps.login.token}}"},
        "body": None,
        "assertions": [
            {"type": "status", "expected": 200},
            {"type": "json_equals", "path": "user.id", "expected": "demo-user"},
            {"type": "elapsed_ms_lte", "expected": 3000},
        ],
        "extract": {},
    }
    common = {
        "requirement_id": requirement["id"],
        "requirement_version": requirement["version"],
        "expected_basis": REQUIREMENT_TEXT,
    }

    invalid_password = copy.deepcopy(login_step)
    invalid_password.update(
        {
            "phase": "test",
            "body": {"username": "demo-user", "password": "incorrect-demo-value"},
            "assertions": [
                {"type": "status", "expected": 401},
                {"type": "json_equals", "path": "code", "expected": "INVALID_CREDENTIALS"},
            ],
            "extract": {},
        }
    )
    failed_login = copy.deepcopy(login_step)
    failed_login["body"] = {"username": "demo-user", "password": "incorrect-demo-value"}
    wrong_user = copy.deepcopy(me_step)
    wrong_user["assertions"][1]["expected"] = "different-user"
    unavailable_login = copy.deepcopy(login_step)
    unavailable_login.update({"phase": "test", "extract": {}})

    return {
        "PASS": {
            **common,
            "title": "Phase2 PASS：错误密码按约定返回401",
            "steps": [invalid_password],
        },
        "FAIL": {
            **common,
            "title": "Phase2 人为FAIL：故意写错本人编号预期",
            "expected_basis": "人为制造FAIL：预期different-user，实际应为demo-user",
            "steps": [login_step, wrong_user],
        },
        "BLOCKED": {
            **common,
            "title": "Phase2 人为BLOCKED：准备登录失败后不查询本人",
            "expected_basis": "人为制造BLOCKED：准备登录使用错误密码，后续/me不得发送",
            "steps": [failed_login, me_step],
        },
        "ERROR": {
            **common,
            "title": "Phase2 人为ERROR：独立演示实例已停止",
            "expected_basis": "人为制造ERROR：仅对单独且已停止的本机实例发起登录",
            "steps": [unavailable_login],
        },
    }


def prepare_scenarios(client, username, password, name, selected=OUTCOMES[:3]):
    project = call(client, "POST", "/api/projects", {"name": name}, 201)
    base = f"/api/projects/{project['id']}"
    requirement = call(
        client, "POST", base + "/requirements", {"text": REQUIREMENT_TEXT}, 201
    )
    login = call(
        client, "POST", base + "/endpoints", {"method": "POST", "path": "/auth/login"}, 201
    )
    me = call(
        client, "POST", base + "/endpoints", {"method": "GET", "path": "/me"}, 201
    )
    call(
        client,
        "PUT",
        base + "/environment",
        {"target": "demo", "secrets": {"username": username, "password": password}},
    )
    cases = {}
    for outcome, draft in drafts(requirement, login, me).items():
        if outcome not in selected:
            continue
        case = call(client, "POST", base + "/cases", draft, 201)
        cases[outcome] = case
    return {"project": project, "requirement": requirement, "base": base, "cases": cases}


def run_confirmed_case(client, base, case):
    confirmed = call(
        client, "POST", base + f"/cases/{case['id']}/confirm", {"version": case["version"]}
    )
    if confirmed["status"] != "CONFIRMED":
        raise AssertionError(f"用例未确认：{confirmed}")
    accepted = call(
        client,
        "POST",
        base + "/runs",
        {"cases": [{"id": case["id"], "version": case["version"]}]},
        202,
    )
    route = base + f"/runs/{accepted['run_id']}"
    deadline = time.monotonic() + 15
    while True:
        detail = call(client, "GET", route)
        if detail["status"] in {"COMPLETED", "INTERRUPTED"}:
            return detail
        if time.monotonic() >= deadline:
            raise TimeoutError("运行批次未在15秒内结束")
        time.sleep(0.05)


def evidence_item(outcome, context, case, detail, requests):
    result = detail["results"][0]
    expected_counts = {key: int(key == outcome) for key in OUTCOMES}
    if detail["counts"] != expected_counts or result["outcome"] != outcome:
        raise AssertionError(f"{outcome} 结果不符：{detail}")
    return {
        "scenario": outcome,
        "intentionally_induced": outcome != "PASS",
        "project_id": context["project"]["id"],
        "requirement_id": context["requirement"]["id"],
        "requirement_version": context["requirement"]["version"],
        "case_id": case["id"],
        "case_version": case["version"],
        "run_id": detail["run_id"],
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
        "demo_requests_received": requests,
    }


def verify(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(24)
    request_log = []
    request_lock = threading.Lock()

    class CountingDemoHandler(DemoHandler):
        def parse_request(self):
            if not super().parse_request():
                return False
            with request_lock:
                request_log.append(f"{self.command} {self.path}")
            return True

    server = make_server("demo-user", password, port=0)
    server.RequestHandlerClass = CountingDemoHandler
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with loopback_no_proxy(), temporary_sqlite_directory() as temp:
            settings = Settings(
                database_path=Path(temp) / "active.sqlite3",
                demo_base_url=f"http://127.0.0.1:{server.server_port}",
            )
            observations = []
            with TestClient(create_app(settings)) as client:
                context = prepare_scenarios(
                    client, "demo-user", password, "周兴宇 Phase2 独立结果自测"
                )
                for outcome in OUTCOMES[:3]:
                    case = context["cases"][outcome]
                    with request_lock:
                        request_log.clear()
                    detail = run_confirmed_case(client, context["base"], case)
                    with request_lock:
                        received = request_log.copy()
                    item = evidence_item(outcome, context, case, detail, received)
                    steps = item["steps"]
                    if outcome == "PASS":
                        assert steps[0]["http_status"] == 401
                        assert received == ["POST /auth/login"]
                    elif outcome == "FAIL":
                        assert [step["http_status"] for step in steps] == [200, 200]
                        assert steps[1]["error_stage"] == "assertion"
                        assert any("different-user" in diff for diff in steps[1]["assertion_diffs"])
                        assert received == ["POST /auth/login", "GET /me"]
                    else:
                        assert steps[0]["http_status"] == 401
                        assert steps[1]["http_status"] is None
                        assert steps[1]["error_stage"] == "setup_failed"
                        assert received == ["POST /auth/login"]
                        assert all(request != "GET /me" for request in received)
                    observations.append(item)

            # Start and then fully stop a separate target. Its port is never reused
            # by the active demo, so this is a real connection failure, not a fake.
            stopped = make_server("demo-user", secrets.token_urlsafe(24), port=0)
            stopped_url = f"http://127.0.0.1:{stopped.server_port}"
            stopped_thread = threading.Thread(target=stopped.serve_forever, daemon=True)
            stopped_thread.start()
            stopped.shutdown()
            stopped.server_close()
            stopped_thread.join(timeout=3)
            stopped_settings = Settings(
                database_path=Path(temp) / "stopped.sqlite3", demo_base_url=stopped_url
            )
            with TestClient(create_app(stopped_settings)) as client:
                context = prepare_scenarios(
                    client,
                    "demo-user",
                    password,
                    "周兴宇 Phase2 独立停止实例自测",
                    selected=("ERROR",),
                )
                case = context["cases"]["ERROR"]
                detail = run_confirmed_case(client, context["base"], case)
                item = evidence_item("ERROR", context, case, detail, [])
                item["failure_source"] = "单独且已停止的本机演示实例；真实连接失败"
                assert item["steps"][0]["http_status"] is None
                assert item["steps"][0]["error_stage"] == "connection"
                observations.append(item)

            evidence = {
                "transport": "平台API使用TestClient；被测登录服务使用真实本机HTTP",
                "database": "两个独立临时SQLite数据库，退出后清除",
                "model_called": False,
                "shared_final_execution": "未代替郭泽强执行；共享草稿由prepare命令单独创建",
                "results": observations,
                "summary": {item["scenario"]: item["outcome"] for item in observations},
                "timeout_control": {
                    "existing_test": "test_timeout_becomes_error_with_evidence",
                    "kind": "httpx.MockTransport超时替身",
                    "counted_as_stopped_instance_evidence": False,
                },
            }
            serialized = json.dumps(evidence, ensure_ascii=False, indent=2)
            assert password not in serialized and server.token not in serialized
            (output_dir / "evidence.json").write_text(serialized, encoding="utf-8")
            return evidence
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def prepare(api_base: str, output: Path):
    password = os.environ.get("DEMO_PASSWORD")
    if not password:
        raise SystemExit("请先在当前终端设置 DEMO_PASSWORD；密码不会写入输出文件")
    username = os.environ.get("DEMO_USERNAME", "demo-user")
    with httpx.Client(base_url=api_base, trust_env=False, timeout=10) as client:
        context = prepare_scenarios(
            client, username, password, "周兴宇 Phase2 共享验收（待人工确认）"
        )
    result = {
        "project_id": context["project"]["id"],
        "requirement_id": context["requirement"]["id"],
        "requirement_version": context["requirement"]["version"],
        "cases": [
            {
                "scenario": outcome,
                "case_id": case["id"],
                "case_version": case["version"],
                "status": case["status"],
                "title": case["title"],
            }
            for outcome, case in context["cases"].items()
        ],
        "manual_next_steps": [
            "在用例页面逐条复核预期，并人工确认三个草稿",
            "PASS、FAIL、BLOCKED可分别执行；FAIL优先交给郭泽强做失败分析",
            "由郭泽强在共享验收页最终点击执行，并记录真实run_id",
            "ERROR只在独立停止实例环境复现，不在共享正常服务中执行",
        ],
        "credentials_written": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify_parser = commands.add_parser("verify", help="独立临时数据库验证四类结果")
    verify_parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/phase2-run-outcomes")
    )
    prepare_parser = commands.add_parser("prepare", help="只创建共享草稿，不确认、不执行")
    prepare_parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    prepare_parser.add_argument(
        "--output", type=Path, default=Path("artifacts/phase2-run-outcomes/preparation.json")
    )
    args = parser.parse_args()
    if args.command == "verify":
        evidence = verify(args.output_dir)
        print(json.dumps({"summary": evidence["summary"], "output_dir": str(args.output_dir.resolve())}, ensure_ascii=False))
    else:
        prepared = prepare(args.api_base, args.output)
        print(json.dumps(prepared, ensure_ascii=False))
