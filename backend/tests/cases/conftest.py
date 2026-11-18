import threading

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from demo_service.server import make_server


@pytest.fixture
def demo_url():
    server = make_server("demo-user", "case-test-only", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.fixture
def settings(tmp_path, demo_url):
    return Settings(database_path=tmp_path / "cases.sqlite3", demo_base_url=demo_url)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def create_context(client):
    project = client.post("/api/projects", json={"name": "用例报告验收"}).json()
    base = f"/api/projects/{project['id']}"
    requirement = client.post(base + "/requirements", json={
        "text": "正确密码登录返回200及token，查询本人信息返回demo-user；错误密码返回401。"
    }).json()
    login = client.post(base + "/endpoints", json={
        "method": "POST", "path": "/auth/login"
    }).json()
    me = client.post(base + "/endpoints", json={"method": "GET", "path": "/me"}).json()
    client.put(base + "/environment", json={
        "target": "demo", "secrets": {"username": "demo-user", "password": "case-test-only"}
    })
    draft = {
        "title": "登录后查询本人信息", "requirement_id": requirement["id"],
        "requirement_version": 1, "expected_basis": "登录成功返回200，user.id应为demo-user",
        "steps": [
            {"name": "login", "phase": "setup", "endpoint_id": login["id"],
             "endpoint_version": 1, "headers": {},
             "body": {"username": "{{env.username}}", "password": "{{env.password}}"},
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
    return base, draft


def save(client, base, draft, *, confirm=False):
    response = client.post(base + "/cases", json=draft)
    assert response.status_code == 201, response.text
    case = response.json()
    if confirm:
        response = client.post(base + f"/cases/{case['id']}/confirm", json={"version": 1})
        assert response.status_code == 200, response.text
        case = response.json()
    return case


def run_cases(client, base, cases):
    response = client.post(base + "/runs", json={
        "cases": [{"id": item["id"], "version": item["version"]} for item in cases]
    })
    assert response.status_code == 202, response.text
    client.app.state.run_service.wait_for_idle()
    run_id = response.json()["run_id"]
    return run_id, client.get(base + f"/runs/{run_id}").json()
