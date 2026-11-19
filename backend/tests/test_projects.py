import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient

from backend.app.core.config import REPOSITORY_ROOT, Settings
from backend.app.main import create_app
from backend.app.modules.agent.clarify import ModelError


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "test.sqlite3")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def project(client, name="测试项目"):
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def requirement(client, project_id, text="系统支持登录并返回用户信息"):
    response = client.post(f"/api/projects/{project_id}/requirements", json={"text": text})
    assert response.status_code == 201, response.text
    return response.json()


def test_complete_data_workflow_and_reopen_database(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/projects").json() == []
        assert client.get("/api/health").json() == {"status": "ok"}
        pid = project(client)
        base = f"/api/projects/{pid}"
        req = requirement(client, pid)
        assert req["version"] == 1
        updated = client.patch(
            f"{base}/requirements/{req['id']}", json={"text": "登录成功返回200和非空token"}
        ).json()
        assert updated["version"] == 2
        assert updated["id"] == req["id"]
        for method, path in [("POST", "/auth/login"), ("GET", "/me")]:
            response = client.post(f"{base}/endpoints", json={"method": method, "path": path})
            assert response.status_code == 201
            assert response.json()["version"] == 1
        assert client.get(f"{base}/environment").json() == {
            "target": "demo",
            "service_id": None,
            "base_url": None,
            "environment_version": None,
            "configured_keys": [],
        }
        response = client.put(
            f"{base}/environment",
            json={
                "target": "demo",
                "secrets": {"username": "fixture-user", "password": "fixture-password"},
            },
        )
        assert response.status_code == 200
        assert response.json() == {
            "target": "demo",
            "service_id": "demo",
            "base_url": None,
            "environment_version": 1,
            "configured_keys": ["password", "username"],
        }
        assert "fixture-password" not in response.text
        assert "fixture-user" not in response.text
    # New app and new DB connections, same file: no fixture or in-memory state.
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get("/api/projects").json() == [{"id": pid, "name": "测试项目"}]
        assert restarted.get(f"{base}/requirements").json() == [updated]
        assert len(restarted.get(f"{base}/endpoints").json()) == 2
        environment = restarted.get(f"{base}/environment")
        assert environment.json()["configured_keys"] == ["password", "username"]
        assert "fixture-password" not in environment.text
        assert restarted.app.state.project_repository.read_environment(pid, "demo") == {
            "username": "fixture-user",
            "password": "fixture-password",
        }


def test_project_isolation_and_internal_adapters(client):
    first, second = project(client, "A"), project(client, "B")
    req = requirement(client, first)
    endpoint = client.post(
        f"/api/projects/{first}/endpoints", json={"method": "POST", "path": "/auth/login"}
    ).json()
    response = client.patch(
        f"/api/projects/{second}/requirements/{req['id']}", json={"text": "禁止越界修改"}
    )
    assert response.status_code == 404
    assert client.get(f"/api/projects/{second}/requirements").json() == []
    assert client.get(f"/api/projects/{second}/endpoints").json() == []
    repo = client.app.state.project_repository
    assert repo.load_text(second, req["id"]) is None
    assert repo.load_text(first, req["id"]) == req["text"]
    for getter, identifier in [
        (repo.get_requirement, req["id"]),
        (repo.get_endpoint, endpoint["id"]),
    ]:
        with pytest.raises(HTTPException) as error:
            getter(second, identifier)
        assert error.value.status_code == 404
        with pytest.raises(HTTPException) as error:
            getter(first, identifier, expected_version=99)
        assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        repo.get_requirement_version(second, req["id"], 1)
    assert error.value.status_code == 404
    assert repo.get_requirement(first, req["id"], expected_version=1) == req
    assert repo.get_endpoint(first, endpoint["id"], expected_version=1) == endpoint


def test_versions_history_and_source_preservation(client):
    pid = project(client)
    text = "  登录需要用户信息。\n保留引用位置。  "
    req = requirement(client, pid, text)
    repo = client.app.state.project_repository
    for version in range(2, 5):
        response = client.patch(
            f"/api/projects/{pid}/requirements/{req['id']}", json={"text": text}
        )
        assert response.json()["version"] == version
    assert repo.get_requirement_version(pid, req["id"], 1)["text"] == text
    assert repo.get_requirement_version(pid, req["id"], 4)["text"] == text
    with pytest.raises(HTTPException) as error:
        repo.get_requirement(pid, req["id"], expected_version=1)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        repo.get_requirement_version(pid, req["id"], 99)
    assert error.value.status_code == 404


def test_parallel_requirement_edits_have_distinct_versions(client):
    pid = project(client)
    req = requirement(client, pid)
    repo = client.app.state.project_repository
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda i: repo.update_requirement(pid, req["id"], f"修订{i}"), range(8))
        )
    assert sorted(row["version"] for row in results) == list(range(2, 10))
    assert repo.get_requirement(pid, req["id"])["version"] == 9
    for result in results:
        assert repo.get_requirement_version(pid, req["id"], result["version"]) == result


