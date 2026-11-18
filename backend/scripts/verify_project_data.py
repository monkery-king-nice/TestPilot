"""Real HTTP acceptance, with an isolated SQLite file and a process restart.

Run from repository root: python backend/scripts/verify_project_data.py
No external service or model is called. All credentials are disposable fixtures.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
OPENER = build_opener(ProxyHandler({}))


def request(base, method, path, body=None, expected=200):
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(
        base + path, data=payload, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with OPENER.open(req, timeout=5) as response:
            status, content = response.status, response.read().decode("utf-8")
    except HTTPError as error:
        status, content = error.code, error.read().decode("utf-8")
    if status != expected:
        # Deliberately omit the request body from failures.
        raise AssertionError(f"{method} {path}: expected {expected}, got {status}")
    result = json.loads(content)
    assert "temporary-fixture-password" not in content, "公开响应泄露环境值"
    assert "temporary-fixture-user" not in content, "公开响应泄露环境值"
    return result


@contextmanager
def server(database_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["TESTPILOT_DATABASE"] = str(database_path)
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        "backend",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise RuntimeError("后端进程启动失败，请先检查依赖和配置")
                try:
                    if request(base, "GET", "/api/health") == {"status": "ok"}:
                        break
                except (URLError, OSError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("等待服务启动超时") from None
                    time.sleep(0.1)
            yield base
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def verify():
    checks = []
    with tempfile.TemporaryDirectory(prefix="testpilot-data-acceptance-") as directory:
        database = Path(directory) / "acceptance.sqlite3"
        with server(database) as base:
            assert request(base, "GET", "/api/projects") == []
            item = request(base, "POST", "/api/projects", {"name": "HTTP验收项目"}, 201)
            second = request(base, "POST", "/api/projects", {"name": "隔离验证项目"}, 201)
            checks.append({"name": "空库启动与项目创建", "result": "PASS", "response": item})
            prefix = f"/api/projects/{item['id']}"
            req = request(
                base, "POST", prefix + "/requirements", {"text": "系统支持登录并返回用户信息"}, 201
            )
            updated = request(
                base,
                "PATCH",
                prefix + f"/requirements/{req['id']}",
                {"text": "POST /auth/login 成功返回200和token，GET /me 返回user.id"},
            )
            assert updated["version"] == 2
            checks.append({"name": "需求创建与修改版本递增", "result": "PASS", "response": updated})
            endpoints = [
                request(base, "POST", prefix + "/endpoints", {"method": method, "path": path}, 201)
                for method, path in [("POST", "/auth/login"), ("GET", "/me")]
            ]
            checks.append(
                {"name": "登记登录与用户信息接口", "result": "PASS", "response": endpoints}
            )
            environment = request(
                base,
                "PUT",
                prefix + "/environment",
                {
                    "target": "demo",
                    "secrets": {
                        "username": "temporary-fixture-user",
                        "password": "temporary-fixture-password",
                    },
                },
            )
            assert environment == {"target": "demo", "configured_keys": ["password", "username"]}
            assert request(base, "GET", prefix + "/environment") == environment
            checks.append(
                {"name": "环境写入及公开读取不回传值", "result": "PASS", "response": environment}
            )
            denied = request(
                base,
                "PATCH",
                f"/api/projects/{second['id']}/requirements/{req['id']}",
                {"text": "尝试跨项目修改"},
                404,
            )
            checks.append(
                {"name": "跨项目引用拒绝", "result": "PASS", "status": 404, "response": denied}
            )
            invalid = request(
                base,
                "POST",
                prefix + "/endpoints",
                {"method": "GET", "path": "https://example.invalid/me"},
                422,
            )
            checks.append(
                {
                    "name": "拒绝用接口路径指定外部主机",
                    "result": "PASS",
                    "status": 422,
                    "response": invalid,
                }
            )
        # The first OS process is gone. Start a fresh OS process on the same DB.
        with server(database) as restarted:
            assert len(request(restarted, "GET", "/api/projects")) == 2
            assert request(restarted, "GET", prefix + "/requirements") == [updated]
            assert request(restarted, "GET", prefix + "/endpoints") == endpoints
            assert request(restarted, "GET", prefix + "/environment") == environment
            checks.append({"name": "终止并重新启动进程后基础数据保留", "result": "PASS"})
    return {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "mode": "独立uvicorn进程、真实本机HTTP、临时SQLite文件、终止后重启验证",
        "scope": "曾炜毅：项目基础与数据；未调用Agent、用例或执行器",
        "python": sys.version.split()[0],
        "checks": checks,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="可选：保存不含凭证的JSON证据")
    args = parser.parse_args()
    report = verify()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"PASS: {len(report['checks'])} real HTTP acceptance checks (including process restart)")
