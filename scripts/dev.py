"""Start the existing API, demo and npm dev script in real mode, from any cwd.

Standard library only. Never deletes a database or stops a pre-existing process.
"""

from __future__ import annotations

import argparse
import ctypes
import getpass
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
PORTS = {"API": 8000, "demo": 8010, "frontend": 5173}
MODEL_KEYS = ("DEEPSEEK_API_KEY", "TESTPILOT_MODEL_KEY", "TESTPILOT_MODEL_URL", "TESTPILOT_MODEL")
HTTP = build_opener(ProxyHandler({}))


class StartError(RuntimeError):
    pass


def say(message):
    print(message, flush=True)


class WindowsJob:
    """OS-owned job: closes only the process trees created by this launcher."""

    def __init__(self):
        from ctypes import wintypes

        class Limits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_working", ctypes.c_size_t),
                ("max_working", ctypes.c_size_t),
                ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class Counters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "read_ops",
                    "write_ops",
                    "other_ops",
                    "read_bytes",
                    "write_bytes",
                    "other_bytes",
                )
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", Limits),
                ("io", Counters),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise StartError(
                "Cannot create an isolated Windows process job. Retry in a normal PowerShell window."
            )
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.close()
            raise StartError("Cannot configure Windows process cleanup; no services were started.")

    def attach(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            process.terminate()
            process.wait(timeout=5)
            raise StartError("Cannot isolate this child process. No existing process was stopped.")

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class Processes:
    def __init__(self):
        self.children = []
        self.job = WindowsJob() if os.name == "nt" else None

    def spawn(self, command, *, cwd=ROOT, env, service=False):
        options = (
            {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE if service else subprocess.DEVNULL,
            **options,
        )
        if self.job:
            self.job.attach(process)
        self.children.append(process)
        return process

    def run(self, command, *, cwd=ROOT, env, description):
        say(f"[install] {description}")
        if self.spawn(command, cwd=cwd, env=env).wait() != 0:
            raise StartError(
                f"{description} failed. Check network/registry access and retry; existing databases are preserved."
            )

    def close(self):
        # The two Python hosts stop on stdin; npm/Vite are contained in our job.
        for process in self.children:
            if process.poll() is None and process.stdin:
                try:
                    process.stdin.write(b"\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
        deadline = time.monotonic() + 6
        for process in self.children:
            if process.poll() is None and process.stdin:
                try:
                    process.wait(timeout=max(0.1, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    pass
        if self.job:
            self.job.close()  # Includes npm's Vite/esbuild grandchildren.
        else:
            for process in self.children:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
        for process in self.children:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait(timeout=5)
            if process.stdin:
                process.stdin.close()


def version(command, name, minimum):
    try:
        result = subprocess.run(
            command, env=child_environment(), capture_output=True, text=True, timeout=15, check=True
        )
        value = result.stdout.strip().lstrip("v")
        if int(value.split(".")[0]) < minimum:
            raise ValueError()
    except (OSError, ValueError, subprocess.SubprocessError):
        raise StartError(
            f"{name} {minimum}+ is required. Install it, reopen PowerShell, and run scripts/start.ps1 -Check."
        ) from None
    say(f"[tool] {name} {value}")
    return value


def node_tools():
    node = shutil.which("node")
    if not node:
        raise StartError(
            "Node.js was not found. Install Node.js with npm, reopen PowerShell, then run scripts/start.ps1 -Check."
        )
    version([node, "--version"], "Node.js", 18)
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise StartError(
            "npm was not found. Repair/reinstall Node.js with npm enabled and reopen PowerShell."
        )
    # Invoke npm's JS entry with Node, avoiding cmd.exe/.ps1 quoting and execution policy.
    npm_path = Path(npm).resolve()
    candidates = [npm_path.parent / "node_modules/npm/bin/npm-cli.js", npm_path]
    npm_cli = next((p for p in candidates if p.is_file() and p.suffix == ".js"), None)
    if npm_cli is None:
        raise StartError(
            "npm CLI was not found beside Node.js. Repair the Node.js/npm installation and retry."
        )
    version([node, str(npm_cli), "--version"], "npm", 8)
    return node, str(npm_cli)


def check_ports(*, skip_demo=False):
    for name, port in PORTS.items():
        if skip_demo and name == "demo":
            continue
        with socket.socket() as listener:
            if os.name == "nt":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                raise StartError(
                    f"Port {port} ({name}) is occupied. No process was stopped. "
                    f"Use Get-NetTCPConnection -LocalPort {port} to identify its owner; "
                    "close your previous TestPilot terminal or ask the owner to release it, then retry."
                ) from None
        say(f"[port] {name} {port} available")


def venv_python():
    return ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def installed(python):
    if not python.is_file():
        return False
    try:
        return (
            subprocess.run(
                [
                    str(python),
                    "-c",
                    "import fastapi,uvicorn,httpx,pydantic; assert tuple(__import__('sys').version_info)>=(3,11)",
                ],
                env=child_environment(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def read_http(path):
    try:
        with HTTP.open(path, timeout=2) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as error:
        return error.code, error.read().decode("utf-8")


def wait_ready(processes, url, expected, *, json_body=None):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise StartError(
                "A service exited during startup. Read the error above; check dependencies and ports, then retry."
            )
        try:
            status, body = read_http(url)
            if status == expected and (json_body is None or json.loads(body) == json_body):
                return
        except (URLError, OSError, ValueError):
            pass
        time.sleep(0.1)
    raise StartError(
        f"Service health timeout at {url}. Check the errors above; do not reuse a half-started session."
    )


def child_environment(*, model=False):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    env.pop("DEMO_PASSWORD", None)
    if not model:
        for name in MODEL_KEYS:
            env.pop(name, None)
    return env


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="read-only tool/port/dependency checks"
    )
    parser.add_argument(
        "--skip-install", action="store_true", help="use already-installed local dependencies"
    )
    parser.add_argument(
        "--no-model", action="store_true", help="disable model calls; use manually confirmed cases"
    )
    parser.add_argument(
        "--no-demo",
        action="store_true",
        help="skip the local demo login service (8010); for local targets that need no credentials",
    )
    parser.add_argument(
        "--database", default=os.getenv("TESTPILOT_DATABASE", "backend/data/testpilot.sqlite3")
    )
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):  # noqa: UP036 - launcher diagnoses older Python before dependencies
        raise StartError(
            "Python 3.11+ is required. Install it and retry with scripts/start.ps1 -Python python."
        )
    say(f"[tool] Python {sys.version.split()[0]}")
    node, npm_cli = node_tools()
    check_ports(skip_demo=args.no_demo)  # Before installations, password prompts, or database writes.
    python = venv_python()
    frontend_ready = (ROOT / "frontend/node_modules/vite/bin/vite.js").is_file()
    backend_ready = installed(python)
    say(
        f"[dependency] backend {'ready' if backend_ready else 'installation required'}; frontend {'ready' if frontend_ready else 'npm ci required'}"
    )
    database = Path(args.database)
    if str(database) == ":memory:":
        raise StartError("Use a SQLite file path; :memory: cannot retain data after restart.")
    if not database.is_absolute():
        database = ROOT / database
    database = database.resolve()
    say(
        f"[database] {'existing file, preserved' if database.exists() else 'new file will be created at service startup'}"
    )
    say(
        "[mode] REAL: VITE_USE_MOCK=false; browser /api -> local API"
        + (" -> local demo" if not args.no_demo else " (demo service skipped, local target only)")
    )
    if args.check:
        say(
            "[check] PASS. Run scripts/start.ps1 to install dependencies and start all three services."
        )
        return 0
    if args.skip_install and not (backend_ready and frontend_ready):
        raise StartError(
            "Local dependencies are missing. Retry without -SkipInstall, or run the manual install commands in README.md."
        )
    password = None
    if not args.no_demo:
        password = os.getenv("DEMO_PASSWORD")
        if not password:
            if not sys.stdin.isatty():
                raise StartError(
                    "Set DEMO_PASSWORD in this terminal before starting (see the secure Read-Host example in README.md)."
                )
            password = getpass.getpass(
                "Local demo password (hidden; use the same value in the environment page): "
            )
            if not password:
                raise StartError(
                    "The local demo password must not be empty. Set DEMO_PASSWORD and retry."
                )
    processes = Processes()
    try:
        if not args.skip_install:
            install_env = child_environment()
            if not python.exists():
                processes.run(
                    [sys.executable, "-m", "venv", str(ROOT / ".venv")],
                    env=install_env,
                    description="create .venv",
                )
            processes.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    "backend/requirements.txt",
                    "-c",
                    "backend/requirements-lock.txt",
                ],
                env=install_env,
                description="install backend requirements",
            )
            processes.run(
                [node, npm_cli, "ci", "--no-audit", "--no-fund"],
                cwd=ROOT / "frontend",
                env=install_env,
                description="npm ci (existing package-lock.json)",
            )
        demo = None
        demo_env = None
        if not args.no_demo:
            demo_env = child_environment()
            demo_env["DEMO_PASSWORD"] = password
        api_env = child_environment(model=not args.no_model)
        api_env.update(TESTPILOT_DATABASE=str(database), DEMO_BASE_URL="http://127.0.0.1:8010")
        configured = bool(
            api_env.get("DEEPSEEK_API_KEY")
            or api_env.get("TESTPILOT_MODEL_KEY")
            or api_env.get("TESTPILOT_MODEL_URL")
        )
        say(
            f"[model] {'configured (values hidden)' if configured else 'not configured/disabled; confirmed cases and reports remain usable'}"
        )
        frontend_env = child_environment()
        frontend_env["VITE_USE_MOCK"] = "false"
        host = str(ROOT / "scripts/service_host.py")
        if demo_env is not None:
            demo = processes.spawn([str(python), host, "demo"], env=demo_env, service=True)
        api = processes.spawn([str(python), host, "api"], env=api_env, service=True)
        frontend = processes.spawn(
            [
                node,
                npm_cli,
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                "5173",
                "--strictPort",
            ],
            cwd=ROOT / "frontend",
            env=frontend_env,
        )
        services = [api, frontend]
        if demo is not None:
            services.insert(0, demo)
            wait_ready(
                services, "http://127.0.0.1:8010/me", 401, json_body={"code": "UNAUTHORIZED"}
            )
        wait_ready(services, "http://127.0.0.1:8000/api/health", 200, json_body={"status": "ok"})
        wait_ready(services, "http://127.0.0.1:5173/projects", 200)
        wait_ready(services, "http://127.0.0.1:5173/api/health", 200, json_body={"status": "ok"})
        say("[READY] frontend: http://127.0.0.1:5173/projects (REAL mode)")
        if demo is not None:
            say("[READY] API docs: http://127.0.0.1:8000/docs ; demo: http://127.0.0.1:8010")
            say(
                "[next] Create a project and requirement; configure demo credentials in the environment page."
            )
        else:
            say("[READY] API docs: http://127.0.0.1:8000/docs ; demo service skipped")
            say("[next] Create a project and requirement; set the local service target in the environment page.")
        say(
            "[next] Without a model, save/confirm a manual case, execute it, and download the report."
        )
        say(
            "[stop] Press Enter or Ctrl+C here. Only this launcher's child processes will stop; databases are retained."
        )
        stop = threading.Event()

        def read_stop():
            sys.stdin.readline()
            stop.set()

        threading.Thread(target=read_stop, daemon=True).start()
        while not stop.wait(0.2):
            if any(process.poll() is not None for process in services):
                raise StartError(
                    "A service exited. This session will stop its own remaining children; inspect the error and restart."
                )
        return 0
    finally:
        processes.close()
        say("[stopped] Owned services stopped; database files preserved.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StartError as error:
        say(f"[ERROR] {error}")
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        say("[stopped] Interrupted. Existing services and databases were not removed.")
        raise SystemExit(130) from None