@pytest.mark.parametrize("route", ["requirements", "endpoints", "environment"])
def test_missing_project_rejected(client, route):
    response = client.get(f"/api/projects/missing/{route}")
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("name", ["", "   ", "a" * 101, 123, None])
def test_invalid_project_name(client, name):
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 422
    assert set(response.json()) == {"detail"}
    assert client.get("/api/projects").json() == []


@pytest.mark.parametrize("text", ["", "  \n", "a" * 16001, 1, None])
def test_invalid_requirement(client, text):
    pid = project(client)
    response = client.post(f"/api/projects/{pid}/requirements", json={"text": text})
    assert response.status_code == 422
    assert client.get(f"/api/projects/{pid}/requirements").json() == []


@pytest.mark.parametrize(
    "path",
    [
        "https://example.invalid/me",
        "//example.invalid/me",
        "me",
        "/../me",
        "/a/../me",
        "/%2e%2e/me",
        "/%2fexample.invalid",
        "/a\\me",
        "/me#fragment",
        "/me\n",
        "/me\x7f",
    ],
)
def test_unsafe_endpoint_rejected(client, path):
    pid = project(client)
    response = client.post(f"/api/projects/{pid}/endpoints", json={"method": "GET", "path": path})
    assert response.status_code == 422


def test_endpoint_method_normalization_and_target_injection(client):
    pid = project(client)
    base = f"/api/projects/{pid}"
    response = client.post(
        f"{base}/endpoints", json={"method": "get", "path": "/items?page_size=1"}
    )
    assert response.status_code == 201
    assert response.json()["method"] == "GET"
    for payload in [
        {"method": "TRACE", "path": "/me"},
        {"method": "GET", "path": "/me", "base_url": "http://example.invalid"},
    ]:
        assert client.post(f"{base}/endpoints", json=payload).status_code == 422


def test_environment_updates_do_not_leak_and_cannot_change_target(client):
    pid, other = project(client), project(client)
    url = f"/api/projects/{pid}/environment"
    repo = client.app.state.project_repository
    with pytest.raises(HTTPException) as error:
        repo.read_environment(pid)
    assert error.value.status_code == 422
    for password in ["fixture-first", "fixture-replacement"]:
        response = client.put(
            url,
            json={"target": "demo", "secrets": {"username": "fixture-user", "password": password}},
        )
        assert response.status_code == 200
        assert password not in response.text
        assert "fixture-user" not in response.text
    assert repo.read_environment(pid)["password"] == "fixture-replacement"
    assert client.get(f"/api/projects/{other}/environment").json()["configured_keys"] == []
    for payload in [
        {
            "target": "https://example.invalid",
            "secrets": {"username": "u", "password": "private-sentinel"},
        },
        {"target": "demo", "secrets": {"username": 123, "password": "private-sentinel"}},
        {"target": "demo", "secrets": {"username": "u", "password": ""}},
        {"target": "demo", "secrets": {"username": "u"}},
        {
            "target": "demo",
            "secrets": {
                "username": "u",
                "password": "private-sentinel",
                "token": "private-sentinel",
            },
        },
    ]:
        response = client.put(url, json=payload)
        assert response.status_code == 422
        assert "private-sentinel" not in response.text
        assert isinstance(response.json()["detail"], str)
    assert repo.read_environment(pid)["password"] == "fixture-replacement"
    with pytest.raises(HTTPException):
        repo.read_environment(pid, "arbitrary-target")
    with pytest.raises(HTTPException):
        repo.read_environment("missing")


def test_transaction_rollback_and_foreign_keys(client):
    database = client.app.state.database
    with pytest.raises(RuntimeError):
        with database.connection(write=True) as connection:
            connection.execute("INSERT INTO projects VALUES ('rollback', 'should rollback')")
            raise RuntimeError("abort")
    assert client.get("/api/projects").json() == []
    with pytest.raises(sqlite3.IntegrityError):
        with database.connection(write=True) as connection:
            connection.execute("INSERT INTO requirements VALUES ('r', 'missing', 'bad', 1)")


