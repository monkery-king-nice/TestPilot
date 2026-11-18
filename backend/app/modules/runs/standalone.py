"""Temporary standalone harness while projects/cases modules are unmerged.

Run from repository root with:
  python -m uvicorn app.modules.runs.standalone:app --app-dir backend
This seeds four confirmed fixture cases; it is not the production composition root.
"""

import copy
import os
from pathlib import Path
from typing import Mapping, Sequence

from .app_factory import create_runs_app
from .dependencies import PreflightRejected
from .models import CaseRef
from .repository import RunRepository
from .service import RunService, RunSettings


def _login(password="{{env.password}}", phase="setup", expected=200):
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
        "body": {"username": "{{env.username}}", "password": password},
        "assertions": assertions,
        "extract": {"token": "token"} if expected == 200 else {},
    }


def _me(expected="demo-user"):
    return {
        "name": "me",
        "phase": "test",
        "endpoint_id": "ep-me",
        "endpoint_version": 1,
        "headers": {"Authorization": "Bearer {{steps.login.token}}"},
        "body": None,
        "assertions": [
            {"type": "status", "expected": 200},
            {"type": "json_equals", "path": "user.id", "expected": expected},
            {"type": "elapsed_ms_lte", "expected": 3000},
        ],
        "extract": {},
    }


def _case(case_id, title, steps):
    return {
        "case_id": case_id,
        "title": title,
        "version": 1,
        "status": "CONFIRMED",
        "requirement_id": "req-standalone",
        "requirement_version": 1,
        "expected_basis": "独立联调固定样例：登录并查询本人信息",
        "requirement": {"id": "req-standalone", "version": 1, "text": "系统支持登录并返回用户信息"},
        "steps": steps,
        "endpoints": {
            "ep-login": {"id": "ep-login", "method": "POST", "path": "/auth/login", "version": 1},
            "ep-me": {"id": "ep-me", "method": "GET", "path": "/me", "version": 1},
        },
    }


FIXTURE_CASES = {
    item["case_id"]: item
    for item in [
        _case("case-login-me", "登录后获取本人信息", [_login(), _me()]),
        _case("case-business-fail", "业务断言失败", [_login(), _me("not-demo-user")]),
        _case(
            "case-setup-blocked",
            "准备失败阻塞主步骤",
            [_login(password="intentionally-wrong"), _me()],
        ),
        _case(
            "case-invalid-login",
            "错误密码且预期 401",
            [_login(password="intentionally-wrong", phase="test", expected=401)],
        ),
    ]
}


class StandaloneDependencies:
    """Clearly marked test double; replace with team adapters during integration."""

    def preflight(self, project_id: str, cases: Sequence[CaseRef]) -> list[dict]:
        if project_id != "standalone-project":
            raise PreflightRejected(["独立演示仅支持项目 standalone-project"])
        selected = []
        for ref in cases:
            case = FIXTURE_CASES.get(ref.id)
            if not case:
                raise PreflightRejected([f"未知独立演示用例 {ref.id}"])
            if ref.version != case["version"]:
                raise PreflightRejected([f"用例 {ref.id} 版本已过期"])
            selected.append(copy.deepcopy(case))
        return selected

    def read_environment(self, project_id: str, target: str) -> Mapping[str, str]:
        if target != "demo":
            raise PreflightRejected(["仅允许 demo 目标"])
        return {
            "username": os.getenv("DEMO_USERNAME", "demo-user"),
            "password": os.environ["DEMO_PASSWORD"],
        }


_database = Path(os.getenv("RUNS_DB", "backend/data/runs-standalone.sqlite3"))
_service = RunService(
    RunRepository(_database),
    StandaloneDependencies(),
    RunSettings(
        demo_base_url=os.getenv("DEMO_BASE_URL", "http://127.0.0.1:8010"),
        request_timeout_seconds=float(os.getenv("RUN_TIMEOUT_SECONDS", "3")),
    ),
)
app = create_runs_app(_service)
