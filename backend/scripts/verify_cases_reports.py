"""Real HTTP acceptance: separate Uvicorn process + team's local demo service.

Run from repository root. Creates a temporary database, never calls an external
model, and writes only sanitized results/reports to --output-dir.
"""

import argparse
import copy
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from demo_service.server import make_server  # noqa: E402


def unused_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def stop_process(process):
    if process.poll() is None:
        # Graceful stdin shutdown also reaches Windows venv redirector children.
        process.stdin.write(b"\n")
        process.stdin.flush()
        process.wait(timeout=15)
    process.stdin.close()


def verify(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(24)
    server = make_server("demo-user", password, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    observations = []
    try:
        with tempfile.TemporaryDirectory(prefix="testpilot-cases-") as temp, ExitStack() as cleanup:
            env = dict(os.environ, PYTHONUTF8="1",
                       TESTPILOT_DATABASE=str(Path(temp) / "acceptance.sqlite3"),
                       DEMO_BASE_URL=f"http://127.0.0.1:{server.server_port}")
            port = unused_port()
            runner = (
                "import sys,threading,uvicorn;sys.path.insert(0,'backend');"
                "server=uvicorn.Server(uvicorn.Config('app.main:app',host='127.0.0.1',"
                "port=int(sys.argv[1]),access_log=False));"
                "threading.Thread(target=lambda:(sys.stdin.readline(),"
                "setattr(server,'should_exit',True)),daemon=True).start();server.run()"
            )
            process = subprocess.Popen([sys.executable, "-c", runner, str(port)],
                cwd=ROOT, env=env, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            cleanup.callback(stop_process, process)
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=10) as api:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        if api.get("/api/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("独立后端未能启动")
                    time.sleep(0.1)

                def call(method, path, payload=None, status=200):
                    response = api.request(method, path, json=payload)
                    if response.status_code != status:
                        raise AssertionError(f"{method} {path}: expected {status}, got {response.status_code}")
                    return response

                project = call("POST", "/api/projects", {"name": "沈冠宇模块真实HTTP验收"}, 201).json()
                base = f"/api/projects/{project['id']}"
                req = call("POST", base + "/requirements", {"text":
                    "正确密码登录返回200和非空token，查询本人返回demo-user；错误密码返回401和INVALID_CREDENTIALS。"
                }, 201).json()
                login = call("POST", base + "/endpoints", {"method": "POST", "path": "/auth/login"}, 201).json()
                me = call("POST", base + "/endpoints", {"method": "GET", "path": "/me"}, 201).json()
                call("PUT", base + "/environment", {"target": "demo", "secrets": {
                    "username": "demo-user", "password": password}})
                draft = {
                    "title": "登录并查询本人信息", "requirement_id": req["id"],
                    "requirement_version": 1, "expected_basis": req["text"], "steps": [
                        {"name": "login", "phase": "setup", "endpoint_id": login["id"],
                         "endpoint_version": 1, "headers": {}, "body": {
                             "username": "{{env.username}}", "password": "{{env.password}}"},
                         "assertions": [{"type": "status", "expected": 200},
                                        {"type": "nonempty_string", "path": "token"}],
                         "extract": {"token": "token"}},
                        {"name": "me", "phase": "test", "endpoint_id": me["id"],
                         "endpoint_version": 1, "headers": {"Authorization": "Bearer {{steps.login.token}}"},
                         "body": None, "assertions": [
                             {"type": "status", "expected": 200},
                             {"type": "json_equals", "path": "user.id", "expected": "demo-user"},
                             {"type": "elapsed_ms_lte", "expected": 3000}], "extract": {}},
                    ],
                }
                case = call("POST", base + "/cases", draft, 201).json()
                ref = {"cases": [{"id": case["id"], "version": 1}]}
                rejected = call("POST", base + "/runs", ref, 422).json()
                observations.append({"check": "未确认用例拦截", "result": rejected})
                for name in ("缺少断言", "未定义变量"):
                    invalid = copy.deepcopy(draft)
                    if name == "缺少断言":
                        invalid["steps"][1]["assertions"] = []
                    else:
                        invalid["steps"][1]["headers"]["Authorization"] = "{{steps.login.absent}}"
                    item = call("POST", base + "/cases", invalid, 201).json()
                    rejected = call("POST", base + f"/cases/{item['id']}/confirm", {"version": 1}, 422).json()
                    observations.append({"check": name, "result": rejected})
                call("POST", base + f"/cases/{case['id']}/confirm", {"version": 1})

                def run(refs):
                    accepted = call("POST", base + "/runs", {"cases": refs}, 202).json()
                    route = base + f"/runs/{accepted['run_id']}"
                    deadline = time.monotonic() + 15
                    while True:
                        detail = call("GET", route).json()
                        if detail["status"] in {"COMPLETED", "INTERRUPTED"}:
                            return route, detail
                        if time.monotonic() >= deadline:
                            raise TimeoutError("验收批次未按时结束")
                        time.sleep(0.05)

                route, detail = run(ref["cases"])
                assert detail["counts"] == {"PASS": 1, "FAIL": 0, "ERROR": 0, "BLOCKED": 0}
                original = call("GET", route + "/report").content
                (output_dir / "success-report.html").write_bytes(original)
                observations.append({"check": "真实登录与查询成功", "result": detail})

                variants = []
                for name in ("错误密码按预期拒绝", "故意设置不匹配的用户编号", "准备登录失败", "运行时提取缺失字段"):
                    item = copy.deepcopy(draft)
                    item["title"] = name
                    if name == "错误密码按预期拒绝":
                        item["steps"] = item["steps"][:1]
                        item["steps"][0].update({"phase": "test", "extract": {}, "assertions": [
                            {"type": "status", "expected": 401},
                            {"type": "json_equals", "path": "code", "expected": "INVALID_CREDENTIALS"}]})
                        item["steps"][0]["body"]["password"] = "incorrect-demo-value"
                    elif name == "故意设置不匹配的用户编号":
                        item["expected_basis"] = "验收FAIL：人为设置不匹配预期，验证保存断言差异"
                        item["steps"][1]["assertions"][1]["expected"] = "different-user"
                    elif name == "准备登录失败":
                        item["steps"][0]["body"]["password"] = "incorrect-demo-value"
                    else:
                        item["expected_basis"] = "验收ERROR：预期401，但人为配置不存在的提取字段"
                        item["steps"] = item["steps"][1:]
                        item["steps"][0].update({"headers": {}, "assertions": [
                            {"type": "status", "expected": 401}], "extract": {"missing": "absent"}})
                    saved = call("POST", base + "/cases", item, 201).json()
                    call("POST", base + f"/cases/{saved['id']}/confirm", {"version": 1})
                    variants.append({"id": saved["id"], "version": 1})
                mixed_route, mixed = run(variants)
                assert mixed["counts"] == {"PASS": 1, "FAIL": 1, "ERROR": 1, "BLOCKED": 1}
                (output_dir / "outcomes-report.html").write_bytes(call("GET", mixed_route + "/report").content)
                observations.append({"check": "真实HTTP四类结果", "result": mixed})

                manual = call("POST", base + f"/cases/{case['id']}/manual-checks", {
                    "version": 1, "items": [{"check": "页面登录交互", "pass_condition": "提交后给出结果",
                        "outcome": "NOT_CHECKED", "evidence": "接口验收脚本不冒充人工页面验收"}]}, 201).json()
                assert manual["version"] == 1
                observations.append({"check": "保存人工检查清单", "result": {
                    "version": manual["version"], "outcome": manual["items"][0]["outcome"]}})

                call("PATCH", base + f"/requirements/{req['id']}", {"text": "变更后的需求正文"})
                rejected = call("POST", base + "/runs", ref, 422).json()
                assert "需求版本已过期" in rejected["detail"]
                observations.append({"check": "需求版本过期拦截", "result": rejected})
                draft["title"] = "当前用例已修改"
                draft["expected_basis"] = "新依据不应改写旧报告"
                draft["requirement_version"] = 2
                edited = call("PATCH", base + f"/cases/{case['id']}", draft).json()
                assert (edited["version"], edited["status"]) == (2, "NEEDS_REVIEW")
                assert call("GET", route + "/report").content == original
                observations.append({"check": "修改需求与用例后历史报告字节一致", "result": {
                    "sha256": hashlib.sha256(original).hexdigest(), "identical": True}})
                combined = json.dumps(observations, ensure_ascii=False)
                assert password not in combined
                assert server.token not in combined
                assert all(password.encode() not in p.read_bytes()
                           and server.token.encode() not in p.read_bytes()
                           for p in output_dir.glob("*.html"))
                (output_dir / "acceptance.json").write_text(json.dumps({
                    "transport": "真实HTTP：独立Uvicorn进程 + 团队本地演示服务",
                    "model_called": False, "checks": observations,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({"checks_passed": len(observations), "four_outcomes": mixed["counts"],
                    "history_unchanged": True, "output_dir": str(output_dir.resolve())}, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/cases-reports"))
    verify(parser.parse_args().output_dir)