def test_missing_project_writes_do_not_leave_orphans(client):
    base = "/api/projects/missing"
    for method, url, payload in [
        ("POST", f"{base}/requirements", {"text": "需求"}),
        ("POST", f"{base}/endpoints", {"method": "GET", "path": "/me"}),
        ("PATCH", f"{base}/requirements/missing", {"text": "需求"}),
        (
            "PUT",
            f"{base}/environment",
            {"target": "demo", "secrets": {"username": "u", "password": "p"}},
        ),
    ]:
        assert client.request(method, url, json=payload).status_code == 404


def test_error_shape_for_malformed_json_and_http_errors(client):
    for response in [
        client.get("/api/not-found"),
        client.delete("/api/projects"),
        client.post(
            "/api/projects",
            content='{"password":"private-sentinel",',
            headers={"content-type": "application/json"},
        ),
    ]:
        assert response.status_code in {404, 405, 422}
        assert set(response.json()) == {"detail"}
        assert isinstance(response.json()["detail"], str)
        assert "private-sentinel" not in response.text


def test_explicit_router_registration_and_generic_errors(settings):
    extra = APIRouter()

    @extra.get("/api/integration-probe")
    def broken():
        raise RuntimeError("private-sentinel")

    calls = []
    app = create_app(settings, routers=[extra], startup_hooks=[lambda app: calls.append(app)])
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/integration-probe")
        assert response.status_code == 500
        assert response.json() == {"detail": "服务内部错误"}
        assert calls == [app]
        schema = client.get("/openapi.json").json()
        assert "/api/projects/{project_id}/environment" in schema["paths"]


def test_database_path_is_independent_of_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert (
        Settings(database_path="backend/data/test.sqlite3").database_path
        == (REPOSITORY_ROOT / "backend/data/test.sqlite3").resolve()
    )


@pytest.mark.parametrize(
    "target",
    ["ftp://localhost", "http://u:p@localhost", "http://localhost/path", "http://localhost?x=1"],
)
def test_invalid_server_target_config(target):
    with pytest.raises(ValueError):
        Settings(demo_base_url=target)


def test_agent_router_reads_current_database_text_and_preserves_quotes(settings):
    received = []

    def provider(text):
        received.append(text)
        return {"questions": [{"quote": text, "question": "成功条件是什么？"}]}

    with TestClient(create_app(settings, agent_provider=provider)) as client:
        pid = project(client)
        req = requirement(client, pid)
        route = f"/api/projects/{pid}/agent/clarify"
        response = client.post(route, json={"requirement_id": req["id"]})
        assert response.status_code == 200
        assert response.json() == {
            "status": "NEEDS_INFO",
            "questions": [{"quote": req["text"], "question": "成功条件是什么？"}],
        }
        replacement = "登录成功返回200和非空token"
        client.patch(f"/api/projects/{pid}/requirements/{req['id']}", json={"text": replacement})
        response = client.post(route, json={"requirement_id": req["id"]})
        assert response.json()["questions"][0]["quote"] == replacement
        assert received == [req["text"], replacement]


def test_agent_router_rejects_foreign_requirement_before_model_call(settings):
    received = []

    def provider(text):
        received.append(text)
        return {"questions": []}

    with TestClient(create_app(settings, agent_provider=provider)) as client:
        first, second = project(client), project(client)
        req = requirement(client, first)
        for pid, rid in [(second, req["id"]), (first, "missing"), ("missing", req["id"])]:
            response = client.post(
                f"/api/projects/{pid}/agent/clarify", json={"requirement_id": rid}
            )
            assert response.status_code == 404
            assert isinstance(response.json()["detail"], str)
        assert received == []


def test_agent_failure_keeps_project_and_requirement_usable(settings):
    def provider(text):
        raise ModelError("模型服务暂不可用")

    with TestClient(create_app(settings, agent_provider=provider)) as client:
        pid = project(client)
        req = requirement(client, pid)
        response = client.post(
            f"/api/projects/{pid}/agent/clarify", json={"requirement_id": req["id"]}
        )
        assert response.status_code == 502
        assert response.json() == {"detail": "模型服务暂不可用"}
        assert client.get(f"/api/projects/{pid}/requirements").json() == [req]

def test_local_environment_can_omit_credentials(client):
    pid = project(client, "local-no-login")
    response = client.put(
        f"/api/projects/{pid}/environment",
        json={"target": "local", "service_id": "arrow-game", "base_url": "http://127.0.0.1:8030"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "target": "local",
        "service_id": "arrow-game",
        "base_url": "http://127.0.0.1:8030",
        "environment_version": 1,
        "configured_keys": [],
    }
    assert client.get(f"/api/projects/{pid}/environment").json()["configured_keys"] == []


def test_demo_environment_requires_credentials(client):
    pid = project(client, "demo-requires")
    response = client.put(f"/api/projects/{pid}/environment", json={"target": "demo"})
    assert response.status_code == 422