import copy
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.modules.runs.dependencies import PreflightRejected
from app.modules.runs.models import CaseRef
from app.modules.runs.repository import RunRepository
from app.modules.runs.service import RunService, RunSettings
from demo_service.server import make_server


class FakeDependencies:
    """Explicit test double for the unmerged cases/project-data modules."""

    def __init__(self, snapshots=(), environment=None, execution_target=None):
        self.snapshots = {item["case_id"]: item for item in snapshots}
        self.environment = environment or {"username": "demo-user", "password": "local-demo-only"}
        self.execution_target = execution_target or {
            "target": "demo",
            "service_id": "demo",
            "base_url": None,
        }
        self.preflight_calls = 0

    def preflight(self, project_id: str, cases: list[CaseRef]):
        self.preflight_calls += 1
        if project_id != "project-1":
            raise PreflightRejected(["项目不存在"])
        reasons = []
        selected = []
        for ref in cases:
            snapshot = self.snapshots.get(ref.id)
            if not snapshot:
                reasons.append(f"用例 {ref.id} 不存在")
            elif snapshot.get("status") != "CONFIRMED":
                reasons.append(f"用例 {ref.id} 尚未确认")
            elif snapshot["version"] != ref.version:
                reasons.append(f"用例 {ref.id} 版本已过期")
            else:
                selected.append(copy.deepcopy(snapshot))
        if reasons:
            raise PreflightRejected(reasons)
        return selected

    def read_execution_target(self, project_id: str):
        assert project_id == "project-1"
        if self.execution_target is None:
            raise PreflightRejected(["尚未配置项目测试环境"])
        return copy.deepcopy(self.execution_target)

    def read_environment(self, project_id: str, target: str):
        assert project_id == "project-1"
        assert target == self.execution_target["target"]
        return copy.deepcopy(self.environment)


@pytest.fixture
def demo_server():
    server = make_server("demo-user", "local-demo-only", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def service_factory(tmp_path):
    services = []

    def create(dependencies, base_url="http://127.0.0.1:8010", **kwargs):
        name = f"runs-{len(services)}.sqlite3"
        service = RunService(
            RunRepository(tmp_path / name),
            dependencies,
            RunSettings(demo_base_url=base_url, request_timeout_seconds=kwargs.pop("timeout", 1.0)),
            background=kwargs.pop("background", False),
            transport=kwargs.pop("transport", None),
            **kwargs,
        )
        services.append(service)
        return service

    yield create
    for service in services:
        service.close()


def endpoints():
    return {
        "ep-login": {"id": "ep-login", "method": "POST", "path": "/auth/login", "version": 1},
        "ep-me": {"id": "ep-me", "method": "GET", "path": "/me", "version": 1},
        "ep-slow": {"id": "ep-slow", "method": "GET", "path": "/slow", "version": 1},
    }


def login_step(phase="setup", expected=200, extract=True):
    assertions = [{"type": "status", "expected": expected}]
    if expected == 200:
        assertions.append({"type": "nonempty_string", "path": "token"})
    else:
        assertions.append({"type": "json_equals", "path": "code", "expected": "INVALID_CREDENTIALS"})
    return {
        "name": "login",
        "phase": phase,
        "endpoint_id": "ep-login",
        "endpoint_version": 1,
        "headers": {},
        "body": {"username": "{{env.username}}", "password": "{{env.password}}"},
        "assertions": assertions,
        "extract": {"token": "token"} if extract else {},
    }


def me_step(expected_user="demo-user"):
    return {
        "name": "me",
        "phase": "test",
        "endpoint_id": "ep-me",
        "endpoint_version": 1,
        "headers": {"Authorization": "Bearer {{steps.login.token}}"},
        "body": None,
        "assertions": [
            {"type": "status", "expected": 200},
            {"type": "json_equals", "path": "user.id", "expected": expected_user},
            {"type": "elapsed_ms_lte", "expected": 3000},
        ],
        "extract": {},
    }


def case_snapshot(case_id, title, steps, status="CONFIRMED"):
    return {
        "case_id": case_id,
        "project_id": "project-1",
        "title": title,
        "version": 1,
        "status": status,
        "requirement_id": "req-1",
        "requirement_version": 2,
        "expected_basis": "已确认需求：登录后返回本人编号 demo-user",
        "requirement": {"id": "req-1", "version": 2, "text": "系统支持登录并返回用户信息"},
        "steps": steps,
        "endpoints": endpoints(),
    }
