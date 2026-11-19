"""Acceptance for the Windows launcher, using an independent clean checkout.

Creates local test data only; never calls a model. Report omits personal paths,
environment values, credentials and tokens. --keep-running supports browser QA.
"""

import argparse
import hashlib
import json
import os
import queue
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from dev import ROOT, Processes, check_ports

HTTP = build_opener(ProxyHandler({}))


def request(method, path, payload=None, expected=200):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        "http://127.0.0.1:5173" + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with HTTP.open(req, timeout=10) as response:
            status, data = response.status, response.read().decode("utf-8")
    except HTTPError as error:
        status, data = error.code, error.read().decode("utf-8")
    assert status == expected, f"{method} {path}: expected {expected}, got {status}"
    return data


def clean_copy(destination):
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
        )
        .decode("utf-8")
        .split("\0")
    )
    for name in filter(None, set(names)):
        source = ROOT / name
        if source.is_file():
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output)


def stop_and_assert_ports_free():
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        try:
            for port in (8000, 8010, 5173):
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", port))
            return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("A child service still owns a port after launcher shutdown")


@contextmanager
def launch(checkout, secret, observations, *, skip_install=False):
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(checkout / "scripts/start.ps1"),
        "-NoModel",
        "-Database",
        "startup.sqlite3",
        "-Python",
        sys.executable,
    ]
    if skip_install:
        command.append("-SkipInstall")
    env = dict(os.environ, DEMO_PASSWORD=secret, DEMO_USERNAME="demo-user", PYTHONUTF8="1")
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("TESTPILOT_MODEL_KEY", None)
    env.pop("TESTPILOT_MODEL_URL", None)
    guard = Processes()
    process = subprocess.Popen(
        command,
        cwd=checkout.parent,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    guard.job.attach(process)
    guard.children.append(process)
    lines = queue.Queue()
    transcript = []

    def consume():
        for raw in iter(process.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            transcript.append(line)
            lines.put(line)

    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 300
        ready = False
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=0.25)
                if line.startswith(
                    ("[tool]", "[port]", "[dependency]", "[mode]", "[READY]", "[model]", "[ERROR]")
                ):
                    print(line, flush=True)
                if line.startswith("[stop]"):
                    ready = True
                    break
            except queue.Empty:
                pass
            if process.poll() is not None:
                raise AssertionError("Launcher exited before ready: " + "\n".join(transcript[-12:]))
        assert ready, "Launcher did not become healthy within 300 seconds"
        observations.append(
            {
                "check": "Windows PowerShell 5.1三服务启动"
                + ("（已安装依赖）" if skip_install else "（零依赖目录）"),
                "result": "PASS",
                "mode": "VITE_USE_MOCK=false; model disabled",
                "tools": [line for line in transcript if line.startswith("[tool]")],
                "cwd": "从仓库以外的目录调用脚本，仍按仓库定位资源",
            }
        )
        yield
    finally:
        guard.close()
        reader.join(timeout=3)
        process.stdout.close()
        assert secret not in "\n".join(transcript), "Launcher output leaked the test credential"
        stop_and_assert_ports_free()


def verify(checkout, *, skip_install=False, keep_running=False):
    observations = []
    check_ports()
    database = checkout / "startup.sqlite3"
    assert not database.exists(), "Acceptance requires a new database"
    secret = secrets.token_urlsafe(28)
    with launch(checkout, secret, observations, skip_install=skip_install):
        config = request("GET", "/src/api/config.ts")
        assert re.search(r'["\']VITE_USE_MOCK["\']\s*:\s*["\']false["\']', config), (
            "Frontend did not receive real-mode environment"
        )
        assert json.loads(request("GET", "/api/projects")) == []
        project = json.loads(request("POST", "/api/projects", {"name": "第二阶段空库复现"}, 201))
        prefix = f"/api/projects/{project['id']}"
        text = "未登录查询本人信息返回401和UNAUTHORIZED。"
        requirement = json.loads(request("POST", prefix + "/requirements", {"text": text}, 201))
        observations.append(
            {
                "check": "真实Vite代理创建项目及需求",
                "result": "PASS",
                "project_id": project["id"],
                "requirement_id": requirement["id"],
                "version": requirement["version"],
                "text": text,
            }
        )
        endpoint = json.loads(
            request("POST", prefix + "/endpoints", {"method": "GET", "path": "/me"}, 201)
        )
        request(
            "PUT",
            prefix + "/environment",
            {"target": "demo", "secrets": {"username": "demo-user", "password": secret}},
        )
        draft = {
            "title": "无模型手工确认：缺少凭证返回401",
            "requirement_id": requirement["id"],
            "requirement_version": 1,
            "expected_basis": text,
            "steps": [
                {
                    "name": "me_without_auth",
                    "phase": "test",
                    "endpoint_id": endpoint["id"],
                    "endpoint_version": 1,
                    "headers": {},
                    "body": None,
                    "assertions": [
                        {"type": "status", "expected": 401},
                        {"type": "json_equals", "path": "code", "expected": "UNAUTHORIZED"},
                    ],
                    "extract": {},
                }
            ],
        }
        case = json.loads(request("POST", prefix + "/cases", draft, 201))
        request("POST", prefix + f"/cases/{case['id']}/confirm", {"version": 1})
        run = json.loads(
            request("POST", prefix + "/runs", {"cases": [{"id": case["id"], "version": 1}]}, 202)
        )
        run_path = prefix + f"/runs/{run['run_id']}"
        deadline = time.monotonic() + 20
        while True:
            detail = json.loads(request("GET", run_path))
            if detail["status"] == "COMPLETED":
                break
            assert time.monotonic() < deadline, "Run did not finish"
            time.sleep(0.1)
        assert detail["counts"] == {"PASS": 1, "FAIL": 0, "ERROR": 0, "BLOCKED": 0}
        report = request("GET", run_path + "/report")
        assert run["run_id"] in report and secret not in report
        request("POST", prefix + "/agent/clarify", {"requirement_id": requirement["id"]}, 502)
        request("GET", run_path + "/report")
        observations.append(
            {
                "check": "禁用模型仍能人工确认、真实执行及下载报告",
                "result": "PASS",
                "case_id": case["id"],
                "case_version": 1,
                "run_id": run["run_id"],
                "counts": detail["counts"],
                "model_api_status": 502,
            }
        )
        if keep_running:
            print(
                "[BROWSER-QA] Open http://127.0.0.1:5173/projects ; press Enter in this verifier after browser QA.",
                flush=True,
            )
            input()
    observations.append({"check": "停止后仅本次三服务退出，端口全部释放", "result": "PASS"})
    with launch(checkout, secret, observations, skip_install=True):
        assert project in json.loads(request("GET", "/api/projects"))
        assert json.loads(request("GET", prefix + "/requirements")) == [requirement]
        assert json.loads(request("GET", run_path))["counts"] == detail["counts"]
        assert run["run_id"] in request("GET", run_path + "/report")
        observations.append(
            {
                "check": "同一数据库重启后ID、需求正文及历史报告保留",
                "result": "PASS",
                "project_id": project["id"],
                "requirement_id": requirement["id"],
                "run_id": run["run_id"],
            }
        )
    digest = hashlib.sha256(database.read_bytes()).hexdigest()
    missing = subprocess.run(
        [
            sys.executable,
            str(checkout / "scripts/dev.py"),
            "--check",
            "--database",
            "startup.sqlite3",
        ],
        cwd=checkout,
        env=dict(os.environ, PATH=""),
        capture_output=True,
        timeout=15,
    )
    assert (
        missing.returncode == 1
        and b"Install Node.js" in missing.stdout
        and b"reopen PowerShell" in missing.stdout
    )
    assert hashlib.sha256(database.read_bytes()).hexdigest() == digest
    observations.append({"check": "缺少Node给出安装及重开终端提示，数据库不变", "result": "PASS"})
    guard = Processes()
    try:
        owner = subprocess.Popen(
            [sys.executable, "-m", "http.server", "8000", "--bind", "127.0.0.1"],
            cwd=checkout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        guard.job.attach(owner)
        guard.children.append(owner)
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", 8000), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.1)
        busy = subprocess.run(
            [
                sys.executable,
                str(checkout / "scripts/dev.py"),
                "--check",
                "--database",
                "startup.sqlite3",
            ],
            cwd=checkout,
            capture_output=True,
            timeout=20,
        )
        assert busy.returncode == 1 and b"Get-NetTCPConnection" in busy.stdout
        assert owner.poll() is None, "Unrelated port owner was terminated"
        with socket.create_connection(("127.0.0.1", 8000), timeout=1):
            pass
        assert hashlib.sha256(database.read_bytes()).hexdigest() == digest
        observations.append(
            {"check": "API端口被另一进程占用时拒绝启动，原进程及数据库保留", "result": "PASS"}
        )
    finally:
        guard.close()
    stop_and_assert_ports_free()
    return {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "baseline": "7ccc4e5",
        "tested_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "scope": "同一台Windows机器上的独立源码目录、新虚拟环境、新SQLite文件；不代表第二位同学或第二台电脑复现",
        "second_person": "待同学独立执行README步骤并回传第一处问题",
        "checks": observations,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checkout", type=Path, help="已有隔离测试目录；需无startup.sqlite3文件")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--keep-running", action="store_true")
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("This acceptance checks the Windows PowerShell launcher; run on Windows.")
    with tempfile.TemporaryDirectory(prefix="testpilot-phase2-clean-") as directory:
        checkout = args.checkout or Path(directory) / "checkout"
        if not args.checkout:
            clean_copy(checkout)
        result = verify(checkout, skip_install=args.skip_install, keep_running=args.keep_running)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"PASS: {len(result['checks'])} startup acceptance checks", flush=True)
